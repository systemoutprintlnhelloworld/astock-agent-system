"""Risk manager with conservative one-vote veto rules."""

from __future__ import annotations

from astock_agent_system.config import Settings, load_settings
from astock_agent_system.models import AnalysisResult, RiskProfile, StockQuote


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


class RiskManager:
    """Apply liquidity, volatility, sentiment and position-limit checks."""

    def __init__(self, settings: Settings | None = None, risk_profile: RiskProfile | None = None) -> None:
        self.settings = settings or load_settings()
        self.risk_profile = risk_profile or RiskProfile(
            max_position_per_stock=self.settings.risk.max_position_per_stock,
            max_total_position=self.settings.risk.max_total_position,
            stop_loss_pct=self.settings.risk.stop_loss_pct,
            max_volatility=self.settings.risk.max_volatility,
            min_turnover=self.settings.risk.min_turnover,
        )

    def analyze(
        self,
        stock_code: str,
        quote: StockQuote,
        technical: AnalysisResult,
        fundamental: AnalysisResult,
        sentiment: AnalysisResult,
        current_total_position: float = 0.0,
    ) -> AnalysisResult:
        reasons: list[str] = []
        risks: list[str] = []
        hard_veto = False

        volatility = float(technical.metadata.get("volatility", 0.0) or 0.0)
        if quote.amount < self.risk_profile.min_turnover:
            hard_veto = True
            risks.append(f"成交额 {quote.amount:.0f} 低于阈值 {self.risk_profile.min_turnover:.0f}")
        else:
            reasons.append("流动性满足最低阈值")

        if volatility > self.risk_profile.max_volatility:
            hard_veto = True
            risks.append(f"年化波动率 {volatility:.2%} 超过阈值 {self.risk_profile.max_volatility:.2%}")
        else:
            reasons.append("波动率处于风控阈值内")

        if sentiment.score < 0.25:
            hard_veto = True
            risks.append("舆情显著偏负面，触发一票否决")
        if fundamental.score < 0.25:
            hard_veto = True
            risks.append("基本面评分过低，触发一票否决")
        if current_total_position >= self.risk_profile.max_total_position:
            hard_veto = True
            risks.append("总仓位已达到或超过上限")

        combined_quality = technical.score * 0.35 + fundamental.score * 0.35 + sentiment.score * 0.30
        remaining_total_cap = max(0.0, self.risk_profile.max_total_position - current_total_position)
        suggested_position_cap = min(self.risk_profile.max_position_per_stock, remaining_total_cap)
        approved = not hard_veto and suggested_position_cap > 0
        score = 0.0 if hard_veto else _clamp(combined_quality)

        if approved:
            reasons.append(f"单股建议仓位上限 {suggested_position_cap:.1%}")

        return AnalysisResult(
            agent_name="RiskManager",
            stock_code=stock_code,
            score=round(score, 4),
            label="通过" if approved else "拒绝",
            reasons=reasons,
            risks=risks,
            metadata={
                "approved": approved,
                "hard_veto": hard_veto,
                "suggested_position_cap": round(suggested_position_cap, 6),
                "risk_profile": self.risk_profile.to_dict(),
                "current_total_position": current_total_position,
                "volatility": volatility,
            },
        )
