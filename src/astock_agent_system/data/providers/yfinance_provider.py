from __future__ import annotations

import logging
from typing import Any

from astock_agent_system.models import FinancialSnapshot, StockBar, StockQuote

logger = logging.getLogger(__name__)


class YFinanceProvider:
    """Fetch reference prices from yfinance for global/HK/A-share mapped symbols."""

    def __init__(self) -> None:
        self._yf: Any = None

    def _get_yf(self) -> Any:
        if self._yf is not None:
            return self._yf
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ImportError("yfinance is not installed. Run: pip install yfinance") from exc
        self._yf = yf
        return self._yf

    def get_history(self, stock_code: str, days: int = 30, freq: str = "1d", **_: Any) -> list[StockBar]:
        yf = self._get_yf()
        symbol = self._to_yahoo_symbol(stock_code)
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{max(days, 1)}d", interval=freq or "1d", auto_adjust=False, actions=False)
        if df is None or df.empty:
            return []

        bars: list[StockBar] = []
        for index, row in df.iterrows():
            close = _safe_float(row.get("Close", 0.0))
            volume = _safe_float(row.get("Volume", 0.0))
            bars.append(
                StockBar(
                    stock_code=stock_code,
                    date=_date_from_index(index),
                    open=_safe_float(row.get("Open", 0.0)),
                    high=_safe_float(row.get("High", 0.0)),
                    low=_safe_float(row.get("Low", 0.0)),
                    close=close,
                    volume=volume,
                    amount=close * volume,
                    turnover=0.0,
                )
            )
        bars.sort(key=lambda item: item.date)
        return bars[-days:] if days > 0 else bars

    def get_quote(self, stock_code: str) -> StockQuote:
        bars = self.get_history(stock_code, days=2)
        if not bars:
            raise ValueError(f"No yfinance quote data found for {stock_code}")
        latest = bars[-1]
        previous_close = bars[-2].close if len(bars) > 1 else latest.close
        change_pct = (latest.close - previous_close) / previous_close if previous_close else 0.0
        return StockQuote(
            stock_code=stock_code,
            stock_name=stock_code,
            date=latest.date,
            price=latest.close,
            change_pct=change_pct,
            volume=latest.volume,
            amount=latest.amount,
            sector="",
        )

    def get_financial(self, stock_code: str) -> FinancialSnapshot:
        quote = self.get_quote(stock_code)
        return FinancialSnapshot(
            stock_code=stock_code,
            stock_name=quote.stock_name,
            report_date=quote.date,
            pe_ttm=0.0,
            pb=0.0,
            roe=0.0,
            debt_ratio=0.0,
            revenue_growth=0.0,
            profit_growth=0.0,
            market_cap=0.0,
            sector=quote.sector,
        )

    @staticmethod
    def _to_yahoo_symbol(stock_code: str) -> str:
        if "." in stock_code:
            code, suffix = stock_code.split(".", 1)
            suffix = suffix.upper()
            if suffix == "SH":
                return f"{code}.SS"
            if suffix in {"SZ", "SS"}:
                return f"{code}.{suffix}"
            return stock_code
        if stock_code.startswith("6"):
            return f"{stock_code}.SS"
        if stock_code.startswith(("0", "3")):
            return f"{stock_code}.SZ"
        return stock_code


def _date_from_index(index: Any) -> str:
    if hasattr(index, "strftime"):
        return str(index.strftime("%Y-%m-%d"))
    return str(index).split()[0]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number
