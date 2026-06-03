"""Report persistence helpers for JSON and Markdown outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT
from astock_agent_system.models import AnalysisResult, DailyRunReport, StockAnalysisReport, TradeDecision


def save_stock_report(report: StockAnalysisReport, output_dir: str | Path = "reports") -> dict[str, str]:
    """Save one stock report as JSON and Markdown."""
    directory = _resolve_output_dir(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{report.stock.stock_code}_{report.stock.stock_name}"
    json_path = directory / f"{stem}.json"
    md_path = directory / f"{stem}.md"
    _write_json(json_path, report.to_dict())
    md_path.write_text(stock_report_to_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def save_daily_report(report: DailyRunReport, output_dir: str | Path = "reports") -> dict[str, Any]:
    """Save daily summary plus individual stock reports under reports/YYYYMMDD."""
    day_dir = _resolve_output_dir(output_dir) / report.run_date.replace("-", "")
    day_dir.mkdir(parents=True, exist_ok=True)
    daily_json = day_dir / "daily_report.json"
    daily_md = day_dir / "daily_report.md"
    _write_json(daily_json, report.to_dict())
    daily_md.write_text(daily_report_to_markdown(report), encoding="utf-8")
    stock_files = [save_stock_report(item, day_dir) for item in report.reports]
    return {
        "daily_json": str(daily_json),
        "daily_markdown": str(daily_md),
        "stock_reports": stock_files,
    }


def stock_report_to_markdown(report: StockAnalysisReport) -> str:
    decision = report.decision
    lines = [
        f"# {report.stock.stock_name} ({report.stock.stock_code}) 分析报告",
        "",
        "## 行情",
        f"- 日期：{report.quote.date}",
        f"- 最新价：{report.quote.price}",
        f"- 涨跌幅：{report.quote.change_pct:.2%}",
        f"- 成交额：{report.quote.amount:,.0f}",
        "",
        "## 最终决策",
        _decision_to_markdown(decision),
        "",
        "## Agent 结果",
    ]
    for result in [report.technical, report.fundamental, report.sentiment, report.debate, report.risk]:
        if result is not None:
            lines.extend(_analysis_to_markdown(result))
    lines.extend(
        [
            "",
            "## 免责声明",
            "本报告由模拟盘研究系统自动生成，仅用于学习与研究，不构成投资建议。",
        ]
    )
    return "\n".join(lines) + "\n"


def daily_report_to_markdown(report: DailyRunReport) -> str:
    lines = [
        f"# 每日 A股 Agent 分析报告 - {report.run_date}",
        "",
        f"- 候选数量：{len(report.candidates)}",
        f"- 完成分析：{len(report.reports)}",
        f"- 数据模式：{report.metadata.get('data_mode', '')}",
        "",
        "## 决策摘要",
        "| 股票 | 行业 | 动作 | 置信度 | 仓位 | 目标价 | 止损价 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in report.reports:
        decision = item.decision
        if decision is None:
            continue
        lines.append(
            "| {name}({code}) | {sector} | {action} | {confidence:.2%} | {position:.2%} | {target} | {stop} |".format(
                name=item.stock.stock_name,
                code=item.stock.stock_code,
                sector=item.stock.sector,
                action=decision.action,
                confidence=decision.confidence,
                position=decision.position_size,
                target="" if decision.target_price is None else f"{decision.target_price:.2f}",
                stop="" if decision.stop_loss is None else f"{decision.stop_loss:.2f}",
            )
        )
    lines.extend(["", "## 风险提示", "模拟盘报告不构成任何投资建议。"])
    return "\n".join(lines) + "\n"


def _analysis_to_markdown(result: AnalysisResult) -> list[str]:
    lines = ["", f"### {result.agent_name} - {result.label} ({result.score:.2f})"]
    if result.reasons:
        lines.append("**理由：**")
        lines.extend(f"- {item}" for item in result.reasons)
    if result.risks:
        lines.append("**风险：**")
        lines.extend(f"- {item}" for item in result.risks)
    return lines


def _decision_to_markdown(decision: TradeDecision | None) -> str:
    if decision is None:
        return "- 暂无决策"
    lines = [
        f"- 动作：{decision.action}",
        f"- 置信度：{decision.confidence:.2%}",
        f"- 建议仓位：{decision.position_size:.2%}",
        f"- 目标价：{decision.target_price if decision.target_price is not None else ''}",
        f"- 止损价：{decision.stop_loss if decision.stop_loss is not None else ''}",
    ]
    lines.extend(f"- 理由：{item}" for item in decision.reasons)
    lines.extend(f"- 风险：{item}" for item in decision.risk_notes)
    return "\n".join(lines)


def _resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
