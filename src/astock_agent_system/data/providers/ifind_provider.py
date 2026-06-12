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
        """Get daily history through the documented THS_HQ HTTP service."""
        end = datetime.now()
        start = end - timedelta(days=max(days * 2, days + 10, 10))
        errors: list[str] = []
        for code, indicators in _history_request_variants(stock_code):
            try:
                payload = self._post(
                    "cmd_history_quotation",
                    {
                        "codes": code,
                        "indicators": indicators,
                        "startdate": start.strftime("%Y-%m-%d"),
                        "enddate": end.strftime("%Y-%m-%d"),
                        "functionpara": {"Currency": "MHB", "Fill": "Omit"},
                    },
                )
            except Exception as exc:
                errors.append(f"{code}/{indicators}: {exc}")
                continue
            bars = _bars_from_history_payload(payload, stock_code=stock_code)
            if bars:
                bars.sort(key=lambda item: item.date)
                return bars[-days:] if days > 0 else bars
        if errors:
            raise RuntimeError("iFinD history attempts failed: " + " | ".join(errors[-3:]))
        return []

    def get_quote(self, stock_code: str) -> StockQuote:
        """Build a quote from THS_RQ, falling back to recent history."""
        try:
            payload = self._post(
                "real_time_quotation",
                {
                    "codes": _to_ifind_code(stock_code),
                    "indicators": "open,high,low,latest,volume,amount",
                },
            )
            row = next(iter(_rows_from_payload(payload)), {})
            latest_price = _safe_float(_pick(row, "latest", "price", "close", "现价"))
            if latest_price > 0:
                previous_close = _safe_float(_pick(row, "preclose", "pre_close", "昨收"), latest_price)
                change_pct = (latest_price - previous_close) / previous_close if previous_close else 0.0
                stock_name = self._lookup_name(stock_code) or stock_code
                return StockQuote(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    date=str(_pick(row, "time", "date", default=datetime.now().strftime("%Y-%m-%d"))).split()[0],
                    price=latest_price,
                    change_pct=change_pct,
                    volume=_safe_float(_pick(row, "volume", "vol", "成交量")),
                    amount=_safe_float(_pick(row, "amount", "amt", "成交额")),
                    sector="",
                )
        except Exception:
            pass

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
        try:
            return self._post_once(endpoint, body)
        except Exception as exc:
            if self.refresh_token and _looks_like_token_error(exc):
                self.access_token = self._refresh_access_token()
                return self._post_once(endpoint, body)
            raise

    def _post_once(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
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

    def _refresh_access_token(self) -> str:
        response = requests.post(
            f"{self.base_url}/get_access_token",
            headers={"Content-Type": "application/json", "ifindlang": "cn"},
            json={"refresh_token": self.refresh_token},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("iFinD token refresh returned non-object JSON")
        token = _extract_access_token(payload)
        if not token:
            error_code = payload.get("errorcode", payload.get("error_code", ""))
            message = payload.get("errmsg") or payload.get("error_msg") or payload.get("message") or "missing access_token"
            raise RuntimeError(f"iFinD access token refresh failed {error_code}: {message}")
        return token


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


def _history_request_variants(stock_code: str) -> list[tuple[str, str]]:
    """Return iFinD THS_HQ request variants ordered from most to least specific."""

    indicator_sets = [
        "open,high,low,close,volume,amount",
        "open,high,low,close",
    ]
    variants: list[tuple[str, str]] = []
    for code in _candidate_ifind_codes(stock_code):
        for indicators in indicator_sets:
            item = (code, indicators)
            if item not in variants:
                variants.append(item)
    return variants


def _candidate_ifind_codes(stock_code: str) -> list[str]:
    """Try official suffix form plus raw/common vendor forms for live diagnostics."""

    raw = stock_code.strip().upper()
    normalized = _to_ifind_code(raw)
    digits = normalized.split(".", 1)[0] if "." in normalized else raw
    suffix = normalized.split(".", 1)[1] if "." in normalized else ""
    candidates = [normalized, raw]
    if suffix in {"SH", "SZ", "BJ"} and digits.isdigit():
        candidates.extend([digits, f"{suffix}{digits}"])
        if suffix == "SH":
            candidates.append(f"{digits}.SS")
        elif suffix == "SZ":
            candidates.extend([f"{digits}.XSHE"])
    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique


def _bars_from_history_payload(payload: dict[str, Any], *, stock_code: str) -> list[StockBar]:
    rows = _rows_from_payload(payload)
    bars: list[StockBar] = []
    for row in rows:
        date = _pick(row, "time", "date", "datetime", "trade_date", "日期", default="")
        close = _safe_float(_pick(row, "close", "ths_close_price_stock", "收盘价"))
        open_price = _safe_float(_pick(row, "open", "ths_open_price_stock", "开盘价"), close)
        high = _safe_float(_pick(row, "high", "ths_high_price_stock", "最高价"), max(open_price, close))
        low = _safe_float(_pick(row, "low", "ths_low_price_stock", "最低价"), min(open_price, close))
        volume = _safe_float(_pick(row, "volume", "vol", "成交量"))
        amount = _safe_float(_pick(row, "amount", "amt", "成交额"))
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
                volume=volume,
                amount=amount,
                turnover=0.0,
            )
        )
    return bars


def _rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("tables", "table"):
        rows = _rows_from_any(payload.get(key))
        if rows:
            return rows
    data = payload.get("data")
    times = payload.get("time")
    rows: list[dict[str, Any]] = []
    if isinstance(data, list):
        rows = _rows_from_list(data, payload)
        return _attach_times(rows, times)
    if not isinstance(data, dict):
        return rows
    for key in ("table", "tables"):
        nested = data.get(key)
        if isinstance(nested, list):
            return _attach_times(_rows_from_list(nested, payload), times)
        if isinstance(nested, dict):
            nested_rows = _rows_from_column_dict(nested)
            if nested_rows:
                return _attach_times(nested_rows, times)
    rows = _rows_from_column_dict(data)
    return _attach_times(rows, times)


def _rows_from_any(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        nested = value.get("table")
        if isinstance(nested, (dict, list)):
            return _rows_from_any(nested)
        return _rows_from_column_dict(value)
    if isinstance(value, list):
        return _rows_from_list(value, {})
    return []


def _rows_from_list(data: list[Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    if all(isinstance(item, dict) for item in data):
        rows: list[dict[str, Any]] = []
        for item in data:
            nested_rows = _rows_from_any(item.get("table") if isinstance(item, dict) and "table" in item else item)
            if isinstance(item, dict):
                nested_rows = _attach_times(nested_rows, item.get("time"))
                for row in nested_rows:
                    row.setdefault("thscode", item.get("thscode"))
            rows.extend(nested_rows or [dict(item)])
        return rows
    indicators = payload.get("indicators") or payload.get("indicator")
    if isinstance(indicators, str):
        indicator_names = [item.strip() for item in indicators.replace(";", ",").split(",") if item.strip()]
    elif isinstance(indicators, list):
        indicator_names = [str(item).strip() for item in indicators if str(item).strip()]
    else:
        indicator_names = []
    times = payload.get("time") if isinstance(payload.get("time"), list) else []
    if indicator_names and all(isinstance(item, list) for item in data):
        row_count = max((len(item) for item in data if isinstance(item, list)), default=0)
        rows: list[dict[str, Any]] = []
        for row_index in range(row_count):
            row: dict[str, Any] = {}
            if row_index < len(times):
                row["time"] = times[row_index]
            for col_index, name in enumerate(indicator_names):
                column = data[col_index] if col_index < len(data) and isinstance(data[col_index], list) else []
                row[name] = column[row_index] if row_index < len(column) else None
            rows.append(row)
        return rows
    return []


def _attach_times(rows: list[dict[str, Any]], times: Any) -> list[dict[str, Any]]:
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
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] not in {None, ""}:
            return row[key]
        normalized_key = _normalize_key(key)
        if normalized_key in normalized and normalized[normalized_key] not in {None, ""}:
            return normalized[normalized_key]
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _normalize_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _looks_like_token_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in ("401", "403", "token", "unauthorized", "forbidden", "鉴权", "权限", "过期"))


def _extract_access_token(payload: dict[str, Any]) -> str:
    for key in ("access_token", "accessToken", "token"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_access_token(data)
    rows = _rows_from_payload(payload)
    for row in rows:
        for key in ("access_token", "accessToken", "token"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""
