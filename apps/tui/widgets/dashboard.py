"""Text render helpers for the TUI dashboard panes."""

from __future__ import annotations

from typing import Any

from apps.tui.session import TuiSessionState


def render_status_bar(state: TuiSessionState, run_status: dict[str, Any] | None = None) -> str:
    """Render the chat/status strip shown under the input area."""
    ratio = state.context_ratio
    filled = int(ratio * 20)
    context_bar = "█" * filled + "░" * (20 - filled)
    run_text = "unknown"
    if isinstance(run_status, dict):
        run_text = str(run_status.get("status", "unknown"))
        run = run_status.get("run")
        if isinstance(run, dict) and run.get("run_id"):
            run_text = f"{run_text}:{run.get('run_id')}"
    return (
        f"模型: {', '.join(state.selected_models)} | "
        f"工作流: {', '.join(state.workflow_types)} | "
        f"运行: {run_text} | "
        f"上下文: {context_bar} {ratio:.0%} | "
        f"权限: {state.permission_mode} | 沙盒: {state.sandbox_mode} | "
        f"主题: {state.theme} | 语言: {state.language} | 附件: {len(state.attachments)}"
    )


def render_todo_strip(state: TuiSessionState) -> str:
    """Render compact todo/progress chips for the left chat pane."""
    icons = {"pending": "○", "in_progress": "◐", "completed": "●", "failed": "×"}
    return " | ".join(f"{icons.get(status, '?')} {name}:{status}" for name, status in state.todo_status.items())


def render_provider_diagnostics(payload: dict[str, Any]) -> str:
    """Render data-source suitability and recent attempts for the right pane."""
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload, dict) else {}
    catalog = diagnostics.get("catalog", []) if isinstance(diagnostics, dict) else []
    attempts = diagnostics.get("attempts", []) if isinstance(diagnostics, dict) else []
    chain = diagnostics.get("provider_chain", []) if isinstance(diagnostics, dict) else []
    lines = ["数据源诊断", "=" * 40, f"模式: {diagnostics.get('mode', 'unknown') if isinstance(diagnostics, dict) else 'unknown'}"]
    lines.append(f"链路: {', '.join(chain) if isinstance(chain, list) else chain}")
    lines.append("\nProvider 适配矩阵:")
    for item in catalog if isinstance(catalog, list) else []:
        if not isinstance(item, dict):
            continue
        source = item.get("source", "")
        configured = "已配置" if item.get("configured") else "未配置"
        adapter = "adapter-ok" if item.get("adapter_available") else "adapter-none"
        credentials = "凭证-ok" if item.get("has_credentials") else f"缺凭证:{','.join(item.get('missing_credentials', []))}"
        capabilities = "/".join(str(value) for value in item.get("capabilities", []))
        lines.append(f"- {source}: {configured}, {adapter}, {credentials}, {capabilities}")
        if item.get("suitability"):
            lines.append(f"  适配: {item['suitability']}")
    lines.append("\n最近尝试:")
    if not attempts:
        lines.append("- 暂无；运行一次 /start 或调用 /providers 后会记录本进程尝试。")
    for attempt in attempts[-10:] if isinstance(attempts, list) else []:
        if isinstance(attempt, dict):
            lines.append(
                f"- {attempt.get('source')}::{attempt.get('operation')} "
                f"{attempt.get('status')} {attempt.get('detail', '')}"
            )
    return "\n".join(lines)


def render_rankings(payload: dict[str, Any]) -> str:
    """Render model leaderboard rows."""
    rows = payload.get("rankings", []) if isinstance(payload, dict) else []
    lines = ["模型排行榜", "=" * 40]
    if not rows:
        lines.append("暂无排行榜。先运行 /start --offline。")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"#{row.get('rank')} {row.get('llm_model')} | "
            f"收益 {float(row.get('total_return', 0.0) or 0.0):.2%} | "
            f"权益 {float(row.get('equity', 0.0) or 0.0):.2f} | "
            f"交易 {row.get('total_trades', 0)}"
        )
    return "\n".join(lines)


def render_stock_board(payload: dict[str, Any]) -> str:
    """Render holdings, candidates and trades in a terminal-friendly layout."""
    holdings = payload.get("holdings", []) if isinstance(payload, dict) else []
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    trades = payload.get("trades", []) if isinstance(payload, dict) else []
    lines = ["交易看板", "=" * 40, "持仓:"]
    if not holdings:
        lines.append("- 暂无持仓")
    for row in holdings[:10] if isinstance(holdings, list) else []:
        if isinstance(row, dict):
            lines.append(
                f"- {row.get('llm_model')} {row.get('stock_code')} "
                f"{row.get('shares')}股 市值={row.get('market_value')} 浮盈={row.get('unrealized_return')}"
            )
    lines.append("候选:")
    if not candidates:
        lines.append("- 暂无候选")
    for row in candidates[:10] if isinstance(candidates, list) else []:
        if isinstance(row, dict):
            lines.append(f"- {row.get('stock_code')} {row.get('stock_name')} {row.get('action')} score={row.get('score')}")
    lines.append("交易:")
    if not trades:
        lines.append("- 暂无交易")
    for row in trades[:10] if isinstance(trades, list) else []:
        if isinstance(row, dict):
            lines.append(f"- {row.get('date')} {row.get('llm_model')} {row.get('side')} {row.get('stock_code')} x{row.get('shares')}")
    return "\n".join(lines)


def render_decision_logs(payload: dict[str, Any]) -> str:
    """Render collapsible-like decision logs as nested text blocks."""
    items = payload.get("items", []) if isinstance(payload, dict) else []
    lines = ["决策日志", "=" * 40]
    if not items:
        lines.append("暂无决策日志。")
    for item in items[:8] if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(f"▸ {item.get('llm_model')} {item.get('stock_code')} {item.get('action')} conf={item.get('confidence')}")
        for reason in item.get("reasons", [])[:3]:
            lines.append(f"  - 理由: {reason}")
        for step in item.get("steps", [])[:4]:
            if isinstance(step, dict):
                lines.append(f"  ▹ {step.get('title')}: {step.get('summary')}")
    return "\n".join(lines)


def render_agent_flow(payload: dict[str, Any]) -> str:
    """Render the fixed multi-agent orchestration chain."""
    nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
    edges = payload.get("edges", []) if isinstance(payload, dict) else []
    labels: dict[str, str] = {}
    for node in nodes if isinstance(nodes, list) else []:
        if isinstance(node, dict):
            data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}
            labels[str(node.get("id", ""))] = str(data.get("label", node.get("id", "")))
    lines = ["Agent 编排", "=" * 40]
    for edge in edges if isinstance(edges, list) else []:
        if isinstance(edge, dict):
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            lines.append(f"{labels.get(source, source)} -> {labels.get(target, target)}")
    return "\n".join(lines)
