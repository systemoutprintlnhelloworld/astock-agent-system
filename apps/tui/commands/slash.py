"""Slash command dispatcher for the AStock terminal client."""

from __future__ import annotations

import json
import shlex
from typing import Protocol

from apps.tui.backend_client import BackendClientError
from apps.tui.commands.agent import CommandResult, handle_agent_command
from apps.tui.session import TuiSessionState, read_attachment_previews
from apps.tui.widgets import (
    render_agent_flow,
    render_agent_management_panel,
    render_decision_logs,
    render_learning_progress,
    render_provider_diagnostics,
    render_rankings,
    render_run_observability,
    render_status_bar,
    render_stock_board,
    render_todo_strip,
)
from apps.tui.prompt import command_help_lines


class TuiBackend(Protocol):
    """Backend methods used by the slash command layer."""

    def health(self) -> dict[str, object]: ...

    def config(self) -> dict[str, object]: ...

    def save_config(self, config: dict[str, object]) -> dict[str, object]: ...

    def test_llm(self, config: dict[str, object] | None = None, *, run_bench: bool = False) -> dict[str, object]: ...

    def list_models(self) -> dict[str, object]: ...

    def start_auto_investment(
        self,
        *,
        models: list[str] | None = None,
        offline: bool = False,
        max_count: int | None = None,
        days: int | None = None,
        background: bool = True,
    ) -> dict[str, object]: ...

    def run_status(self) -> dict[str, object]: ...

    def decisions(self) -> dict[str, object]: ...

    def stock_board(self) -> dict[str, object]: ...

    def rankings(self) -> dict[str, object]: ...

    def data_providers(self) -> dict[str, object]: ...

    def agent_flow(self) -> dict[str, object]: ...

    def learning_status(self) -> dict[str, object]: ...


def handle_slash_command(command: str, *, state: TuiSessionState, client: TuiBackend) -> CommandResult:
    """Handle one slash command from the chat input."""
    try:
        parts = shlex.split(command.strip(), posix=False)
    except ValueError as exc:
        return CommandResult(False, "命令解析失败", str(exc))
    if not parts or not parts[0].startswith("/"):
        return CommandResult(False, "命令错误", "请输入 /help 查看可用命令。")

    root = parts[0].lower()
    try:
        if root in {"/help", "/?"}:
            return CommandResult(True, "TUI 命令帮助", _help_text())
        if root == "/agent":
            return handle_agent_command(command)
        if root == "/status":
            return _status(state, client)
        if root == "/run":
            state.active_tab = "run"
            return _run_view(state, client)
        if root == "/models":
            return _models(parts, state, client)
        if root == "/workflow":
            return _workflow(parts, state)
        if root == "/start":
            return _start(parts, state, client)
        if root == "/providers":
            payload = client.data_providers()
            state.todo_status["数据源"] = "completed"
            return CommandResult(True, "数据源诊断", render_provider_diagnostics(payload))
        if root == "/dashboard":
            return _dashboard(parts, state, client)
        if root == "/config":
            return _config(parts, state, client)
        if root == "/compact":
            state.compact_history(auto=False)
            return CommandResult(True, "上下文已压缩", render_status_bar(state, _safe_run_status(client)))
        if root == "/theme":
            return _set_simple_state(parts, state, "theme", "主题")
        if root in {"/lang", "/language"}:
            return _set_simple_state(parts, state, "language", "语言")
        if root == "/permission":
            return _set_simple_state(parts, state, "permission_mode", "权限模式")
        if root == "/sandbox":
            return _set_simple_state(parts, state, "sandbox_mode", "沙盒模式")
        if root == "/attachments":
            if len(parts) > 1 and parts[1].lower() in {"show", "preview"}:
                return CommandResult(True, "附件预览", read_attachment_previews(state.attachments))
            return CommandResult(True, "附件路径", "\n".join(state.attachments) if state.attachments else "暂无附件。")
        if root in {"/history", "/memory"}:
            body = "\n".join(f"- {message.role}: {message.content[:120]}" for message in state.messages[-20:])
            return CommandResult(True, "本地 TUI 对话历史", body or "暂无本地历史。")
        if root == "/exit":
            return CommandResult(True, "EXIT", "收到 exit，TUI 将结束；后端后台任务不会被强制中断。")
    except BackendClientError as exc:
        return CommandResult(False, "后端请求失败", str(exc))
    except Exception as exc:  # pragma: no cover - interactive runtime guard
        return CommandResult(False, "命令执行失败", str(exc))
    return CommandResult(False, "未知命令", _help_text())


def _status(state: TuiSessionState, client: TuiBackend) -> CommandResult:
    health = client.health()
    run_status = client.run_status()
    lines = [
        render_status_bar(state, run_status),
        render_todo_strip(state),
        "",
        f"Backend: {health.get('status', 'unknown')} {health.get('app', '')}",
    ]
    return CommandResult(True, "TUI 状态", "\n".join(lines))


def _models(parts: list[str], state: TuiSessionState, client: TuiBackend) -> CommandResult:
    if len(parts) >= 2 and parts[1].lower() == "selected":
        return CommandResult(True, "当前比赛模型", ", ".join(state.selected_models))
    if len(parts) >= 2 and parts[1].lower() == "select":
        models = _refresh_models_for_selection(state, client)
        if not models:
            return CommandResult(False, "模型选择失败", "后端没有返回可选模型；请先检查 /config test-llm。")
        try:
            from InquirerPy import inquirer
            from InquirerPy.base.control import Choice

            selected = inquirer.checkbox(
                message="选择本轮比赛模型（空格选择/取消，Enter 确认）",
                choices=[Choice(value=model, name=model) for model in models],
                default=[model for model in state.selected_models if model in models],
                instruction="比赛模型会并行启动独立 Agent 和独立虚拟账户",
            ).execute()
        except Exception as exc:
            return CommandResult(False, "模型选择失败", f"无法打开交互式选择器：{exc}")
        state.set_models([str(model) for model in selected])
        return CommandResult(True, "模型已选择", ", ".join(state.selected_models))
    if len(parts) >= 3 and parts[1].lower() == "set":
        models = _csv_args(parts[2:])
        state.set_models(models)
        return CommandResult(True, "模型已选择", ", ".join(state.selected_models))
    models = _refresh_models_for_selection(state, client)
    if models:
        lines = ["后端模型列表（运行前用 /models select 多选，或用 /models set 手动选择比赛模型）:"]
        lines.extend(f"- {model}" for model in state.available_models)
        lines.append("")
        lines.append(f"当前比赛模型: {', '.join(state.selected_models)}")
        return CommandResult(True, "模型列表", "\n".join(lines))
    payload = client.list_models()
    return CommandResult(True, "模型列表", json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _workflow(parts: list[str], state: TuiSessionState) -> CommandResult:
    if len(parts) < 2:
        return CommandResult(True, "当前工作流", ", ".join(state.workflow_types))
    ok, message = state.set_workflow_types(_csv_args(parts[1:]))
    return CommandResult(ok, "工作流选择" if ok else "工作流选择失败", message)


def _start(parts: list[str], state: TuiSessionState, client: TuiBackend) -> CommandResult:
    options = _parse_start_options(parts[1:], state)
    state.todo_status["运行"] = "in_progress"
    try:
        payload = client.start_auto_investment(**options)
    except Exception:
        state.todo_status["运行"] = "failed"
        raise
    run_id = str(payload.get("run_id", ""))
    state.last_run_id = run_id
    state.todo_status["运行"] = "completed" if str(payload.get("status", "")).lower() in {"accepted", "ok"} else "failed"
    state.active_tab = "run"
    return CommandResult(
        True,
        "自动投资已提交" if options.get("background", True) else "自动投资已完成",
        _render_run_view_safe(state, client, run_id=run_id),
    )


def _dashboard(parts: list[str], state: TuiSessionState, client: TuiBackend) -> CommandResult:
    tab = parts[1].lower() if len(parts) > 1 else "trading"
    state.active_tab = tab
    if tab in {"overview", "status"}:
        return _status(state, client)
    if tab in {"providers", "data"}:
        return CommandResult(True, "数据源诊断", render_provider_diagnostics(client.data_providers()))
    if tab in {"rankings", "performance"}:
        return CommandResult(True, "模型排行榜", render_rankings(client.rankings()))
    if tab in {"stocks", "board", "trading"}:
        return CommandResult(True, "交易看板", render_stock_board(client.stock_board()))
    if tab in {"run", "runs", "current"}:
        return _run_view(state, client)
    if tab in {"decisions", "logs"}:
        return CommandResult(True, "决策日志", render_decision_logs(client.decisions()))
    if tab in {"flow", "agents"}:
        return CommandResult(True, "Agent 编排", render_agent_flow(client.agent_flow()))
    if tab in {"agent-md", "agent"}:
        return CommandResult(True, "Agent 管理", render_agent_management_panel())
    if tab in {"learning", "memory"}:
        learning = client.learning_status().get("learning", {})
        return CommandResult(True, "学习进度", render_learning_progress(learning if isinstance(learning, dict) else {}))
    return CommandResult(False, "未知面板", "可用面板: trading/run/status/providers/rankings/decisions/flow/agent/learning")


def _run_view(state: TuiSessionState, client: TuiBackend) -> CommandResult:
    return CommandResult(True, "运行观测", _render_run_view_safe(state, client, run_id=state.last_run_id))


def _render_run_view_safe(state: TuiSessionState, client: TuiBackend, *, run_id: str = "") -> str:
    return render_run_observability(
        run_status=_safe_run_status(client),
        rankings=_safe_payload(client.rankings),
        stock_board=_safe_payload(client.stock_board),
        decisions=_safe_payload(client.decisions),
        run_id=run_id,
    )


def _config(parts: list[str], state: TuiSessionState, client: TuiBackend) -> CommandResult:
    action = parts[1].lower() if len(parts) > 1 else "show"
    if action == "show":
        payload = client.config()
        state.todo_status["配置"] = "completed"
        return CommandResult(True, "当前配置", json.dumps(payload.get("config", {}), ensure_ascii=False, indent=2, default=str))
    if action == "test-llm":
        return CommandResult(True, "LLM 配置检测", json.dumps(client.test_llm(run_bench="--bench" in parts), ensure_ascii=False, indent=2, default=str))
    return CommandResult(False, "配置命令错误", "/config show | /config test-llm [--bench]")


def _set_simple_state(parts: list[str], state: TuiSessionState, attr: str, label: str) -> CommandResult:
    if len(parts) < 2:
        return CommandResult(True, f"当前{label}", str(getattr(state, attr)))
    setattr(state, attr, parts[1])
    return CommandResult(True, f"{label}已更新", str(getattr(state, attr)))


def _parse_start_options(parts: list[str], state: TuiSessionState) -> dict[str, object]:
    offline = "--offline" in parts or "offline" in state.workflow_types
    background = "--foreground" not in parts
    max_count = _flag_int(parts, "--max-count")
    days = _flag_int(parts, "--days")
    models = state.selected_models
    if "--models" in parts:
        index = parts.index("--models")
        if index + 1 < len(parts):
            models = _csv_args([parts[index + 1]])
            state.set_models(models)
    return {
        "models": models,
        "offline": offline,
        "max_count": max_count,
        "days": days,
        "background": background,
    }


def _flag_int(parts: list[str], flag: str) -> int | None:
    if flag not in parts:
        return None
    index = parts.index(flag)
    if index + 1 >= len(parts):
        return None
    try:
        return int(parts[index + 1])
    except ValueError:
        return None


def _csv_args(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        items.extend(part.strip() for part in value.split(",") if part.strip())
    return list(dict.fromkeys(items))


def _refresh_models_for_selection(state: TuiSessionState, client: TuiBackend) -> list[str]:
    payload = client.list_models()
    models = payload.get("models", []) if isinstance(payload, dict) else []
    if isinstance(models, list):
        state.set_available_models([str(model) for model in models])
    return state.available_models


def _safe_run_status(client: TuiBackend) -> dict[str, object]:
    try:
        return client.run_status()
    except Exception:
        return {"status": "unknown"}


def _safe_payload(loader) -> dict[str, object]:
    try:
        payload = loader()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _help_text() -> str:
    return "\n".join(command_help_lines())
