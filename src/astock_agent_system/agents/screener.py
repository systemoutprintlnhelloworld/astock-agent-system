"""Dynamic stock screening based on data, technical and fundamental scores."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from astock_agent_system.agents.fundamental_analyst import FundamentalAnalyst
from astock_agent_system.agents.technical_analyst import TechnicalAnalyst
from astock_agent_system.data import DataAgent
from astock_agent_system.models import AnalysisResult, StockIdentity


@dataclass(slots=True)
class ScreenedStock:
    stock: StockIdentity
    score: float
    technical: AnalysisResult
    fundamental: AnalysisResult
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StockScreener:
    """Rank the universe with explainable offline-friendly rules."""

    def __init__(
        self,
        data_agent: DataAgent | None = None,
        technical_analyst: TechnicalAnalyst | None = None,
        fundamental_analyst: FundamentalAnalyst | None = None,
    ) -> None:
        self.data_agent = data_agent or DataAgent()
        self.technical_analyst = technical_analyst or TechnicalAnalyst()
        self.fundamental_analyst = fundamental_analyst or FundamentalAnalyst()

    def screen(self, max_count: int = 10, history_days: int = 24) -> list[ScreenedStock]:
        candidates: list[ScreenedStock] = []
        min_turnover = self.data_agent.settings.risk.min_turnover
        for stock in self.data_agent.get_universe():
            bars = self.data_agent.get_history(stock.stock_code, days=history_days)
            financial = self.data_agent.get_financial(stock.stock_code)
            quote = self.data_agent.get_quote(stock.stock_code)
            technical = self.technical_analyst.analyze(stock.stock_code, bars)
            fundamental = self.fundamental_analyst.analyze(financial)

            liquidity_score = min(1.0, quote.amount / min_turnover) if min_turnover > 0 else 1.0
            combined_score = round(
                (technical.score * 0.45) + (fundamental.score * 0.35) + (liquidity_score * 0.20),
                4,
            )
            reasons = [
                f"技术评分 {technical.score:.2f}（{technical.label}）",
                f"基本面评分 {fundamental.score:.2f}（{fundamental.label}）",
            ]
            if liquidity_score >= 1.0:
                reasons.append("成交额满足流动性阈值")
            risks = list(technical.risks[:2]) + list(fundamental.risks[:2])
            if liquidity_score < 1.0:
                risks.append("成交额低于流动性阈值")

            candidates.append(
                ScreenedStock(
                    stock=stock,
                    score=combined_score,
                    technical=technical,
                    fundamental=fundamental,
                    reasons=reasons,
                    risks=risks,
                    metrics={
                        "latest_price": quote.price,
                        "change_pct": quote.change_pct,
                        "amount": quote.amount,
                        "liquidity_score": round(liquidity_score, 4),
                        "return_20d": technical.metadata.get("return_20d", 0.0),
                        "volatility": technical.metadata.get("volatility", 0.0),
                        "pe_ttm": financial.pe_ttm,
                        "roe": financial.roe,
                    },
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: max(0, max_count)]
