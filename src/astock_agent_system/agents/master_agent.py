"""Master orchestration agent for the daily investment workflow."""

from __future__ import annotations

from datetime import datetime

from astock_agent_system.agents.debate_room import DebateRoom
from astock_agent_system.agents.fundamental_analyst import FundamentalAnalyst
from astock_agent_system.agents.portfolio_manager import PortfolioManager
from astock_agent_system.agents.risk_manager import RiskManager
from astock_agent_system.agents.screener import StockScreener
from astock_agent_system.agents.sentiment_analyst import SentimentAnalyst
from astock_agent_system.agents.technical_analyst import TechnicalAnalyst
from astock_agent_system.config import Settings, load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.models import DailyRunReport, StockAnalysisReport, StockIdentity


class MasterAgent:
    """Run the explicit MVP workflow before optional LangGraph integration."""

    def __init__(self, settings: Settings | None = None, data_agent: DataAgent | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_agent = data_agent or DataAgent(settings=self.settings)
        self.technical_analyst = TechnicalAnalyst()
        self.fundamental_analyst = FundamentalAnalyst()
        self.sentiment_analyst = SentimentAnalyst(settings=self.settings)
        self.debate_room = DebateRoom()
        self.risk_manager = RiskManager(settings=self.settings)
        self.portfolio_manager = PortfolioManager(settings=self.settings)
        self.screener = StockScreener(
            data_agent=self.data_agent,
            technical_analyst=self.technical_analyst,
            fundamental_analyst=self.fundamental_analyst,
        )

    def analyze_stock(
        self,
        stock_code: str,
        history_days: int = 24,
        current_total_position: float = 0.0,
    ) -> StockAnalysisReport:
        """Analyze one stock and return a complete structured report."""
        bars = self.data_agent.get_history(stock_code, days=history_days)
        quote = self.data_agent.get_quote(stock_code)
        financial = self.data_agent.get_financial(stock_code)
        stock = StockIdentity(stock_code=quote.stock_code, stock_name=quote.stock_name, sector=quote.sector)

        technical = self.technical_analyst.analyze(stock_code, bars)
        fundamental = self.fundamental_analyst.analyze(financial)
        sentiment = self.sentiment_analyst.analyze(stock_code, stock_name=quote.stock_name, sector=quote.sector)
        debate = self.debate_room.analyze(stock_code, technical, fundamental, sentiment)
        risk = self.risk_manager.analyze(
            stock_code,
            quote,
            technical,
            fundamental,
            sentiment,
            current_total_position=current_total_position,
        )
        decision = self.portfolio_manager.decide(stock_code, quote, technical, fundamental, sentiment, debate, risk)
        return StockAnalysisReport(
            stock=stock,
            quote=quote,
            financial=financial,
            technical=technical,
            fundamental=fundamental,
            sentiment=sentiment,
            debate=debate,
            risk=risk,
            decision=decision,
        )

    def run_daily(self, max_count: int | None = None, history_days: int = 24) -> DailyRunReport:
        """Screen the universe, analyze selected candidates, and return a daily report."""
        limit = max_count if max_count is not None else self.settings.data.dynamic_universe_limit
        screened = self.screener.screen(max_count=limit, history_days=history_days)
        reports = [self.analyze_stock(item.stock.stock_code, history_days=history_days) for item in screened]
        return DailyRunReport(
            run_date=datetime.now().strftime("%Y-%m-%d"),
            candidates=[item.stock for item in screened],
            reports=reports,
            metadata={
                "data_mode": self.settings.data.mode,
                "history_days": history_days,
                "screened_count": len(screened),
                "candidate_scores": {item.stock.stock_code: item.score for item in screened},
            },
        )
