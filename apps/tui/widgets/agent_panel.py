"""Text render helpers for Agent Markdown management panels.

These functions are framework-neutral. The Textual implementation can wrap the
returned strings in Static/RichLog widgets while tests can assert them directly.
"""

from __future__ import annotations

from astock_agent_system.agent_descriptor import list_agent_descriptors
from astock_agent_system.agent_learning import get_learning_status


def render_agent_management_panel() -> str:
    """Render a compact Agent management table for the TUI right pane."""
    lines = ["Agent 管理", "=" * 40]
    for descriptor in list_agent_descriptors():
        rules = descriptor.rules
        key_rules = ", ".join(f"{key}={value}" for key, value in list(rules.items())[:3]) or "无可调规则"
        lines.append(f"[{descriptor.agent_id}] {descriptor.version} - {descriptor.name}")
        lines.append(f"  更新: {descriptor.updated_at or '未知'} | {descriptor.update_reason or '无'}")
        lines.append(f"  规则: {key_rules}")
    if len(lines) == 2:
        lines.append("未找到 Agent Markdown 描述文件。")
    return "\n".join(lines)


def render_learning_progress(status: dict[str, object] | None = None) -> str:
    """Render the learning progress bar used under the chat/status area."""
    status = status or get_learning_status()
    threshold = int(status.get("threshold", 30) or 30)
    progress = int(status.get("progress", 0) or 0)
    filled = int((progress / threshold) * 20) if threshold else 0
    bar = "█" * filled + "░" * (20 - filled)
    return (
        f"学习进度: {bar} {progress}/{threshold} | "
        f"经验总数: {status.get('total_experiences', 0)} | "
        f"成功率: {float(status.get('success_rate', 0.0) or 0.0):.1%} | "
        f"平均收益: {float(status.get('average_return_pct', 0.0) or 0.0):.2f}%"
    )

