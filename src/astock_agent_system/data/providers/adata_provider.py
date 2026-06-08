from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote

logger = logging.getLogger(__name__)


class ADataProvider:
    """Best-effort adapter for the optional AData package."""

    def __init__(self) -> None:
        self._adata: Any = None

    def _get_adata(self) -> Any:
        if self._adata is not None:
            return self._adata
        try:
            import adata
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ImportError("adata is not installed. Install it only if you want the optional AData source.") from exc
        self._adata = adata
        return self._adata

    def get_universe(self, limit: int | None = None) -> list[StockIdentity]:
        adata = self._get_adata()
        callers: list[Callable[[], Any]] = []
        stock = getattr(adata, "stock", None)
        info = getattr(stock, "info", None) if stock is not None else None
        if info is not None:
            for name in ("all_code", "get_all_code", "get_stock_code"):
                func = getattr(info, name, None)
                if callable(func):
                    callers.append(func)

        df = _first_success(callers)
        if df is None:
            raise RuntimeError("AData universe API is unavailable for this installed package version")

        stocks: list[StockIdentity] = []
        for row in _iter_rows(df):
            stock_code = _pick(row, "stock_code", "code", "股票代码", "证券代码")
            if not stock_code:
                continue
            stocks.append(
                StockIdentity(
                    stock_code=_normalize_code(str(stock_code)),
                    stock_name=str(_pick(row, "short_name", "stock_name", "name", "股票简称", "证券简称") or stock_code),
                    sector=str(_pick(row, "industry", "sector", "行业") or ""),
                )
            )
            if limit and len(stocks) >= limit:
                break
        return stocks

    def get_history(self, stock_code: str, days: int = 30, **_: Any) -> list[StockBar]:
        adata = self._get_adata()
        stock = getattr(adata, "stock", None)
        market = getattr(stock, "market", None) if stock is not None else None
        if market is None:
            raise RuntimeError("AData market API is unavailable for this installed package version")

        start_date = (datetime.now() - timedelta(days=max(days, 1))).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        callers: list[Callable[[], Any]] = []
        for name in ("get_market", "get_kline", "get_history"):
            func = getattr(market, name, None)
            if callable(func):
                callers.extend(
                    [
                        lambda func=func: func(stock_code=stock_code, start_date=start_date, end_date=end_date),
                        lambda func=func: func(code=stock_code, start_date=start_date, end_date=end_date),
                        lambda func=func: func(stock_code),
                    ]
                )

        df = _first_success(callers)
        if df is None:
            raise RuntimeError("AData history API is unavailable for this installed package version")

        bars = [_bar_from_row(stock_code, row) for row in _iter_rows(df)]
        bars = [item for item in bars if item is not None]
        bars.sort(key=lambda item: item.date)
        return bars[-days:] if days > 0 else bars

    def get_quote(self, stock_code: str) -> StockQuote:
        bars = self.get_history(stock_code, days=2)
        if not bars:
            raise ValueError(f"No AData quote data found for {stock_code}")
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


def _first_success(callers: list[Callable[[], Any]]) -> Any | None:
    last_error: Exception | None = None
    for caller in callers:
        try:
            result = caller()
            if result is not None and not getattr(result, "empty", False):
                return result
        except Exception as exc:  # pragma: no cover - package-version dependent
            last_error = exc
    if last_error is not None:
        logger.debug("AData optional API probing failed: %s", last_error)
    return None


def _iter_rows(table: Any):
    if hasattr(table, "iterrows"):
        for _, row in table.iterrows():
            yield row
        return
    if isinstance(table, list):
        for row in table:
            yield row


def _pick(row: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(row, dict) and key in row:
            return row.get(key)
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value not in {None, ""}:
            return value
    return None


def _bar_from_row(stock_code: str, row: Any) -> StockBar | None:
    date = _pick(row, "date", "trade_date", "datetime", "日期", "交易日期")
    close = _safe_float(_pick(row, "close", "close_price", "收盘", "收盘价"), default=None)
    if date is None or close is None:
        return None
    volume = _safe_float(_pick(row, "volume", "成交量"))
    amount = _safe_float(_pick(row, "amount", "成交额"))
    return StockBar(
        stock_code=stock_code,
        date=str(date).split()[0],
        open=_safe_float(_pick(row, "open", "open_price", "开盘", "开盘价")),
        high=_safe_float(_pick(row, "high", "最高", "最高价")),
        low=_safe_float(_pick(row, "low", "最低", "最低价")),
        close=close,
        volume=volume,
        amount=amount,
        turnover=_safe_float(_pick(row, "turnover", "换手率")),
    )


def _normalize_code(code: str) -> str:
    if "." in code:
        return code.split(".", 1)[0] if code[0].isdigit() else code.split(".", 1)[1]
    return code


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number
