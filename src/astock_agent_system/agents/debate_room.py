"""Bull/bear debate agent for balancing analysis signals."""

from __future__ import annotations

from astock_agent_system.models import AnalysisResult


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _label(score: float) -> str:
    if score >= 0.72:
        return "看多"
    if score >= 0.58:
        return "谨慎看多"
    if score >= 0.42:
        return "中性"
    return "偏空"


class DebateRoom:
    """Create a lightweight bull/bear/judge synthesis from prior agents."""

    def analyze(
        self,
        stock_code: str,
        technical: AnalysisResult,
        fundamental: AnalysisResult,
        sentiment: AnalysisResult,
    ) -> AnalysisResult:
        bull_points: list[str] = []
        bear_points: list[str] = []

        for result in (technical, fundamental, sentiment):
            if result.score >= 0.60:
                bull_points.extend(result.reasons[:2])
            if result.score < 0.55:
                bear_points.extend(result.risks[:2] or [f"{result.agent_name} 评分偏低：{result.score:.2f}"])
            else:
                bear_points.extend(result.risks[:1])

        score = round(_clamp(technical.score * 0.40 + fundamental.score * 0.35 + sentiment.score * 0.25), 4)
        if not bull_points:
            bull_points.append("未形成明显看多共识")
        if not bear_points:
            bear_points.append("未发现足以推翻交易假设的核心风险")

        return AnalysisResult(
            agent_name="DebateRoom",
            stock_code=stock_code,
            score=score,
            label=_label(score),
            reasons=[f"Bull: {item}" for item in bull_points[:5]],
            risks=[f"Bear: {item}" for item in bear_points[:5]],
            metadata={
                "bull_points": bull_points[:5],
                "bear_points": bear_points[:5],
                "judge": f"综合评分 {score:.2f}，结论：{_label(score)}",
            },
        )
