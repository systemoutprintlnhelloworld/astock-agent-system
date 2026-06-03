"""Built-in lightweight historical backtest engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from astock_agent_system.agents.debate_room import DebateRoom
from astock_agent_system.agents.fundamental_analyst import FundamentalAnalyst
from astock_agent_system.agents.portfolio_manager import PortfolioManager
from astock_agent_system.agents.risk_manager import RiskManager
from astock_agent_system.agents.screener import StockScreener
from astock_agent_system.agents.sentiment_analyst import SentimentAnalyst
from astock_agent_system.agents.technical_analyst import TechnicalAnalyst
from astock_agent_system.backtest.virtual_account import VirtualAccount
from astock_agent_system.config import Settings, load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.models import StockBar, StockQuote


@dataclass(slots=True)
class BacktestResult:
    status: str
    initial_capital: float
    final_equity: float
    total_return: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    cash: float
    positions: dict[str, Any] = field(default_factory=dict)
    equity_curve: list[dict[str, float | str]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BacktestEngine:
    """Replay the MVP decision rules on available historical bars."""

    def __init__(self, settings: Settings | None = None, data_agent: DataAgent | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_agent = data_agent or DataAgent(settings=self.settings)
        self.technical_analyst = TechnicalAnalyst()
        self.fundamental_analyst = FundamentalAnalyst()
        self.sentiment_analyst = SentimentAnalyst(settings=self.settings)
        self.debate_room = DebateRoom()
        self.risk_manager = RiskManager(settings=self.settings)
        self.portfolio_manager = PortfolioManager(settings=self.settings)

    def run(
        self,
        stock_codes: list[str] | None = None,
        max_count: int = 3,
        initial_capital: float | None = None,
        history_days: int = 24,
    ) -> BacktestResult:
        selected_codes = stock_codes or [item.stock.stock_code for item in StockScreener(self.data_agent).screen(max_count=max_count)]
        selected_codes = selected_codes[: max(1, max_count)]
        histories = {code: self.data_agent.get_history(code, days=history_days) for code in selected_codes}
        dates = _common_dates(histories)
        account = VirtualAccount(self.settings, initial_capital=initial_capital)

        if len(dates) < 6:
            return _build_result(account, {}, status="skipped", metadata={"reason": "not enough common dates"})

        latest_prices: dict[str, float] = {}
        for current_date in dates:
            prices = {code: _bar_on_date(bars, current_date).close for code, bars in histories.items() if _bar_on_date(bars, current_date)}
            latest_prices.update(prices)
            for code in selected_codes:
                bars_to_date = [bar for bar in histories[code] if bar.date <= current_date]
                if len(bars_to_date) < 6:
                    continue
                latest_bar = bars_to_date[-1]
                quote = _quote_from_bar(code, self.data_agent.get_quote(code).stock_name, self.data_agent.get_quote(code).sector, latest_bar, bars_to_date)
                technical = self.technical_analyst.analyze(code, bars_to_date)
                fundamental = self.fundamental_analyst.analyze(self.data_agent.get_financial(code))
                sentiment = self.sentiment_analyst.analyze(code, stock_name=quote.stock_name, sector=quote.sector)
                debate = self.debate_room.analyze(code, technical, fundamental, sentiment)
                risk = self.risk_manager.analyze(
                    code,
                    quote,
                    technical,
                    fundamental,
                    sentiment,
                    current_total_position=account.exposure_pct(latest_prices),
                )
                decision = self.portfolio_manager.decide(code, quote, technical, fundamental, sentiment, debate, risk)
                position = account.positions.get(code)
                stop_loss_pct = self.settings.risk.stop_loss_pct
                if position and latest_bar.close <= position.cost_basis * (1.0 - stop_loss_pct):
                    account.sell(code, latest_bar.close, None, current_date, reason="stop_loss")
                elif decision.action == "SELL" and position:
                    account.sell(code, latest_bar.close, None, current_date, reason="decision_sell")
                elif decision.action == "BUY" and not position:
                    target_value = account.equity(latest_prices) * decision.position_size
                    account.buy(code, latest_bar.close, target_value, current_date, reason="decision_buy")
            account.mark_to_market(current_date, latest_prices)

        return _build_result(
            account,
            latest_prices,
            status="ok",
            metadata={"stock_codes": selected_codes, "engine": "built-in", "history_days": history_days},
        )


def _quote_from_bar(stock_code: str, stock_name: str, sector: str, bar: StockBar, bars: list[StockBar]) -> StockQuote:
    previous_close = bars[-2].close if len(bars) >= 2 else bar.close
    change_pct = (bar.close - previous_close) / previous_close if previous_close else 0.0
    return StockQuote(
        stock_code=stock_code,
        stock_name=stock_name,
        date=bar.date,
        price=bar.close,
        change_pct=change_pct,
        volume=bar.volume,
        amount=bar.amount,
        sector=sector,
    )


def _common_dates(histories: dict[str, list[StockBar]]) -> list[str]:
    date_sets = [{bar.date for bar in bars} for bars in histories.values() if bars]
    if not date_sets:
        return []
    common = set.intersection(*date_sets)
    return sorted(common)


def _bar_on_date(bars: list[StockBar], date: str) -> StockBar | None:
    for bar in bars:
        if bar.date == date:
            return bar
    return None


def _max_drawdown(equity_curve: list[dict[str, float | str]]) -> float:
    peak = 0.0
    max_dd = 0.0
    for row in equity_curve:
        equity = float(row.get("equity", 0.0))
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd


def _win_rate(trades: list[dict[str, Any]]) -> float:
    sell_trades = [trade for trade in trades if trade.get("side") == "SELL"]
    if not sell_trades:
        return 0.0
    wins = sum(1 for trade in sell_trades if float(trade.get("realized_pnl", 0.0)) > 0)
    return wins / len(sell_trades)


def _build_result(account: VirtualAccount, latest_prices: dict[str, float], status: str, metadata: dict[str, Any]) -> BacktestResult:
    account_payload = account.to_dict(latest_prices)
    final_equity = float(account_payload["equity"])
    total_return = (final_equity - account.initial_capital) / account.initial_capital if account.initial_capital else 0.0
    trades = account_payload["trades"]
    return BacktestResult(
        status=status,
        initial_capital=round(account.initial_capital, 4),
        final_equity=round(final_equity, 4),
        total_return=round(total_return, 6),
        max_drawdown=round(_max_drawdown(account.equity_curve), 6),
        win_rate=round(_win_rate(trades), 6),
        trade_count=len(trades),
        cash=round(account.cash, 4),
        positions=account_payload["positions"],
        equity_curve=account.equity_curve,
        trades=trades,
        metadata=metadata,
    )
