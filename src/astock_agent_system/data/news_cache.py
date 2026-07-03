"""Local research/news cache for announcement and sentiment sources.

This module intentionally stays outside the market-data provider chain. It stores
research/news items returned by optional tools such as smart-search or iWencai
SkillHub so CLI/API views can replay what was found without implying those tools
are price/quote providers.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT


DEFAULT_NEWS_CACHE_PATH = PROJECT_ROOT / "data" / "runtime" / "news_research_cache.jsonl"

_SECRET_HINTS = ("token", "password", "secret", "api_key", "access_token", "refresh_token", "authorization")


def news_cache_path() -> Path:
    """Return the active JSONL cache path for research/news items."""

    raw_path = os.getenv("ASTOCK_NEWS_CACHE_PATH", "").strip()
    return Path(raw_path) if raw_path else DEFAULT_NEWS_CACHE_PATH


def redact_news_value(value: Any) -> Any:
    """Redact secrets before persisting research tool output."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(hint in str(key).lower() for hint in _SECRET_HINTS):
                redacted[str(key)] = "***REDACTED***" if item else ""
            else:
                redacted[str(key)] = redact_news_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_news_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_news_value(item) for item in value]
    if isinstance(value, str):
        text = value
        for marker in (
            "Bearer ",
            "Token ",
            "access_token=",
            "refresh_token=",
            "api_key=",
            "password=",
            "authorization=",
            "Authorization=",
            "authorization:",
            "Authorization:",
        ):
            if marker in text:
                head, _, tail = text.partition(marker)
                token, sep, rest = tail.partition(" ")
                text = f"{head}{marker}***REDACTED***{sep}{rest}" if token else text
        return text[:2000]
    return value


def append_news_cache(
    *,
    source: str,
    query: str,
    status: str,
    stock_code: str = "",
    stock_name: str = "",
    skill: str = "",
    items: list[dict[str, Any]] | None = None,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Append one research/news cache row and return the stored item."""

    item = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": str(source or ""),
        "query": str(query or ""),
        "status": str(status or ""),
        "stock_code": str(stock_code or ""),
        "stock_name": str(stock_name or ""),
        "skill": str(skill or ""),
        "items": redact_news_value(items or []),
        "reason": str(reason or "")[:1000],
        "metadata": redact_news_value(metadata or {}),
    }
    target = Path(path) if path else news_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps(redact_news_value(item), ensure_ascii=False, default=str) + "\n")
    return item


def load_news_cache(
    *,
    limit: int = 100,
    source: str = "",
    stock_code: str = "",
    status: str = "",
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Load recent research/news cache rows from newest to oldest."""

    target = Path(path) if path else news_cache_path()
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if source and str(item.get("source", "")) != source:
                continue
            if stock_code and str(item.get("stock_code", "")) != stock_code:
                continue
            if status and str(item.get("status", "")) != status:
                continue
            rows.append(redact_news_value(item))
    rows = rows[-max(0, int(limit or 0)) :] if limit else rows
    return list(reversed(rows))


def summarize_news_cache(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact source/status counts for cached research/news rows."""

    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_stock: dict[str, int] = {}
    item_count = 0
    for item in items:
        source = str(item.get("source", "") or "unknown")
        status = str(item.get("status", "") or "unknown")
        stock_code = str(item.get("stock_code", "") or "market")
        by_source[source] = by_source.get(source, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_stock[stock_code] = by_stock.get(stock_code, 0) + 1
        raw_items = item.get("items", []) if isinstance(item.get("items"), list) else []
        item_count += len(raw_items)
    return {
        "total": len(items),
        "item_count": item_count,
        "by_source": by_source,
        "by_status": by_status,
        "by_stock": by_stock,
    }
