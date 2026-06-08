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
    render_status_bar,
    render_stock_board,
    render_todo_strip,
)


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
    if len(parts) >= 3 and parts[1].lower() == "set":
        models = _csv_args(parts[2:])
        state.set_models(models)
        return CommandResult(True, "模型已选择", ", ".join(state.selected_models))
    payload = client.list_models()
    models = payload.get("models", []) if isinstance(payload, dict) else []
    if isinstance(models, list) and models:
        return CommandResult(True, "模型列表", "\n".join(f"- {model}" for model in models))
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
    return CommandResult(
        True,
        "自动投资已提交" if options.get("background", True) else "自动投资已完成",
        json.dumps({"run_id": run_id, "status": payload.get("status"), "background": options.get("background", True)}, ensure_ascii=False, indent=2),
    )


def _dashboard(parts: list[str], state: TuiSessionState, client: TuiBackend) -> CommandResult:
    tab = parts[1].lower() if len(parts) > 1 else state.active_tab
    state.active_tab = tab
    if tab in {"overview", "status"}:
        return _status(state, client)
    if tab in {"providers", "data"}:
        return CommandResult(True, "数据源诊断", render_provider_diagnostics(client.data_providers()))
    if tab in {"rankings", "performance"}:
        return CommandResult(True, "模型排行榜", render_rankings(client.rankings()))
    if tab in {"stocks", "board", "trading"}:
        return CommandResult(True, "交易看板", render_stock_board(client.stock_board()))
    if tab in {"decisions", "logs"}:
        return CommandResult(True, "决策日志", render_decision_logs(client.decisions()))
    if tab in {"flow", "agents"}:
        return CommandResult(True, "Agent 编排", render_agent_flow(client.agent_flow()))
    if tab in {"agent-md", "agent"}:
        return CommandResult(True, "Agent 管理", render_agent_management_panel())
    if tab in {"learning", "memory"}:
        learning = client.learning_status().get("learning", {})
        return CommandResult(True, "学习进度", render_learning_progress(learning if isinstance(learning, dict) else {}))
    return CommandResult(False, "未知面板", "可用面板: overview/providers/rankings/stocks/decisions/flow/agent/learning")


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


def _safe_run_status(client: TuiBackend) -> dict[str, object]:
    try:
        return client.run_status()
    except Exception:
        return {"status": "unknown"}


def _help_text() -> str:
    return "\n".join(
        [
            "/help - 查看命令",
            "/status - 后端、任务和上下文状态",
            "/config show | /config test-llm [--bench] - 查看或检测配置",
            "/models - 刷新模型列表；/models set rule-baseline,gpt-5.4-mini - 选择模型",
            "/workflow auto|daily|offline|review - 选择工作流；auto/daily 不能与其他类型多选",
            "/start [--offline] [--models a,b] [--max-count N] [--days N] [--foreground] - 启动模拟盘轮次",
            "/providers - 查看数据源 provider chain 诊断",
            "/dashboard overview|providers|rankings|stocks|decisions|flow|agent|learning - 切换右侧看板",
            "/agent list/view/edit/backup/learning stats|suggestions|trigger - 管理 Agent Markdown",
            "/compact - 手动压缩本地 TUI 对话上下文",
            "/permission ask|auto|deny /sandbox read-only|workspace-write - 设置终端交互约束",
            "/theme dark|light /lang zh-CN|en-US /attachments [show] /history /exit",
        ]
    )
