from __future__ import annotations

from typing import Any

from astock_agent_system.models import FinancialSnapshot, StockBar, StockQuote


class OpenBBProvider:
    """Best-effort OpenBB adapter for global reference market data."""

    def __init__(self) -> None:
        self._obb: Any = None

    def _get_obb(self) -> Any:
        if self._obb is not None:
            return self._obb
        try:
            from openbb import obb
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ImportError("openbb is not installed. Install it only if you want the optional OpenBB source.") from exc
        self._obb = obb
        return self._obb

    def get_history(self, stock_code: str, days: int = 30, **_: Any) -> list[StockBar]:
        obb = self._get_obb()
        symbol = self._to_openbb_symbol(stock_code)
        result = obb.equity.price.historical(symbol=symbol)
        rows = _result_to_rows(result)
        bars = [_bar_from_row(stock_code, row) for row in rows]
        bars = [item for item in bars if item is not None]
        bars.sort(key=lambda item: item.date)
        return bars[-days:] if days > 0 else bars

    def get_quote(self, stock_code: str) -> StockQuote:
        bars = self.get_history(stock_code, days=2)
        if not bars:
            raise ValueError(f"No OpenBB quote data found for {stock_code}")
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
    def _to_openbb_symbol(stock_code: str) -> str:
        if "." in stock_code:
            code, suffix = stock_code.split(".", 1)
            suffix = suffix.upper()
            if suffix == "SH":
                return f"{code}.SS"
            if suffix == "SZ":
                return f"{code}.SZ"
        if stock_code.startswith("6"):
            return f"{stock_code}.SS"
        if stock_code.startswith(("0", "3")):
            return f"{stock_code}.SZ"
        return stock_code


def _result_to_rows(result: Any) -> list[Any]:
    if hasattr(result, "to_df"):
        df = result.to_df()
        if hasattr(df, "iterrows"):
            return [row for _, row in df.iterrows()]
    results = getattr(result, "results", None)
    if isinstance(results, list):
        return results
    if isinstance(result, list):
        return result
    return []


def _bar_from_row(stock_code: str, row: Any) -> StockBar | None:
    date = _pick(row, "date", "datetime")
    close = _safe_float(_pick(row, "close"), default=None)
    if date is None or close is None:
        return None
    volume = _safe_float(_pick(row, "volume"))
    return StockBar(
        stock_code=stock_code,
        date=str(date).split()[0],
        open=_safe_float(_pick(row, "open")),
        high=_safe_float(_pick(row, "high")),
        low=_safe_float(_pick(row, "low")),
        close=close,
        volume=volume,
        amount=close * volume,
        turnover=0.0,
    )


def _pick(row: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(row, dict) and key in row:
            return row.get(key)
        if hasattr(row, key):
            return getattr(row, key)
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value not in {None, ""}:
            return value
    return None


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number
