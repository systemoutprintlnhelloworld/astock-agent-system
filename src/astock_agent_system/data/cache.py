"""Local market-data cache for provider responses.

The cache is intentionally file-based and dependency-light. It reduces repeat
calls to online providers such as Tushare while keeping live quote data fresh.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT
from astock_agent_system.models import FinancialSnapshot, StockBar, StockQuote


HISTORY_TTL_SECONDS = 7 * 24 * 60 * 60
QUOTE_TTL_SECONDS = 5 * 60
FINANCIAL_TTL_SECONDS = 24 * 60 * 60


class MarketDataCache:
    """Small JSON cache for history, quote and financial provider data."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PROJECT_ROOT / "data" / "market_cache"

    def get_history(self, stock_code: str, days: int) -> list[StockBar] | None:
        payload = self._read("history", {"stock_code": stock_code, "days": int(days)}, HISTORY_TTL_SECONDS)
        if not isinstance(payload, list):
            return None
        try:
            return [StockBar(**item) for item in payload if isinstance(item, dict)]
        except TypeError:
            return None

    def set_history(self, stock_code: str, days: int, bars: list[StockBar]) -> None:
        self._write("history", {"stock_code": stock_code, "days": int(days)}, [_to_dict(bar) for bar in bars])

    def get_quote(self, stock_code: str) -> StockQuote | None:
        payload = self._read("quote", {"stock_code": stock_code}, QUOTE_TTL_SECONDS)
        if not isinstance(payload, dict):
            return None
        try:
            return StockQuote(**payload)
        except TypeError:
            return None

    def set_quote(self, stock_code: str, quote: StockQuote) -> None:
        self._write("quote", {"stock_code": stock_code}, _to_dict(quote))

    def get_financial(self, stock_code: str) -> FinancialSnapshot | None:
        payload = self._read("financial", {"stock_code": stock_code}, FINANCIAL_TTL_SECONDS)
        if not isinstance(payload, dict):
            return None
        try:
            return FinancialSnapshot(**payload)
        except TypeError:
            return None

    def set_financial(self, stock_code: str, snapshot: FinancialSnapshot) -> None:
        self._write("financial", {"stock_code": stock_code}, _to_dict(snapshot))

    def _read(self, namespace: str, key: dict[str, Any], ttl_seconds: int) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(str(envelope.get("created_at", "")))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age > ttl_seconds:
                return None
            return envelope.get("data")
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return None

    def _write(self, namespace: str, key: dict[str, Any], data: Any) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "namespace": namespace,
            "key": key,
            "data": data,
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _path(self, namespace: str, key: dict[str, Any]) -> Path:
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
        return self.root / namespace / f"{digest}.json"


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {}
