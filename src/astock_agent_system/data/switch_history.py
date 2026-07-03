"""Persistent datasource switch/attempt history for CLI and backend views."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT


DEFAULT_SWITCH_HISTORY_PATH = PROJECT_ROOT / "data" / "runtime" / "datasource_switch_history.jsonl"

_SECRET_KEY_HINTS = ("token", "password", "secret", "api_key", "access_token", "refresh_token")


def switch_history_path() -> Path:
    """Return the active persistent datasource history path."""

    raw_path = os.getenv("ASTOCK_DATASOURCE_HISTORY_PATH", "").strip()
    return Path(raw_path) if raw_path else DEFAULT_SWITCH_HISTORY_PATH


def redact_history_value(value: Any) -> Any:
    """Redact secrets before writing provider details to disk."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(hint in str(key).lower() for hint in _SECRET_KEY_HINTS):
                redacted[str(key)] = "***REDACTED***" if item else ""
            else:
                redacted[str(key)] = redact_history_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_history_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_history_value(item) for item in value]
    if isinstance(value, str):
        text = value
        for marker in ("Bearer ", "Token ", "access_token=", "refresh_token=", "api_key=", "password="):
            if marker in text:
                head, _, tail = text.partition(marker)
                token, sep, rest = tail.partition(" ")
                text = f"{head}{marker}***REDACTED***{sep}{rest}" if token else text
        return text[:500]
    return value


def append_switch_history(
    *,
    source: str,
    operation: str,
    status: str,
    detail: str = "",
    run_id: str = "",
    agent_id: str = "",
    model: str = "",
    stock_code: str = "",
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Append one datasource attempt/switch record and return the stored item."""

    item = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "agent_id": agent_id,
        "model": model,
        "source": str(source or ""),
        "operation": str(operation or ""),
        "status": str(status or ""),
        "stock_code": str(stock_code or ""),
        "detail": str(detail or "")[:500],
    }
    target = Path(path) if path else switch_history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps(redact_history_value(item), ensure_ascii=False, default=str) + "\n")
    return item


def load_switch_history(
    *,
    limit: int = 100,
    source: str = "",
    operation: str = "",
    status: str = "",
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Read recent datasource history records from newest to oldest."""

    target = Path(path) if path else switch_history_path()
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
            if operation and str(item.get("operation", "")) != operation:
                continue
            if status and str(item.get("status", "")) != status:
                continue
            rows.append(redact_history_value(item))
    rows = rows[-max(0, int(limit or 0)) :] if limit else rows
    return list(reversed(rows))


def summarize_switch_history(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact counts for datasource history records."""

    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_operation: dict[str, int] = {}
    for item in items:
        source = str(item.get("source", "") or "unknown")
        status = str(item.get("status", "") or "unknown")
        operation = str(item.get("operation", "") or "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_operation[operation] = by_operation.get(operation, 0) + 1
    return {"total": len(items), "by_source": by_source, "by_status": by_status, "by_operation": by_operation}
