"""Pure-Python technical analysis agent."""

from __future__ import annotations

import math

from astock_agent_system.models import AnalysisResult, StockBar


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((item - avg) ** 2 for item in values) / (len(values) - 1)
    return math.sqrt(variance)


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    window = changes[-period:]
    gains = [change for change in window if change > 0]
    losses = [-change for change in window if change < 0]
    average_gain = _mean(gains) if gains else 0.0
    average_loss = _mean(losses) if losses else 0.0
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _label(score: float) -> str:
    if score >= 0.75:
        return "强势"
    if score >= 0.60:
        return "偏强"
    if score >= 0.40:
        return "中性"
    return "偏弱"


class TechnicalAnalyst:
    """Score price trend, momentum, RSI and volatility without pandas."""

    def analyze(self, stock_code: str, bars: list[StockBar]) -> AnalysisResult:
        if len(bars) < 5:
            return AnalysisResult(
                agent_name="TechnicalAnalyst",
                stock_code=stock_code,
                score=0.0,
                label="数据不足",
                risks=["历史K线少于5条，无法进行稳定技术分析"],
            )

        ordered = sorted(bars, key=lambda bar: bar.date)
        closes = [bar.close for bar in ordered]
        returns = [_pct_change(closes[index], closes[index - 1]) for index in range(1, len(closes))]
        latest_close = closes[-1]
        ma5 = _mean(closes[-5:])
        ma20 = _mean(closes[-20:]) if len(closes) >= 20 else _mean(closes)
        return_5d = _pct_change(closes[-1], closes[-6]) if len(closes) >= 6 else 0.0
        return_20d = _pct_change(closes[-1], closes[-21]) if len(closes) >= 21 else _pct_change(closes[-1], closes[0])
        volatility = _std(returns[-20:]) * math.sqrt(252) if returns else 0.0
        rsi14 = _rsi(closes, 14)

        score = 0.50
        reasons: list[str] = []
        risks: list[str] = []

        if ma5 > ma20:
            score += 0.16
            reasons.append("MA5 高于 MA20，短期趋势占优")
        else:
            score -= 0.12
            risks.append("MA5 不高于 MA20，短期趋势偏弱")

        if latest_close > ma20:
            score += 0.10
            reasons.append("收盘价站上 MA20")
        else:
            score -= 0.08
            risks.append("收盘价低于 MA20")

        if return_20d > 0:
            momentum_bonus = min(0.16, return_20d * 1.8)
            score += momentum_bonus
            reasons.append(f"近20日收益为 {return_20d:.2%}")
        else:
            score += max(-0.16, return_20d * 1.5)
            risks.append(f"近20日收益为 {return_20d:.2%}")

        if 45 <= rsi14 <= 70:
            score += 0.08
            reasons.append(f"RSI14={rsi14:.1f}，动量处于相对健康区间")
        elif rsi14 > 80:
            score -= 0.10
            risks.append(f"RSI14={rsi14:.1f}，短线过热")
        elif rsi14 < 30:
            score -= 0.04
            risks.append(f"RSI14={rsi14:.1f}，弱势或超跌状态")

        if volatility <= 0.35:
            score += 0.06
            reasons.append(f"年化波动率约 {volatility:.2%}，在保守阈值内")
        else:
            score -= 0.12
            risks.append(f"年化波动率约 {volatility:.2%}，超过保守阈值")

        final_score = round(_clamp(score), 4)
        return AnalysisResult(
            agent_name="TechnicalAnalyst",
            stock_code=stock_code,
            score=final_score,
            label=_label(final_score),
            reasons=reasons,
            risks=risks,
            metadata={
                "latest_close": latest_close,
                "ma5": round(ma5, 4),
                "ma20": round(ma20, 4),
                "return_5d": round(return_5d, 6),
                "return_20d": round(return_20d, 6),
                "rsi14": round(rsi14, 2),
                "volatility": round(volatility, 6),
            },
        )
