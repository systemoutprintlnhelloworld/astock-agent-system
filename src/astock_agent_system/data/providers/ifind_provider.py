"""iFinD / 同花顺 QuantAPI HTTP provider.

This adapter intentionally uses the documented HTTP interface instead of the
desktop SDK so it can run in a normal Python CLI process. Real access tokens are
read from local environment/runtime config only; never commit them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import requests

from astock_agent_system.models import StockBar, StockQuote


class IfindProvider:
    """Fetch A-share history/quote data from iFinD QuantAPI HTTP endpoints."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str = "",
        base_url: str = "https://quantapi.51ifind.com/api/v1",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not access_token:
            raise ValueError("iFinD access token is required. Set IFIND_ACCESS_TOKEN locally.")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_history(self, stock_code: str, days: int = 30, **_: Any) -> list[StockBar]:
        """Get daily history through the documented date_sequence service.

        The official docs show THS_DS -> /date_sequence with indicator payloads.
        Indicator availability depends on the user's iFinD account; if the
        account lacks a field, the provider raises and DataAgent falls through
        to the next source.
        """
        end = datetime.now()
        start = end - timedelta(days=max(days * 2, days + 10, 10))
        payload = self._post(
            "date_sequence",
            {
                "codes": _to_ifind_code(stock_code),
                "startdate": start.strftime("%Y%m%d"),
                "enddate": end.strftime("%Y%m%d"),
                "functionpara": {"Days": "Tradedays", "Fill": "Previous", "Interval": "D"},
                "indipara": [
                    {"indicator": "ths_open_price_stock"},
                    {"indicator": "ths_high_price_stock"},
                    {"indicator": "ths_low_price_stock"},
                    {"indicator": "ths_close_price_stock"},
                    {"indicator": "ths_stock_short_name_stock"},
                ],
            },
        )
        rows = _rows_from_payload(payload)
        bars: list[StockBar] = []
        for row in rows:
            date = _pick(row, "time", "date", "日期", default="")
            close = _safe_float(_pick(row, "ths_close_price_stock", "close", "收盘价"))
            open_price = _safe_float(_pick(row, "ths_open_price_stock", "open", "开盘价"), close)
            high = _safe_float(_pick(row, "ths_high_price_stock", "high", "最高价"), max(open_price, close))
            low = _safe_float(_pick(row, "ths_low_price_stock", "low", "最低价"), min(open_price, close))
            if not date or close <= 0:
                continue
            bars.append(
                StockBar(
                    stock_code=stock_code,
                    date=str(date).split()[0],
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=0.0,
                    amount=0.0,
                    turnover=0.0,
                )
            )
        bars.sort(key=lambda item: item.date)
        return bars[-days:] if days > 0 else bars

    def get_quote(self, stock_code: str) -> StockQuote:
        """Build a quote from recent iFinD history plus optional name lookup."""
        bars = self.get_history(stock_code, days=5)
        if not bars:
            raise ValueError(f"No iFinD quote data found for {stock_code}")
        latest = bars[-1]
        previous = bars[-2] if len(bars) > 1 else latest
        change_pct = (latest.close - previous.close) / previous.close if previous.close else 0.0
        stock_name = self._lookup_name(stock_code) or stock_code
        return StockQuote(
            stock_code=stock_code,
            stock_name=stock_name,
            date=latest.date,
            price=latest.close,
            change_pct=change_pct,
            volume=latest.volume,
            amount=latest.amount,
            sector="",
        )

    def _lookup_name(self, stock_code: str) -> str:
        today = datetime.now().strftime("%Y%m%d")
        try:
            payload = self._post(
                "basic_data_service",
                {
                    "codes": _to_ifind_code(stock_code),
                    "indipara": [
                        {"indicator": "ths_stock_short_name_stock"},
                        {"indicator": "ths_close_price_stock", "indiparams": [today, "100", today]},
                    ],
                },
            )
        except Exception:
            return ""
        for row in _rows_from_payload(payload):
            name = str(_pick(row, "ths_stock_short_name_stock", "stock_name", "证券简称", default="") or "").strip()
            if name:
                return name
        return ""

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            headers={
                "Content-Type": "application/json",
                "access_token": self.access_token,
                "ifindlang": "cn",
            },
            json=body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("iFinD returned non-object JSON")
        error_code = payload.get("errorcode", payload.get("error_code", 0))
        if str(error_code) not in {"0", "0.0", "None"}:
            message = payload.get("errmsg") or payload.get("error_msg") or payload.get("message") or "unknown iFinD error"
            raise RuntimeError(f"iFinD API error {error_code}: {message}")
        return payload


def _to_ifind_code(stock_code: str) -> str:
    code = stock_code.strip().upper()
    if code.startswith(("SH", "SZ", "BJ")) and len(code) > 2:
        prefix = code[:2]
        digits = code[2:]
        if digits.isdigit():
            return f"{digits}.{prefix}"
    if "." in code:
        left, right = code.split(".", 1)
        suffix = right.upper()
        if suffix == "SS":
            suffix = "SH"
        if suffix == "XSHE":
            suffix = "SZ"
        if suffix in {"SH", "SZ", "BJ"}:
            return f"{left}.{suffix}"
        return code
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


def _rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    times = payload.get("time")
    rows: list[dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                rows.append(dict(item))
        return rows
    if not isinstance(data, dict):
        return rows
    for key in ("table", "tables"):
        nested = data.get(key)
        if isinstance(nested, list):
            return [dict(item) for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            nested_rows = _rows_from_column_dict(nested)
            if nested_rows:
                return nested_rows
    rows = _rows_from_column_dict(data)
    if times and isinstance(times, list):
        for index, value in enumerate(times[: len(rows)]):
            rows[index].setdefault("time", value)
    return rows


def _rows_from_column_dict(data: dict[str, Any]) -> list[dict[str, Any]]:
    max_len = 0
    for value in data.values():
        if isinstance(value, list):
            max_len = max(max_len, len(value))
    if max_len == 0:
        return [dict(data)] if data else []
    rows: list[dict[str, Any]] = []
    for index in range(max_len):
        row: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, list):
                row[key] = value[index] if index < len(value) else None
            else:
                row[key] = value
        rows.append(row)
    return rows


def _pick(row: dict[str, Any], *keys: str, default: Any = 0.0) -> Any:
    for key in keys:
        if key in row and row[key] not in {None, ""}:
            return row[key]
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number
