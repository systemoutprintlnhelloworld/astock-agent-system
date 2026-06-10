"""Portfolio decision agent for producing paper-trading instructions."""

from __future__ import annotations

from astock_agent_system.config import Settings, load_settings
from astock_agent_system.models import AnalysisResult, StockQuote, TradeDecision


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


class PortfolioManager:
    """Convert analysis and risk approval into BUY/HOLD/SELL/REJECT decisions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def decide(
        self,
        stock_code: str,
        quote: StockQuote,
        technical: AnalysisResult,
        fundamental: AnalysisResult,
        sentiment: AnalysisResult,
        debate: AnalysisResult,
        risk: AnalysisResult,
    ) -> TradeDecision:
        approved = bool(risk.metadata.get("approved", False))
        if not approved:
            return TradeDecision(
                stock_code=stock_code,
                action="REJECT",
                confidence=1.0,
                position_size=0.0,
                target_price=None,
                stop_loss=None,
                reasons=["Risk Manager 未通过，组合层拒绝交易"],
                risk_notes=risk.risks,
                explanation_data=_explanation_plan(
                    action="REJECT",
                    technical=technical,
                    fundamental=fundamental,
                    sentiment=sentiment,
                    debate=debate,
                    risk=risk,
                ),
                metadata={"risk": risk.to_dict()},
            )

        combined_score = _clamp(
            technical.score * 0.30 + fundamental.score * 0.25 + sentiment.score * 0.20 + debate.score * 0.25
        )
        confidence = round(_clamp(0.50 + abs(combined_score - 0.50)), 4)
        position_cap = float(risk.metadata.get("suggested_position_cap", self.settings.risk.max_position_per_stock) or 0.0)

        if combined_score >= 0.68:
            action = "BUY"
            position_size = min(position_cap, self.settings.risk.max_position_per_stock) * confidence
            target_price = quote.price * (1.0 + max(0.03, min(0.12, combined_score * 0.12)))
            stop_loss = quote.price * (1.0 - self.settings.risk.stop_loss_pct)
            reasons = ["多维评分达到买入阈值", *debate.reasons[:3]]
        elif combined_score >= 0.45:
            action = "HOLD"
            position_size = 0.0
            target_price = quote.price * 1.03
            stop_loss = quote.price * (1.0 - self.settings.risk.stop_loss_pct)
            reasons = ["综合评分未达到买入阈值，建议观察", *debate.reasons[:2]]
        else:
            action = "SELL"
            position_size = 0.0
            target_price = quote.price
            stop_loss = quote.price * (1.0 - self.settings.risk.stop_loss_pct)
            reasons = ["综合评分偏低，模拟盘应降低或避免暴露"]

        return TradeDecision(
            stock_code=stock_code,
            action=action,
            confidence=confidence,
            position_size=round(position_size, 6),
            target_price=round(target_price, 4) if target_price is not None else None,
            stop_loss=round(stop_loss, 4) if stop_loss is not None else None,
            reasons=reasons,
            risk_notes=risk.risks + debate.risks[:3],
            explanation_data=_explanation_plan(
                action=action,
                technical=technical,
                fundamental=fundamental,
                sentiment=sentiment,
                debate=debate,
                risk=risk,
            ),
            metadata={
                "combined_score": round(combined_score, 4),
                "risk_score": risk.score,
                "position_cap": round(position_cap, 6),
            },
        )


def _explanation_plan(
    *,
    action: str,
    technical: AnalysisResult,
    fundamental: AnalysisResult,
    sentiment: AnalysisResult,
    debate: AnalysisResult,
    risk: AnalysisResult,
) -> dict[str, Any]:
    """Choose objective data blocks that best explain the decision."""
    sections = ["company", "quote", "decision"]
    highlights: list[str] = []
    if technical.score >= 0.60 or technical.score <= 0.40 or action in {"BUY", "SELL"}:
        sections.extend(["kline", "technical_indicators"])
        highlights.append("技术面是本次决策的关键输入，展示K线和均线/RSI等客观指标。")
    if fundamental.score >= 0.60 or fundamental.score <= 0.40 or action in {"BUY", "REJECT"}:
        sections.append("financial")
        highlights.append("基本面或估值影响较大，展示PE/PB/ROE/负债率等财务数据。")
    if sentiment.score != 0.50 or sentiment.risks or sentiment.reasons:
        sections.append("sentiment")
        highlights.append("舆情模块有可解释输入，展示新闻/舆情摘要。")
    if risk.risks or not bool(risk.metadata.get("approved", False)):
        sections.append("risk")
        highlights.append("风控影响最终动作，展示风控约束和否决/限仓原因。")
    sections.append("agent_chain")
    return {
        "sections": list(dict.fromkeys(sections)),
        "highlights": highlights,
        "agent_scores": {
            "technical": round(technical.score, 4),
            "fundamental": round(fundamental.score, 4),
            "sentiment": round(sentiment.score, 4),
            "debate": round(debate.score, 4),
            "risk": round(risk.score, 4),
        },
    }
