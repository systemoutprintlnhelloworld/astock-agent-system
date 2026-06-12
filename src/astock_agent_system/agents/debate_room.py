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
    """Synthesize prior analyst outputs through a visible bull/bear/judge debate."""

    def analyze(
        self,
        stock_code: str,
        technical: AnalysisResult,
        fundamental: AnalysisResult,
        sentiment: AnalysisResult,
    ) -> AnalysisResult:
        inputs = [technical, fundamental, sentiment]
        agent_inputs = [
            {
                "agent": result.agent_name,
                "score": result.score,
                "label": result.label,
                "top_reasons": result.reasons[:3],
                "top_risks": result.risks[:3],
            }
            for result in inputs
        ]
        bull_points: list[str] = []
        bear_points: list[str] = []

        for result in inputs:
            prefix = f"{result.agent_name}({result.score:.2f}/{result.label})"
            if result.score >= 0.60:
                bull_points.extend([f"{prefix}: {item}" for item in result.reasons[:2]])
            else:
                bull_points.append(f"{prefix}: 未形成强看多证据")
            if result.score < 0.55:
                bear_points.extend([f"{prefix}: {item}" for item in (result.risks[:2] or ["评分偏低，需要复核"] )])
            else:
                bear_points.extend([f"{prefix}: {item}" for item in result.risks[:1]])

        score = round(_clamp(technical.score * 0.40 + fundamental.score * 0.35 + sentiment.score * 0.25), 4)
        if not bull_points:
            bull_points.append("未形成明显看多共识")
        if not bear_points:
            bear_points.append("未发现足以推翻交易假设的核心风险")

        discussion_rounds = [
            {"role": "主持人", "content": "收集技术、基本面、舆情三类 Agent 的评分、理由和风险。"},
            {"role": "多头", "content": "；".join(bull_points[:3])},
            {"role": "空头", "content": "；".join(bear_points[:3])},
            {"role": "评委", "content": f"按技术40%/基本面35%/舆情25%加权，得到 {score:.2f}，结论：{_label(score)}。"},
        ]

        return AnalysisResult(
            agent_name="DebateRoom",
            stock_code=stock_code,
            score=score,
            label=_label(score),
            reasons=[f"多头证据: {item}" for item in bull_points[:5]],
            risks=[f"空头质疑: {item}" for item in bear_points[:5]],
            metadata={
                "agent_inputs": agent_inputs,
                "bull_points": bull_points[:5],
                "bear_points": bear_points[:5],
                "judge": f"综合评分 {score:.2f}，结论：{_label(score)}",
                "discussion_rounds": discussion_rounds,
            },
        )
