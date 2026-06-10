"""Plain-text market-data visualizations for the CLI agent runner."""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from typing import Any


def render_company_info(stock: Any, quote: Any | None = None, financial: Any | None = None) -> str:
    """Render a compact company/quote snapshot."""
    stock_data = _as_dict(stock)
    quote_data = _as_dict(quote)
    financial_data = _as_dict(financial)
    lines = [
        f"股票: {stock_data.get('stock_code', quote_data.get('stock_code', ''))} {stock_data.get('stock_name', quote_data.get('stock_name', ''))}",
        f"行业: {stock_data.get('sector', quote_data.get('sector', financial_data.get('sector', '')))}",
    ]
    if quote_data:
        lines.extend(
            [
                f"日期: {quote_data.get('date', '')}",
                f"现价: {_num(quote_data.get('price'))}  涨跌幅: {_pct(quote_data.get('change_pct'))}",
                f"成交量: {_num(quote_data.get('volume'), 0)}  成交额: {_money(quote_data.get('amount'))}",
            ]
        )
    if financial_data:
        lines.append(f"总市值: {_money(financial_data.get('market_cap'))}")
    return "\n".join(lines)


def render_financial_table(financial: Any) -> str:
    """Render key valuation and balance-sheet metrics."""
    data = _as_dict(financial)
    rows = [
        ("报告期", data.get("report_date", "")),
        ("PE TTM", _num(data.get("pe_ttm"))),
        ("PB", _num(data.get("pb"))),
        ("ROE", _pct(data.get("roe"))),
        ("资产负债率", _pct(data.get("debt_ratio"))),
        ("营收增速", _pct(data.get("revenue_growth"))),
        ("利润增速", _pct(data.get("profit_growth"))),
        ("总市值", _money(data.get("market_cap"))),
    ]
    width = max(len(name) for name, _ in rows)
    return "\n".join(f"{name:<{width}} : {value}" for name, value in rows)


def render_kline_ascii(bars: list[Any], max_points: int = 20, height: int = 10) -> str:
    """Render a small OHLC price chart using ASCII blocks."""
    rows = [_as_dict(bar) for bar in bars if _as_dict(bar)]
    rows = sorted(rows, key=lambda item: str(item.get("date", "")))[-max_points:]
    if not rows:
        return "K线: 无可用历史行情。"

    highs = [_float(item.get("high")) for item in rows]
    lows = [_float(item.get("low")) for item in rows]
    closes = [_float(item.get("close")) for item in rows]
    high = max(highs)
    low = min(lows)
    if high <= low:
        high = low + 1.0
    grid: list[str] = []
    for level in range(height, -1, -1):
        price = low + (high - low) * level / height
        chars = []
        for item in rows:
            o = _float(item.get("open"))
            c = _float(item.get("close"))
            h = _float(item.get("high"))
            l = _float(item.get("low"))
            body_low, body_high = sorted((o, c))
            if body_low <= price <= body_high:
                chars.append("█" if c >= o else "▓")
            elif l <= price <= h:
                chars.append("│")
            else:
                chars.append(" ")
        grid.append(f"{price:>8.2f} | {''.join(chars)}")
    first_date = str(rows[0].get("date", ""))
    last_date = str(rows[-1].get("date", ""))
    close_line = f"收盘: {', '.join(_num(value) for value in closes[-5:])}"
    return "\n".join([f"K线 {first_date} -> {last_date}", *grid, close_line])


def render_technical_indicators(bars: list[Any]) -> str:
    """Render objective technical indicators derived from bars."""
    rows = [_as_dict(bar) for bar in bars if _as_dict(bar)]
    rows = sorted(rows, key=lambda item: str(item.get("date", "")))
    closes = [_float(item.get("close")) for item in rows]
    if len(closes) < 2:
        return "技术指标: 历史K线不足。"
    ma5 = _mean(closes[-5:])
    ma20 = _mean(closes[-20:]) if len(closes) >= 20 else _mean(closes)
    rsi14 = _rsi(closes)
    return_5d = _pct_change(closes[-1], closes[-6]) if len(closes) >= 6 else _pct_change(closes[-1], closes[0])
    return_20d = _pct_change(closes[-1], closes[-21]) if len(closes) >= 21 else _pct_change(closes[-1], closes[0])
    volatility = _std([_pct_change(closes[index], closes[index - 1]) for index in range(1, len(closes))][-20:]) * math.sqrt(252)
    rows_text = [
        f"MA5: {_num(ma5)}",
        f"MA20: {_num(ma20)}",
        f"RSI14: {_num(rsi14)}",
        f"近5日收益: {_pct(return_5d)}",
        f"近20日收益: {_pct(return_20d)}",
        f"年化波动率: {_pct(volatility)}",
    ]
    return "\n".join(rows_text)


def render_news_list(news: Any, limit: int = 5) -> str:
    """Render a compact list of news/sentiment snippets."""
    if isinstance(news, str):
        text = news.strip()
        return text if text else "新闻/舆情: 暂无摘要。"
    if not isinstance(news, list) or not news:
        return "新闻/舆情: 暂无摘要。"
    lines = []
    for index, item in enumerate(news[:limit], 1):
        if isinstance(item, dict):
            title = item.get("title") or item.get("summary") or item.get("text") or ""
            source = item.get("source", "")
            date = item.get("date", "")
            lines.append(f"{index}. {date} {source} {title}".strip())
        else:
            lines.append(f"{index}. {item}")
    return "\n".join(lines)


def render_analysis_result(title: str, result: Any) -> str:
    """Render an AnalysisResult with objective metadata and reasons."""
    data = _as_dict(result)
    lines = [f"{title}: {data.get('label', '')}  评分={_pct(data.get('score'))}"]
    reasons = data.get("reasons") or []
    risks = data.get("risks") or []
    for item in reasons[:4]:
        lines.append(f"  + {item}")
    for item in risks[:4]:
        lines.append(f"  - {item}")
    metadata = data.get("metadata") or {}
    if metadata:
        keys = [key for key in metadata if key not in {"summary"}]
        if keys:
            lines.append("  元数据: " + ", ".join(f"{key}={metadata[key]}" for key in keys[:6]))
    return "\n".join(lines)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {}


def _float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _num(value: Any, digits: int = 2) -> str:
    return f"{_float(value):.{digits}f}"


def _money(value: Any) -> str:
    raw = _float(value)
    if abs(raw) >= 100_000_000:
        return f"{raw / 100_000_000:.2f}亿"
    if abs(raw) >= 10_000:
        return f"{raw / 10_000:.2f}万"
    return f"{raw:.2f}"


def _pct(value: Any) -> str:
    return f"{_float(value) * 100:.2f}%"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    return math.sqrt(sum((item - avg) ** 2 for item in values) / (len(values) - 1))


def _pct_change(current: float, previous: float) -> float:
    return 0.0 if previous == 0 else (current - previous) / previous


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    window = changes[-period:]
    gains = [change for change in window if change > 0]
    losses = [-change for change in window if change < 0]
    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
