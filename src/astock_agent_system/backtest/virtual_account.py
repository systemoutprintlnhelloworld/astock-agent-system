"""Virtual account for paper trading and lightweight backtests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from astock_agent_system.config import PortfolioSettings, Settings, load_settings


@dataclass(slots=True)
class Position:
    stock_code: str
    shares: int
    cost_basis: float
    last_buy_date: str = ""

    def market_value(self, price: float) -> float:
        return self.shares * price

    def to_dict(self, price: float | None = None) -> dict[str, Any]:
        payload = asdict(self)
        if price is not None:
            payload["market_value"] = self.market_value(price)
            payload["unrealized_return"] = (price - self.cost_basis) / self.cost_basis if self.cost_basis else 0.0
        return payload


@dataclass(slots=True)
class TradeRecord:
    date: str
    stock_code: str
    side: str
    price: float
    shares: int
    cash_after: float
    realized_pnl: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VirtualAccount:
    """A-share paper account with fees, stamp tax and simple T+1 checks."""

    def __init__(self, settings: Settings | PortfolioSettings | None = None, initial_capital: float | None = None) -> None:
        if settings is None:
            portfolio = load_settings().portfolio
        elif isinstance(settings, PortfolioSettings):
            portfolio = settings
        else:
            portfolio = settings.portfolio
        self.portfolio = portfolio
        self.initial_capital = float(initial_capital if initial_capital is not None else portfolio.initial_capital)
        self.cash = self.initial_capital
        self.positions: dict[str, Position] = {}
        self.trades: list[TradeRecord] = []
        self.equity_curve: list[dict[str, float | str]] = []

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any],
        settings: Settings | PortfolioSettings | None = None,
        initial_capital: float | None = None,
    ) -> "VirtualAccount":
        """Restore a virtual account from a persisted position snapshot.

        The snapshot format matches MongoDB ``positions`` rows. Missing or
        malformed fields fall back to safe defaults so a bad snapshot does not
        crash the daily automation loop.
        """
        restored_initial_capital = initial_capital
        if restored_initial_capital is None and snapshot.get("initial_capital") is not None:
            restored_initial_capital = _to_float(snapshot.get("initial_capital"), 0.0)
        account = cls(settings=settings, initial_capital=restored_initial_capital)
        account.cash = _to_float(snapshot.get("cash"), account.cash)
        restored_positions = snapshot.get("positions", [])
        if isinstance(restored_positions, dict):
            restored_positions = list(restored_positions.values())
        if isinstance(restored_positions, list):
            for item in restored_positions:
                if not isinstance(item, dict):
                    continue
                stock_code = str(item.get("stock_code", "")).strip()
                shares = int(_to_float(item.get("shares"), 0.0))
                cost_basis = _to_float(item.get("cost_basis"), 0.0)
                if not stock_code or shares <= 0 or cost_basis <= 0:
                    continue
                account.positions[stock_code] = Position(
                    stock_code=stock_code,
                    shares=shares,
                    cost_basis=cost_basis,
                    last_buy_date=str(item.get("last_buy_date", "")),
                )
        return account

    def equity(self, prices: dict[str, float] | None = None) -> float:
        prices = prices or {}
        market_value = sum(position.market_value(prices.get(code, position.cost_basis)) for code, position in self.positions.items())
        return self.cash + market_value

    def exposure_pct(self, prices: dict[str, float] | None = None) -> float:
        equity = self.equity(prices)
        if equity <= 0:
            return 0.0
        prices = prices or {}
        market_value = sum(position.market_value(prices.get(code, position.cost_basis)) for code, position in self.positions.items())
        return market_value / equity

    def buy(self, stock_code: str, price: float, target_value: float, date: str, reason: str = "") -> bool:
        execution_price = price * (1.0 + self.portfolio.slippage_rate)
        shares = int(target_value / execution_price / 100) * 100
        if shares <= 0:
            return False
        gross = execution_price * shares
        fee = gross * self.portfolio.commission_rate
        total_cost = gross + fee
        if total_cost > self.cash:
            shares = int(self.cash / execution_price / (1.0 + self.portfolio.commission_rate) / 100) * 100
            if shares <= 0:
                return False
            gross = execution_price * shares
            fee = gross * self.portfolio.commission_rate
            total_cost = gross + fee
        old = self.positions.get(stock_code)
        if old:
            new_shares = old.shares + shares
            new_cost = ((old.cost_basis * old.shares) + gross) / new_shares
            self.positions[stock_code] = Position(stock_code, new_shares, new_cost, last_buy_date=date)
        else:
            self.positions[stock_code] = Position(stock_code, shares, execution_price, last_buy_date=date)
        self.cash -= total_cost
        self.trades.append(TradeRecord(date, stock_code, "BUY", execution_price, shares, self.cash, reason=reason))
        return True

    def sell(self, stock_code: str, price: float, shares: int | None, date: str, reason: str = "") -> bool:
        position = self.positions.get(stock_code)
        if position is None or position.shares <= 0:
            return False
        if position.last_buy_date == date:
            return False
        sell_shares = min(position.shares, shares if shares is not None else position.shares)
        sell_shares = int(sell_shares / 100) * 100
        if sell_shares <= 0:
            return False
        execution_price = price * (1.0 - self.portfolio.slippage_rate)
        gross = execution_price * sell_shares
        fee = gross * self.portfolio.commission_rate
        stamp_tax = gross * self.portfolio.stamp_tax_rate
        revenue = gross - fee - stamp_tax
        realized_pnl = (execution_price - position.cost_basis) * sell_shares - fee - stamp_tax
        self.cash += revenue
        remaining = position.shares - sell_shares
        if remaining > 0:
            self.positions[stock_code] = Position(stock_code, remaining, position.cost_basis, position.last_buy_date)
        else:
            del self.positions[stock_code]
        self.trades.append(TradeRecord(date, stock_code, "SELL", execution_price, sell_shares, self.cash, realized_pnl, reason))
        return True

    def mark_to_market(self, date: str, prices: dict[str, float]) -> dict[str, float | str]:
        equity = self.equity(prices)
        row: dict[str, float | str] = {
            "date": date,
            "cash": round(self.cash, 4),
            "equity": round(equity, 4),
            "exposure_pct": round(self.exposure_pct(prices), 6),
        }
        self.equity_curve.append(row)
        return row

    def positions_to_dict(self, prices: dict[str, float] | None = None) -> dict[str, Any]:
        prices = prices or {}
        return {code: position.to_dict(prices.get(code)) for code, position in self.positions.items()}

    def to_dict(self, prices: dict[str, float] | None = None) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "equity": self.equity(prices),
            "positions": self.positions_to_dict(prices),
            "trades": [trade.to_dict() for trade in self.trades],
            "equity_curve": self.equity_curve,
        }


def _to_float(value: Any, default: float | None = 0.0) -> float:
    if value is None and default is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default or 0.0)
