from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote


class JQDataProvider:
    """Fetch A-share research data from JQData when local credentials exist."""

    def __init__(self, username: str, password: str) -> None:
        if not username or not password:
            raise ValueError("JQData username/password are required. Set JQDATA_USERNAME and JQDATA_PASSWORD locally.")
        self.username = username
        self.password = password
        self._jq: Any = None
        self._authorized = False

    def _get_jq(self) -> Any:
        if self._jq is not None and self._authorized:
            return self._jq
        try:
            import jqdatasdk as jq
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ImportError("jqdatasdk is not installed. Install it only if you have a JQData account.") from exc
        jq.auth(self.username, self.password)
        self._jq = jq
        self._authorized = True
        return jq

    def get_universe(self, limit: int | None = None) -> list[StockIdentity]:
        jq = self._get_jq()
        securities = jq.get_all_securities(types=["stock"], date=None)
        stocks: list[StockIdentity] = []
        if hasattr(securities, "iterrows"):
            iterator = securities.iterrows()
            for code, row in iterator:
                stock_code = self._normalize_code(str(code))
                stocks.append(
                    StockIdentity(
                        stock_code=stock_code,
                        stock_name=str(row.get("display_name") or row.get("name") or stock_code),
                        sector="",
                    )
                )
                if limit and len(stocks) >= limit:
                    break
        return stocks

    def get_history(self, stock_code: str, days: int = 30, **_: Any) -> list[StockBar]:
        jq = self._get_jq()
        jq_code = self._to_jq_code(stock_code)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=max(days, 1))).strftime("%Y-%m-%d")
        df = jq.get_price(
            jq_code,
            start_date=start_date,
            end_date=end_date,
            frequency="daily",
            fields=["open", "close", "high", "low", "volume", "money"],
            skip_paused=True,
            fq="pre",
        )
        if df is None or getattr(df, "empty", False):
            return []
        bars: list[StockBar] = []
        for index, row in df.iterrows():
            close = _safe_float(row.get("close"))
            volume = _safe_float(row.get("volume"))
            bars.append(
                StockBar(
                    stock_code=stock_code,
                    date=_date_from_index(index),
                    open=_safe_float(row.get("open")),
                    high=_safe_float(row.get("high")),
                    low=_safe_float(row.get("low")),
                    close=close,
                    volume=volume,
                    amount=_safe_float(row.get("money"), close * volume),
                    turnover=0.0,
                )
            )
        bars.sort(key=lambda item: item.date)
        return bars[-days:] if days > 0 else bars

    def get_quote(self, stock_code: str) -> StockQuote:
        bars = self.get_history(stock_code, days=2)
        if not bars:
            raise ValueError(f"No JQData quote data found for {stock_code}")
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
    def _to_jq_code(stock_code: str) -> str:
        if "." in stock_code:
            code, suffix = stock_code.split(".", 1)
            suffix = suffix.upper()
            if suffix == "SH":
                return f"{code}.XSHG"
            if suffix == "SZ":
                return f"{code}.XSHE"
            if suffix == "BJ":
                return f"{code}.XBSE"
            return stock_code
        if stock_code.startswith("6"):
            return f"{stock_code}.XSHG"
        if stock_code.startswith(("0", "3")):
            return f"{stock_code}.XSHE"
        if stock_code.startswith("8"):
            return f"{stock_code}.XBSE"
        return stock_code

    @staticmethod
    def _normalize_code(code: str) -> str:
        return code.split(".", 1)[0] if "." in code else code


def _date_from_index(index: Any) -> str:
    if hasattr(index, "strftime"):
        return str(index.strftime("%Y-%m-%d"))
    return str(index).split()[0]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number
