"""Session state for the AStock terminal UI."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path


WINDOWS_PATH_PATTERN = re.compile(r'"([A-Za-z]:\\[^"\r\n]+)"|(?<!\w)([A-Za-z]:\\[^\s"<>|]+)')
WORKFLOW_ALIASES = {
    "自动": "auto",
    "整刊": "daily",
    "离线": "offline",
    "在线": "online",
    "复盘": "review",
    "审查": "review",
}
SENSITIVE_ATTACHMENT_NAMES = {".env", ".env.local", "credentials.json", "secrets.json"}
SENSITIVE_ATTACHMENT_KEYWORDS = ("secret", "token", "apikey", "api_key", "password", "credential")


@dataclass(slots=True)
class ChatMessage:
    """One compact chat-flow message shown in the left pane."""

    role: str
    content: str


@dataclass(slots=True)
class TuiSessionState:
    """Mutable UI-only state; authoritative data remains in the backend."""

    backend_url: str = "http://127.0.0.1:18080"
    selected_models: list[str] = field(default_factory=lambda: ["rule-baseline"])
    workflow_types: list[str] = field(default_factory=lambda: ["auto"])
    active_tab: str = "overview"
    theme: str = "dark"
    language: str = "zh-CN"
    permission_mode: str = "ask"
    sandbox_mode: str = "read-only"
    context_limit_tokens: int = 120_000
    auto_compact_threshold: float = 0.82
    context_used_tokens: int = 0
    messages: list[ChatMessage] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    todo_status: dict[str, str] = field(
        default_factory=lambda: {
            "配置": "pending",
            "数据源": "pending",
            "模型": "pending",
            "运行": "pending",
        }
    )
    last_run_id: str = ""
    compacted_count: int = 0

    @property
    def context_ratio(self) -> float:
        if self.context_limit_tokens <= 0:
            return 0.0
        return min(1.0, self.context_used_tokens / self.context_limit_tokens)

    def add_message(self, role: str, content: str) -> bool:
        """Append a message and compact history if the context meter is high."""
        self.messages.append(ChatMessage(role=role, content=content))
        self.context_used_tokens += estimate_tokens(content)
        compacted = False
        if self.context_ratio >= self.auto_compact_threshold:
            self.compact_history(auto=True)
            compacted = True
        return compacted

    def add_user_input(self, content: str) -> list[str]:
        """Record user text and collect drag-to-terminal file paths."""
        self.add_message("user", content)
        found = extract_file_paths(content)
        for path in found:
            if path not in self.attachments:
                self.attachments.append(path)
        return found

    def compact_history(self, *, auto: bool = False) -> None:
        """Keep a small local summary and recent turns for long sessions."""
        if len(self.messages) <= 8:
            self.context_used_tokens = sum(estimate_tokens(message.content) for message in self.messages)
            return
        old_count = len(self.messages) - 8
        summary_prefix = "自动压缩" if auto else "手动压缩"
        summary = ChatMessage(
            role="system",
            content=(
                f"{summary_prefix}了 {old_count} 条较早 TUI 对话。"
                "后端运行结果、交易记录和 Agent 学习状态仍以 API/持久化存储为准。"
            ),
        )
        self.messages = [summary, *self.messages[-8:]]
        self.context_used_tokens = sum(estimate_tokens(message.content) for message in self.messages)
        self.compacted_count += old_count

    def set_models(self, models: list[str]) -> None:
        cleaned = [item.strip() for item in models if item.strip()]
        self.selected_models = cleaned or ["rule-baseline"]
        self.todo_status["模型"] = "completed"

    def set_workflow_types(self, workflow_types: list[str]) -> tuple[bool, str]:
        normalized = [_normalize_workflow_type(item) for item in workflow_types if item.strip()]
        if not normalized:
            return False, "至少选择一个工作流类型。"
        exclusive = {"auto", "daily"}
        if len(normalized) > 1 and exclusive.intersection(normalized):
            return False, "auto/daily 是独占工作流，不能和其他类型多选。"
        self.workflow_types = list(dict.fromkeys(normalized))
        return True, "工作流类型已更新。"


def _normalize_workflow_type(value: str) -> str:
    raw = value.strip()
    return WORKFLOW_ALIASES.get(raw, raw.lower())


def estimate_tokens(text: str) -> int:
    """Rough local context meter for status bars; backend prompts are separate."""
    return max(1, math.ceil(len(text) / 4))


def extract_file_paths(text: str) -> list[str]:
    """Extract existing absolute Windows paths from terminal-dragged text."""
    paths: list[str] = []
    for match in WINDOWS_PATH_PATTERN.finditer(text):
        raw_path = next((group for group in match.groups() if group), "")
        if not raw_path:
            continue
        candidate = Path(raw_path).expanduser()
        if candidate.exists():
            paths.append(str(candidate.resolve()))
    return list(dict.fromkeys(paths))


def is_sensitive_attachment_path(path: str) -> bool:
    """Return whether a dragged file should not be previewed in terminal output."""
    name = Path(path).name.lower()
    if name in SENSITIVE_ATTACHMENT_NAMES:
        return True
    return any(keyword in name for keyword in SENSITIVE_ATTACHMENT_KEYWORDS)


def read_attachment_previews(paths: list[str], *, max_chars: int = 1200) -> str:
    """Read small previews from user-dragged text files while avoiding secrets."""
    if not paths:
        return "暂无附件。"
    lines: list[str] = []
    for path in paths:
        if is_sensitive_attachment_path(path):
            lines.append(f"[{path}] 已拒绝预览：文件名疑似包含密钥或凭证。")
            continue
        candidate = Path(path)
        if not candidate.exists() or not candidate.is_file():
            lines.append(f"[{path}] 不存在或不是文件。")
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except OSError as exc:
            lines.append(f"[{path}] 读取失败：{exc}")
            continue
        lines.append(f"[{path}]\n{content}")
    return "\n\n".join(lines)
