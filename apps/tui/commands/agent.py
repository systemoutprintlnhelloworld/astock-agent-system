"""Agent Markdown slash commands for the future TUI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from astock_agent_system.agent_descriptor import backup_agent_descriptor, list_agent_descriptors, load_agent_descriptor
from astock_agent_system.agent_learning import get_learning_status, load_learning_suggestions, trigger_learning_if_ready


@dataclass(slots=True)
class CommandResult:
    """Small command result object for rendering in chat panels."""

    ok: bool
    title: str
    body: str


def handle_agent_command(command: str, *, opener: Callable[[str], None] | None = None) -> CommandResult:
    """Handle ``/agent`` subcommands without depending on a TUI framework.

    Supported forms:
    - ``/agent list``
    - ``/agent view technical``
    - ``/agent edit technical`` (uses injected opener when provided)
    - ``/agent backup technical``
    - ``/agent learning stats``
    - ``/agent learning trigger``
    """
    parts = command.strip().split()
    if not parts or parts[0] != "/agent":
        return CommandResult(False, "Agent 命令错误", "命令必须以 /agent 开头。")
    if len(parts) == 1 or parts[1] in {"help", "?"}:
        return CommandResult(True, "Agent 命令帮助", _help_text())

    action = parts[1]
    try:
        if action == "list":
            return _list_agents()
        if action == "view" and len(parts) >= 3:
            return _view_agent(parts[2])
        if action == "edit" and len(parts) >= 3:
            return _edit_agent(parts[2], opener=opener)
        if action == "backup" and len(parts) >= 3:
            path = backup_agent_descriptor(parts[2])
            return CommandResult(True, "Agent MD 已备份", str(path))
        if action == "learning" and len(parts) >= 3:
            if parts[2] == "stats":
                return _learning_stats()
            if parts[2] == "suggestions":
                return _learning_suggestions()
            if parts[2] == "trigger":
                status = trigger_learning_if_ready(force=True)
                return CommandResult(True, "学习分析已触发", _format_learning_status(status))
    except Exception as exc:  # pragma: no cover - defensive for TUI runtime
        return CommandResult(False, "Agent 命令失败", str(exc))
    return CommandResult(False, "Agent 命令错误", _help_text())


def _list_agents() -> CommandResult:
    lines = []
    for descriptor in list_agent_descriptors():
        lines.append(f"- {descriptor.agent_id} {descriptor.version}: {descriptor.name}")
    return CommandResult(True, "Agent 列表", "\n".join(lines) if lines else "未找到 Agent Markdown 描述文件。")


def _view_agent(agent_id: str) -> CommandResult:
    descriptor = load_agent_descriptor(agent_id)
    return CommandResult(True, f"Agent: {descriptor.agent_id}", descriptor.raw_content)


def _edit_agent(agent_id: str, opener: Callable[[str], None] | None) -> CommandResult:
    descriptor = load_agent_descriptor(agent_id)
    if opener is None:
        return CommandResult(True, "Agent MD 路径", str(descriptor.description_path))
    opener(str(descriptor.description_path))
    return CommandResult(True, "Agent MD 已交给外部编辑器", str(descriptor.description_path))


def _learning_stats() -> CommandResult:
    return CommandResult(True, "Agent 学习状态", _format_learning_status(get_learning_status()))


def _learning_suggestions() -> CommandResult:
    payload = load_learning_suggestions()
    suggestions = payload.get("suggestions", [])
    if not suggestions:
        return CommandResult(True, "Agent 学习建议", "暂无可查看的学习建议。请先运行 /agent learning trigger。")
    lines = [
        f"分析时间: {payload.get('analyzed_at', '') or '未知'}",
        f"分析样本数: {payload.get('analyzed_count', 0)}",
        f"触发阈值: {payload.get('threshold', 0)}",
        "",
    ]
    for index, suggestion in enumerate(suggestions, start=1):
        lines.append(
            f"{index}. {suggestion.get('agent_id', '')} / {suggestion.get('section', '')} / {suggestion.get('metric', '')}"
        )
        lines.append(f"   当前值: {suggestion.get('current_value', '未知')}")
        lines.append(f"   建议值: {suggestion.get('suggested_value', '未知')}")
        lines.append(f"   原因: {suggestion.get('reason', '')}")
        lines.append(f"   置信度: {float(suggestion.get('confidence', 0.0) or 0.0):.0%}")
        lines.append("")
    return CommandResult(True, "Agent 学习建议", "\n".join(lines).strip())


def _format_learning_status(status: dict[str, object]) -> str:
    threshold = int(status.get("threshold", 30) or 30)
    progress = int(status.get("progress", 0) or 0)
    filled = int((progress / threshold) * 20) if threshold else 0
    bar = "█" * filled + "░" * (20 - filled)
    return (
        f"学习进度: {bar} {progress}/{threshold}\n"
        f"经验总数: {status.get('total_experiences', 0)}\n"
        f"成功率: {float(status.get('success_rate', 0.0) or 0.0):.1%}\n"
        f"平均收益: {float(status.get('average_return_pct', 0.0) or 0.0):.2f}%\n"
        f"是否可分析: {status.get('ready', False)}"
    )


def _help_text() -> str:
    return "\n".join(
        [
            "/agent list - 列出所有 Agent Markdown",
            "/agent view <agent> - 查看 Agent Markdown",
            "/agent edit <agent> - 返回路径或交给外部编辑器",
            "/agent backup <agent> - 备份当前 Agent Markdown",
            "/agent learning stats - 查看学习进度",
            "/agent learning suggestions - 查看最近学习建议",
            "/agent learning trigger - 强制生成学习建议",
        ]
    )
