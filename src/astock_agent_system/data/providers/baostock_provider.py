from __future__ import annotations

import contextlib
import io
import logging
from datetime import datetime, timedelta
from typing import Any

from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote

logger = logging.getLogger(__name__)


class BaostockProvider:
    """Fetch A-share data from Baostock as a lightweight fallback."""

    def __init__(self) -> None:
        self._bs: Any = None
        self._logged_in = False

    def _get_bs(self) -> Any:
        if self._bs is not None:
            return self._bs
        try:
            import baostock as bs
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ImportError("baostock is not installed. Run: pip install baostock") from exc
        self._bs = bs
        if not self._logged_in:
            # baostock prints "login success!" to stdout, which corrupts JSON
            # output from diagnostic CLI commands. Capture it and rely on the
            # returned error_code/error_msg instead.
            with contextlib.redirect_stdout(io.StringIO()):
                login_result = self._bs.login()
            self._logged_in = True
            if str(getattr(login_result, "error_code", "0")) not in {"0", "0000"}:
                raise RuntimeError(f"Baostock login failed: {getattr(login_result, 'error_msg', 'unknown error')}")
        logger.info("Baostock session initialized")
        return self._bs

    def get_universe(self, limit: int | None = None) -> list[StockIdentity]:
        bs = self._get_bs()
        rs = bs.query_stock_basic()
        if str(getattr(rs, "error_code", "1")) != "0":
            raise RuntimeError(f"Baostock universe query failed: {getattr(rs, 'error_msg', 'unknown error')}")

        stocks: list[StockIdentity] = []
        while rs.next():
            row = rs.get_row_data()
            if not row:
                continue
            raw_code = str(row[0]).strip()
            if not raw_code:
                continue
            stock_code = self._normalize_code(raw_code)
            stock_type = str(row[4]).strip() if len(row) > 4 else ""
            stock_status = str(row[5]).strip() if len(row) > 5 else ""
            if stock_type and stock_type != "1":
                continue
            if stock_status and stock_status != "1":
                continue
            if not _is_supported_a_share_stock_code(stock_code, raw_code):
                continue
            stock_name = str(row[1]).strip() if len(row) > 1 else stock_code
            stocks.append(StockIdentity(stock_code=stock_code, stock_name=stock_name, sector=""))
            if limit and len(stocks) >= limit:
                break

        logger.info("Fetched %s stocks from Baostock universe", len(stocks))
        return stocks

    def get_history(self, stock_code: str, days: int = 30, freq: str = "d", **_: Any) -> list[StockBar]:
        bs = self._get_bs()
        bs_code = self._to_bs_code(stock_code)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=max(days, 1))).strftime("%Y-%m-%d")
        fields = "date,open,high,low,close,volume,amount,pctChg"
        rs = bs.query_history_k_data_plus(
            bs_code,
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency=freq or "d",
            adjustflag="2",
        )
        if str(getattr(rs, "error_code", "1")) != "0":
            raise RuntimeError(f"Baostock history query failed for {stock_code}: {getattr(rs, 'error_msg', 'unknown error')}")

        bars: list[StockBar] = []
        while rs.next():
            row = rs.get_row_data()
            if len(row) < 7:
                continue
            bars.append(
                StockBar(
                    stock_code=stock_code,
                    date=str(row[0]),
                    open=_safe_float(row[1]),
                    high=_safe_float(row[2]),
                    low=_safe_float(row[3]),
                    close=_safe_float(row[4]),
                    volume=_safe_float(row[5]),
                    amount=_safe_float(row[6]),
                    turnover=_safe_float(row[7]) if len(row) > 7 else 0.0,
                )
            )

        bars.sort(key=lambda item: item.date)
        if days > 0:
            return bars[-days:]
        return bars

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

    def get_quote(self, stock_code: str) -> StockQuote:
        bars = self.get_history(stock_code, days=2, freq="d")
        if not bars:
            raise ValueError(f"No Baostock quote data found for {stock_code}")

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

    @staticmethod
    def _to_bs_code(stock_code: str) -> str:
        if "." in stock_code:
            code, suffix = stock_code.split(".", 1)
            suffix = suffix.upper()
            if suffix in {"SH", "SS"}:
                return f"sh.{code}"
            if suffix == "SZ":
                return f"sz.{code}"
            if suffix == "BJ":
                return f"bj.{code}"
            return stock_code.lower()
        if stock_code.startswith("6"):
            return f"sh.{stock_code}"
        if stock_code.startswith(("0", "3")):
            return f"sz.{stock_code}"
        if stock_code.startswith("8"):
            return f"bj.{stock_code}"
        return stock_code.lower()

    @staticmethod
    def _normalize_code(code: str) -> str:
        if "." in code:
            left, right = code.split(".", 1)
            return left if left.isdigit() else right
        return code


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _is_supported_a_share_stock_code(stock_code: str, raw_code: str = "") -> bool:
    """Return whether a Baostock row is a normal A-share stock code.

    Baostock universe rows can include indexes such as ``sh.000001``. If those
    are normalized to ``000001`` without filtering, the screener later asks all
    providers for non-stock symbols like 000003/000004 and looks broken.
    """
    code = stock_code.strip()
    raw = raw_code.strip().lower()
    if len(code) != 6 or not code.isdigit():
        return False
    if raw.startswith("sh.") and code.startswith(("0", "3")):
        return False
    if raw.startswith("sz.") and code.startswith("6"):
        return False
    return code.startswith(("0", "2", "3", "6", "8", "9"))
