"""Prompt-toolkit integration for command discovery, completion and history."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import CompleteStyle


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """One visible slash command or argument in the command palette."""

    token: str
    description: str
    children: tuple["CommandSpec", ...] = ()


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("/help", "查看全部命令和二级菜单"),
    CommandSpec("/status", "查看后端连接、运行状态和上下文占用"),
    CommandSpec("/run", "查看当前/最近一次自动投资运行观测视图"),
    CommandSpec(
        "/dashboard",
        "切换右侧交易看板；默认显示交易/持仓/盈亏",
        (
            CommandSpec("trading", "交易看板（默认）"),
            CommandSpec("run", "运行观测：状态、排行、持仓、交易、决策"),
            CommandSpec("rankings", "模型收益排行榜"),
            CommandSpec("decisions", "决策日志和理由"),
            CommandSpec("providers", "数据源诊断"),
            CommandSpec("flow", "固定多 Agent 编排链路"),
            CommandSpec("learning", "Agent Markdown 学习进度"),
            CommandSpec("status", "仅查看状态栏详情"),
        ),
    ),
    CommandSpec(
        "/models",
        "刷新/选择本轮比赛模型；比赛模型不属于初始化配置",
        (
            CommandSpec("list", "刷新后端模型列表"),
            CommandSpec("select", "用多选列表选择本轮比赛模型"),
            CommandSpec("set", "手动选择模型，如 /models set rule-baseline,gpt-5.5"),
            CommandSpec("selected", "查看当前已选择的比赛模型"),
        ),
    ),
    CommandSpec(
        "/start",
        "启动后台模拟盘轮次并自动切到运行观测视图",
        (
            CommandSpec("--offline", "使用离线样本数据运行"),
            CommandSpec("--models", "覆盖本轮比赛模型，如 --models a,b"),
            CommandSpec("--max-count", "候选股票数量"),
            CommandSpec("--days", "历史窗口天数"),
            CommandSpec("--foreground", "前台运行，等待任务完成"),
        ),
    ),
    CommandSpec("/providers", "查看数据源 provider chain 诊断"),
    CommandSpec("/config", "查看/检测配置", (CommandSpec("show", "查看脱敏配置"), CommandSpec("test-llm", "检测 LLM 配置"))),
    CommandSpec("/workflow", "选择工作流", (CommandSpec("auto", "自动模拟盘"), CommandSpec("offline", "离线运行"), CommandSpec("online", "在线运行"), CommandSpec("review", "复盘"))),
    CommandSpec("/agent", "管理 Agent Markdown", (CommandSpec("list", "列出 Agent"), CommandSpec("view", "查看 Agent 指令"), CommandSpec("learning", "学习状态/建议"))),
    CommandSpec("/compact", "手动压缩本地 TUI 对话上下文"),
    CommandSpec("/permission", "设置权限模式", (CommandSpec("ask", "每次询问"), CommandSpec("auto", "自动允许低风险"), CommandSpec("deny", "拒绝敏感操作"))),
    CommandSpec("/sandbox", "设置沙盒模式", (CommandSpec("read-only", "只读"), CommandSpec("workspace-write", "允许工作区写入"))),
    CommandSpec("/theme", "切换主题", (CommandSpec("dark", "深色"), CommandSpec("light", "浅色"))),
    CommandSpec("/lang", "切换语言", (CommandSpec("zh-CN", "中文"), CommandSpec("en-US", "English"))),
    CommandSpec("/attachments", "查看拖入终端的附件", (CommandSpec("show", "预览安全附件"), CommandSpec("preview", "预览安全附件"))),
    CommandSpec("/history", "查看本地 TUI 对话历史"),
    CommandSpec("/memory", "查看本地 TUI 对话历史"),
    CommandSpec("/exit", "结束 TUI；不会强制中断后端后台任务"),
)


def command_help_lines() -> list[str]:
    """Return command help lines shared by /help and prompt completion."""
    lines: list[str] = []
    for spec in COMMAND_SPECS:
        lines.append(f"{spec.token} - {spec.description}")
        if spec.children:
            child_text = " | ".join(f"{child.token}: {child.description}" for child in spec.children)
            lines.append(f"  {child_text}")
    return lines


def _spec_map() -> dict[str, CommandSpec]:
    return {spec.token: spec for spec in COMMAND_SPECS}


class SlashCommandCompleter(Completer):
    """Completion menu that appears as soon as users type slash commands."""

    def __init__(self, available_models: list[str] | None = None) -> None:
        self.available_models = available_models if available_models is not None else []
        self.commands = _spec_map()

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Generate completions for the current input."""
        text = document.text_before_cursor
        words = text.split()
        
        if not text.startswith("/"):
            return

        if not words or text == "/":
            start_position = -len(text) if text else 0
            for spec in COMMAND_SPECS:
                yield Completion(spec.token, start_position=start_position, display=spec.token, display_meta=spec.description)
            return
        
        if len(words) == 1 and not text.endswith(" "):
            prefix = words[0].lower()
            for spec in COMMAND_SPECS:
                if spec.token.startswith(prefix):
                    yield Completion(spec.token, start_position=-len(prefix), display=spec.token, display_meta=spec.description)
            return
        
        if len(words) >= 1:
            cmd = words[0].lower()
            spec = self.commands.get(cmd)
            if spec is None:
                return

            candidates = list(spec.children)
            if cmd in {"/models", "/start"} and ("set" in words or "--models" in words):
                candidates.extend(CommandSpec(model, "后端模型列表") for model in self.available_models)
            if not candidates:
                return

            prefix = "" if text.endswith(" ") else words[-1].lower()
            start_position = 0 if text.endswith(" ") else -len(prefix)
            for child in candidates:
                if not prefix or child.token.lower().startswith(prefix):
                    yield Completion(child.token, start_position=start_position, display=child.token, display_meta=child.description)


def create_prompt_session(history_file: Path | None = None, *, available_models: list[str] | None = None) -> PromptSession[str]:
    """Create a prompt_toolkit session with history and completion."""
    if history_file is None:
        history_file = Path("data/runtime/tui_history.txt")
    
    history_file.parent.mkdir(parents=True, exist_ok=True)
    
    return PromptSession(
        history=FileHistory(str(history_file)),
        completer=SlashCommandCompleter(available_models=available_models),
        complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN,
        enable_history_search=True,
        reserve_space_for_menu=10,
        bottom_toolbar=" 输入 / 显示命令列表；继续输入可过滤；Tab 接受补全；↑↓ 历史；Ctrl+R 搜索历史 ",
    )
