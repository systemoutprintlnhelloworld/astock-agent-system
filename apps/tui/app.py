"""Minimal terminal client for the shared AStock backend.

This is intentionally dependency-light so users can test the workflow in a
plain Windows terminal before a richer Textual shell is added.  The investment
logic still lives in FastAPI/Python core; this module only renders and dispatches
commands.
"""

from __future__ import annotations

import argparse
import shutil
import textwrap
from pathlib import Path
from typing import Iterable

from rich.console import Console

from apps.tui.backend_client import AStockBackendClient, BackendClientError
from apps.tui.commands import handle_slash_command
from apps.tui.config_wizard import build_config_patch, render_wizard_summary, run_interactive_wizard
from apps.tui.prompt import create_prompt_session
from apps.tui.session import TuiSessionState
from apps.tui.widgets import render_provider_diagnostics, render_rankings, render_status_bar, render_todo_strip

console = Console()


def run_tui(argv: list[str] | None = None) -> int:
    """Run the interactive terminal UI."""
    args = _build_parser().parse_args(argv)
    state = TuiSessionState(backend_url=args.backend_url)
    client = AStockBackendClient(base_url=args.backend_url, timeout_seconds=args.timeout)

    _print_header(state)
    if not _check_backend(client):
        return 2

    if not args.skip_wizard:
        _run_config_wizard(client, state)

    _render_home(client, state)
    
    # Try to create prompt_toolkit session, fallback to plain input if not TTY
    try:
        history_file = Path("data/runtime/tui_history.txt")
        session = create_prompt_session(history_file)
        console.print(f"\n[dim]💡 使用 Tab 键补全命令，↑↓ 浏览历史，Ctrl+R 搜索历史[/dim]")
        use_prompt_toolkit = True
    except Exception:
        console.print(f"\n[dim]💡 运行在非 TTY 环境，使用简化输入模式[/dim]")
        session = None
        use_prompt_toolkit = False
    
    while True:
        try:
            if use_prompt_toolkit and session is not None:
                raw = session.prompt("\nastock> ").strip()
            else:
                raw = input("\nastock> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]输入 /exit 可结束 TUI；本次收到终端中断，TUI 已退出。[/yellow]")
            return 0
        
        if not raw:
            continue
        
        attachments = state.add_user_input(raw)
        if attachments:
            console.print(f"[cyan]已识别附件路径: {', '.join(attachments)}[/cyan]")
        
        if raw.startswith("/"):
            result = handle_slash_command(raw, state=state, client=client)
            if result.title == "EXIT":
                console.print(f"[green]{result.body}[/green]")
                return 0
            _print_result(result.title, result.body, ok=result.ok)
            continue
        
        response = _handle_plain_language(raw)
        state.add_message("assistant", response)
        _print_result("自然语言已记录", response, ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AStock terminal UI client.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:18080", help="Shared FastAPI backend base URL")
    parser.add_argument("--timeout", type=float, default=30.0, help="Backend request timeout in seconds")
    parser.add_argument("--skip-wizard", action="store_true", help="Skip first-run configuration prompts")
    return parser


def _check_backend(client: AStockBackendClient) -> bool:
    try:
        health = client.health()
    except BackendClientError as exc:
        print(f"后端不可达: {exc}")
        print("请先运行: .\\start.bat -Mode backend -Port 18080")
        return False
    print(f"Backend connected: {health.get('app', '')} {health.get('status', '')}")
    return True


def _run_config_wizard(client: AStockBackendClient, state: TuiSessionState) -> None:
    answers = run_interactive_wizard()
    if not answers:
        console.print("[yellow]配置向导已跳过。可稍后用 /config 命令更新配置。[/yellow]")
        return
    
    patch = build_config_patch(answers)
    render_wizard_summary(patch)
    
    from InquirerPy import inquirer
    confirm = inquirer.confirm(
        message="保存上述配置？",
        default=True,
    ).execute()
    
    if confirm:
        client.save_config(patch)
        state.todo_status["配置"] = "completed"
        data_patch = patch.get("data", {}) if isinstance(patch.get("data"), dict) else {}
        if data_patch.get("provider_chain"):
            state.todo_status["数据源"] = "completed"
        scheduler_patch = patch.get("scheduler", {}) if isinstance(patch.get("scheduler"), dict) else {}
        models = scheduler_patch.get("models")
        if isinstance(models, list):
            state.set_models([str(item) for item in models])
        console.print("[green]✓ 配置已保存。[/green]")
    else:
        console.print("[yellow]配置未保存。[/yellow]")


def _render_home(client: AStockBackendClient, state: TuiSessionState) -> None:
    try:
        run_status = client.run_status()
        providers = client.data_providers()
        rankings = client.rankings()
    except BackendClientError as exc:
        _print_result("启动诊断失败", str(exc), ok=False)
        return
    left = [
        "对话流 / Slash 命令",
        "=" * 28,
        "/help 查看命令",
        "/start --offline 提交后台模拟盘轮次",
        "/dashboard providers 查看数据源",
        "/agent learning stats 查看学习进度",
        "",
        render_todo_strip(state),
        render_status_bar(state, run_status),
    ]
    right = [
        render_rankings(rankings),
        "",
        render_provider_diagnostics(providers),
    ]
    _print_split("\n".join(left), "\n".join(right))


def _print_header(state: TuiSessionState) -> None:
    width = shutil.get_terminal_size((120, 32)).columns
    print("=" * width)
    print("AStock TUI - 多 Agent 模拟盘终端客户端")
    print("GUI/TUI 共用 FastAPI 后端；当前只做模拟盘，不会真实下单。")
    print(f"Backend: {state.backend_url}")
    print("=" * width)


def _print_result(title: str, body: str, *, ok: bool) -> None:
    prefix = "OK" if ok else "ERR"
    print(f"\n[{prefix}] {title}")
    print("-" * max(20, min(80, len(title) + 8)))
    print(body)


def _print_split(left: str, right: str) -> None:
    width = shutil.get_terminal_size((120, 32)).columns
    left_width = max(24, int(width * 0.20))
    right_width = max(40, width - left_width - 3)
    left_lines = _wrap_lines(left, left_width)
    right_lines = _wrap_lines(right, right_width)
    total = max(len(left_lines), len(right_lines))
    print()
    for index in range(total):
        left_text = left_lines[index] if index < len(left_lines) else ""
        right_text = right_lines[index] if index < len(right_lines) else ""
        print(f"{left_text:<{left_width}} │ {right_text}")


def _wrap_lines(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if not raw_line:
            lines.append("")
            continue
        wrapped = textwrap.wrap(raw_line, width=width, replace_whitespace=False, drop_whitespace=False)
        lines.extend(wrapped or [raw_line[:width]])
    return lines


def _handle_plain_language(text: str) -> str:
    suggestions = list(_plain_language_suggestions(text))
    if not suggestions:
        suggestions = ["当前轻量 TUI 已记录你的自然语言说明；执行动作请使用 /help 中的 slash 命令。"]
    return "\n".join(f"- {item}" for item in suggestions)


def _plain_language_suggestions(text: str) -> Iterable[str]:
    lowered = text.lower()
    if any(token in lowered for token in ["开始", "运行", "start", "run"]):
        yield "如要启动模拟盘轮次，输入 /start --offline --max-count 1 --days 12。"
    if any(token in lowered for token in ["模型", "model"]):
        yield "如要刷新模型列表，输入 /models；如要选择模型，输入 /models set rule-baseline,gpt-5.4-mini。"
    if any(token in lowered for token in ["数据", "akshare", "baostock", "openbb", "yfinance", "jqdata", "同花顺"]):
        yield "如要查看数据源适配和凭证状态，输入 /providers。"
    if any(token in lowered for token in ["配置", "设置", "config"]):
        yield "如要查看脱敏配置，输入 /config show；LLM 检测输入 /config test-llm。"


if __name__ == "__main__":
    raise SystemExit(run_tui())
