"""Readonly Agent memory facade for model-driven benchmark systems."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from astock_agent_system.config import Settings, load_settings


class AgentMemoryStore:
    """Read memory cases from persisted decisions when storage is available.

    Benchmark systems must stay isolated: callers query one ``agent_id`` at a
    time and the store never mixes cases across model-driven accounts.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def list_cases(self, agent_id: str, *, limit: int = 20, stock_code: str = "", outcome: str = "") -> list[dict[str, Any]]:
        if not agent_id:
            return []
        try:
            from astock_agent_system.storage.mongo_client import MongoClient

            decisions = MongoClient(self.settings).get_agent_decisions(agent_id=agent_id, limit=limit)
        except Exception:
            decisions = []

        cases: list[dict[str, Any]] = []
        for index, decision in enumerate(decisions):
            case = _case_from_decision(agent_id, decision, index)
            if stock_code and case.get("stock_code") != stock_code:
                continue
            if outcome and case.get("outcome") != outcome:
                continue
            cases.append(case)
            if len(cases) >= max(1, limit):
                break
        return cases


def _case_from_decision(agent_id: str, decision: dict[str, Any], index: int) -> dict[str, Any]:
    timestamp = decision.get("timestamp") or decision.get("decision_date") or ""
    if isinstance(timestamp, datetime):
        timestamp_text = timestamp.isoformat()
    else:
        timestamp_text = str(timestamp)
    action = str(decision.get("action", "HOLD"))
    confidence = _to_float(decision.get("confidence"), 0.0)
    pnl_pct = _to_float(decision.get("pnl_pct", decision.get("return_pct")), 0.0)
    outcome = str(decision.get("outcome", "unknown"))
    if outcome == "unknown" and pnl_pct:
        outcome = "successful" if pnl_pct > 0 else "failed"
    return {
        "id": str(decision.get("_id", f"{agent_id}-{index}")),
        "agent_id": agent_id,
        "llm_model": str(decision.get("llm_model", "")),
        "stock_code": str(decision.get("stock_code", "")),
        "stock_name": str(decision.get("stock_name", "")),
        "decision_date": timestamp_text,
        "action": action,
        "reason": _reason_text(decision),
        "outcome": outcome,
        "pnl_pct": pnl_pct,
        "tags": _tags_for_decision(action, confidence, outcome),
        "raw": _json_safe_dict(decision),
    }


def _reason_text(decision: dict[str, Any]) -> str:
    reasons = decision.get("reasons")
    if isinstance(reasons, list) and reasons:
        return "；".join(str(item) for item in reasons[:3])
    return str(decision.get("reason", decision.get("summary", "")))


def _tags_for_decision(action: str, confidence: float, outcome: str) -> list[str]:
    tags = [action.lower()]
    if confidence >= 0.75:
        tags.append("high-confidence")
    if outcome and outcome != "unknown":
        tags.append(outcome)
    return tags


def _json_safe_dict(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "_id":
            safe[key] = str(value)
        elif isinstance(value, datetime):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
