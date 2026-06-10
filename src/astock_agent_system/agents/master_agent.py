"""Master orchestration agent for the daily investment workflow."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from astock_agent_system.agents.debate_room import DebateRoom
from astock_agent_system.agents.fundamental_analyst import FundamentalAnalyst
from astock_agent_system.agents.portfolio_manager import PortfolioManager
from astock_agent_system.agents.risk_manager import RiskManager
from astock_agent_system.agents.screener import StockScreener
from astock_agent_system.agents.sentiment_analyst import SentimentAnalyst
from astock_agent_system.agents.technical_analyst import TechnicalAnalyst
from astock_agent_system.config import Settings, load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.events.emitter import AgentEventEmitter
from astock_agent_system.models import DailyRunReport, StockAnalysisReport, StockIdentity


class MasterAgent:
    """Run the explicit MVP workflow before optional LangGraph integration."""

    def __init__(
        self,
        settings: Settings | None = None,
        data_agent: DataAgent | None = None,
        event_emitter: AgentEventEmitter | None = None,
        run_id: str = "",
        agent_id: str = "",
        model: str = "",
    ) -> None:
        self.settings = settings or load_settings()
        self.data_agent = data_agent or DataAgent(settings=self.settings)
        self.event_emitter = event_emitter
        self.run_id = run_id
        self.agent_id = agent_id
        self.model = model
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
        self._emit(
            "analysis_start",
            stage="analysis",
            message=f"开始分析 {stock_code}",
            stock_code=stock_code,
            history_days=history_days,
        )
        self._emit(
            "data_fetch_start",
            stage="data_fetch",
            message=f"获取 {stock_code} 的K线、报价和财务快照",
            stock_code=stock_code,
            history_days=history_days,
        )
        bars = self.data_agent.get_history(stock_code, days=history_days)
        quote = self.data_agent.get_quote(stock_code)
        financial = self.data_agent.get_financial(stock_code)
        stock = StockIdentity(stock_code=quote.stock_code, stock_name=quote.stock_name, sector=quote.sector)
        objective_data = self._objective_payload(stock, quote, financial, bars)
        self._emit(
            "data_fetch_complete",
            stage="data_fetch",
            message=f"完成 {stock_code} 数据获取：{len(bars)} 根K线",
            stock_code=stock_code,
            history_count=len(bars),
            objective_data=objective_data,
        )

        technical = self.technical_analyst.analyze(stock_code, bars)
        self._emit_chain_step(
            "technical_analyst",
            stock_code,
            "技术分析完成",
            result=technical,
            objective_data={"bars": objective_data.get("bars", [])},
        )
        fundamental = self.fundamental_analyst.analyze(financial)
        self._emit_chain_step(
            "fundamental_analyst",
            stock_code,
            "基本面分析完成",
            result=fundamental,
            objective_data={"financial": objective_data.get("financial")},
        )
        sentiment = self.sentiment_analyst.analyze(stock_code, stock_name=quote.stock_name, sector=quote.sector)
        objective_data["news"] = _extract_news(sentiment)
        self._emit_chain_step(
            "sentiment_analyst",
            stock_code,
            "舆情分析完成",
            result=sentiment,
            objective_data={"news": objective_data.get("news", [])},
        )
        debate = self.debate_room.analyze(stock_code, technical, fundamental, sentiment)
        self._emit_chain_step("debate_room", stock_code, "多Agent辩论完成", result=debate)
        risk = self.risk_manager.analyze(
            stock_code,
            quote,
            technical,
            fundamental,
            sentiment,
            current_total_position=current_total_position,
        )
        self._emit_chain_step("risk_manager", stock_code, "风控评估完成", result=risk, quote=quote)
        decision = self.portfolio_manager.decide(stock_code, quote, technical, fundamental, sentiment, debate, risk)
        agent_chain = {
            "technical": _to_dict(technical),
            "fundamental": _to_dict(fundamental),
            "sentiment": _to_dict(sentiment),
            "debate": _to_dict(debate),
            "risk": _to_dict(risk),
        }
        decision.explanation_data = {
            **(decision.explanation_data or {}),
            "objective_data": objective_data,
            "agent_chain": agent_chain,
        }
        self._emit_chain_step(
            "portfolio_manager",
            stock_code,
            f"组合经理给出 {decision.action} 决策",
            decision=decision,
            explanation_data=decision.explanation_data,
        )
        report = StockAnalysisReport(
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
        self._emit(
            "analysis_complete",
            stage="analysis",
            message=f"完成 {stock_code} 分析：{decision.action}，置信度 {decision.confidence:.2f}",
            stock_code=stock_code,
            report=report.to_dict(),
            objective_data=objective_data,
            agent_chain=agent_chain,
        )
        return report

    def run_daily(self, max_count: int | None = None, history_days: int = 24) -> DailyRunReport:
        """Screen the universe, analyze selected candidates, and return a daily report."""
        limit = max_count if max_count is not None else self.settings.data.dynamic_universe_limit
        self._emit(
            "screening_start",
            stage="screening",
            message=f"开始股票池筛选，目标数量 {limit}",
            max_count=limit,
            history_days=history_days,
            data_mode=self.settings.data.mode,
        )
        screened = self.screener.screen(max_count=limit, history_days=history_days)
        self._emit(
            "screening_complete",
            stage="screening",
            message=f"完成股票池筛选，入选 {len(screened)} 只股票",
            candidates=[item.stock.to_dict() for item in screened],
            candidate_scores={item.stock.stock_code: item.score for item in screened},
        )
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

    def _emit(self, event_type: str, *, stage: str, message: str, **payload: Any) -> None:
        """Emit a streaming event when the caller provided an event bus."""
        if self.event_emitter is None:
            return
        self.event_emitter.emit(
            event_type,
            run_id=self.run_id,
            agent_id=self.agent_id,
            model=self.model,
            stage=stage,
            message=message,
            **payload,
        )

    def _emit_chain_step(self, step: str, stock_code: str, message: str, **payload: Any) -> None:
        result = payload.get("result")
        self._emit(
            "agent_chain_step",
            stage=step,
            message=f"{stock_code} {message}",
            stock_code=stock_code,
            chain_step=step,
            result=_to_dict(result) if result is not None else None,
            **{key: _to_dict(value) for key, value in payload.items() if key != "result"},
        )

    def _objective_payload(self, stock: Any, quote: Any, financial: Any, bars: list[Any]) -> dict[str, Any]:
        return {
            "stock": _to_dict(stock),
            "quote": _to_dict(quote),
            "financial": _to_dict(financial),
            "bars": [_to_dict(bar) for bar in bars[-20:]],
        }


def _to_dict(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_dict(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    return value


def _extract_news(sentiment: Any) -> list[Any]:
    metadata = getattr(sentiment, "metadata", {}) or {}
    for key in ("news", "news_items", "articles", "items", "samples"):
        value = metadata.get(key)
        if value:
            return _to_dict(value)
    reasons = getattr(sentiment, "reasons", []) or []
    return list(reasons)
