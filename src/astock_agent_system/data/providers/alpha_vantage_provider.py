from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from astock_agent_system.models import FinancialSnapshot, StockBar, StockQuote


class AlphaVantageProvider:
    """Fetch global reference prices from Alpha Vantage."""

    def __init__(self, api_key: str, base_url: str = "https://www.alphavantage.co/query") -> None:
        if not api_key:
            raise ValueError("Alpha Vantage API key is required. Set ALPHA_VANTAGE_API_KEY locally.")
        self.api_key = api_key
        self.base_url = base_url

    def get_history(self, stock_code: str, days: int = 30, **_: Any) -> list[StockBar]:
        payload = self._request(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": self._to_alpha_symbol(stock_code),
                "outputsize": "compact",
            }
        )
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict):
            message = payload.get("Note") or payload.get("Information") or payload.get("Error Message") or "missing daily series"
            raise RuntimeError(f"Alpha Vantage daily series unavailable: {message}")

        bars: list[StockBar] = []
        for date, row in series.items():
            if not isinstance(row, dict):
                continue
            close = _safe_float(row.get("4. close"))
            volume = _safe_float(row.get("6. volume") or row.get("5. volume"))
            bars.append(
                StockBar(
                    stock_code=stock_code,
                    date=str(date),
                    open=_safe_float(row.get("1. open")),
                    high=_safe_float(row.get("2. high")),
                    low=_safe_float(row.get("3. low")),
                    close=close,
                    volume=volume,
                    amount=close * volume,
                    turnover=0.0,
                )
            )
        bars.sort(key=lambda item: item.date)
        return bars[-days:] if days > 0 else bars

    def get_quote(self, stock_code: str) -> StockQuote:
        payload = self._request({"function": "GLOBAL_QUOTE", "symbol": self._to_alpha_symbol(stock_code)})
        quote = payload.get("Global Quote")
        if not isinstance(quote, dict) or not quote:
            bars = self.get_history(stock_code, days=2)
            if not bars:
                raise ValueError(f"No Alpha Vantage quote data found for {stock_code}")
            latest = bars[-1]
            previous = bars[-2] if len(bars) > 1 else latest
            change_pct = (latest.close - previous.close) / previous.close if previous.close else 0.0
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

        price = _safe_float(quote.get("05. price"))
        change_pct = _percent_to_ratio(quote.get("10. change percent"))
        volume = _safe_float(quote.get("06. volume"))
        return StockQuote(
            stock_code=stock_code,
            stock_name=str(quote.get("01. symbol") or stock_code),
            date=str(quote.get("07. latest trading day") or datetime.now().strftime("%Y-%m-%d")),
            price=price,
            change_pct=change_pct,
            volume=volume,
            amount=price * volume,
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

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        response = requests.get(self.base_url, params={**params, "apikey": self.api_key}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Alpha Vantage returned non-object JSON")
        return payload

    @staticmethod
    def _to_alpha_symbol(stock_code: str) -> str:
        """Convert common A-share suffixes to Alpha Vantage market suffixes."""
        if "." in stock_code:
            code, suffix = stock_code.split(".", 1)
            suffix = suffix.upper()
            if suffix in {"SH", "SS", "SSE"}:
                return f"{code}.SHH"
            if suffix in {"SZ", "SZSE"}:
                return f"{code}.SHZ"
        return stock_code


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _percent_to_ratio(value: Any) -> float:
    if value is None:
        return 0.0
    return _safe_float(str(value).replace("%", "")) / 100.0
