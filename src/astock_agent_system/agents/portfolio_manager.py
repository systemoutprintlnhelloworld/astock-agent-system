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
            metadata={
                "combined_score": round(combined_score, 4),
                "risk_score": risk.score,
                "position_cap": round(position_cap, 6),
            },
        )
