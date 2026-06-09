"""Experience collection and lightweight learning suggestions for agents.

This module records paper-trading outcomes into local JSONL files and derives
human-reviewable suggestions for Agent Markdown descriptors. It does not
auto-trade or silently rewrite strategy files.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from astock_agent_system.agent_descriptor import AGENT_CONFIG_DIR


LEARNING_DIR = AGENT_CONFIG_DIR / "learning"
EXPERIENCE_LOG_PATH = LEARNING_DIR / "experience_log.jsonl"
LEARNING_STATE_PATH = LEARNING_DIR / "learning_state.json"
SUGGESTIONS_PATH = LEARNING_DIR / "learning_suggestions.json"
STRATEGY_EVOLUTION_PATH = LEARNING_DIR / "strategy_evolution.md"
DEFAULT_LEARNING_THRESHOLD = 30


@dataclass(slots=True)
class LearningSuggestion:
    """One suggested descriptor adjustment awaiting human review."""

    agent_id: str
    section: str
    metric: str
    current_value: float | str | None
    suggested_value: float | str | None
    reason: str
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LearningSummary:
    """Aggregated status for TUI/API display."""

    total_experiences: int
    threshold: int
    progress: int
    ready: bool
    last_analyzed_count: int = 0
    success_rate: float = 0.0
    average_return_pct: float = 0.0
    suggestions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def append_experience(entry: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Append one normalized experience entry to the JSONL log."""
    target = path or EXPERIENCE_LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(entry)
    normalized.setdefault("recorded_at", datetime.now().isoformat(timespec="seconds"))
    normalized.setdefault("experience_id", _stable_id(normalized))
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return normalized


def load_experiences(path: Path | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    target = path or EXPERIENCE_LOG_PATH
    if not target.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries[-limit:] if limit is not None else entries


def record_competition_experience(payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Record one experience row per decision from a competition result."""
    agents = payload.get("agents", [])
    if not isinstance(agents, list):
        return {"recorded": 0, "path": str(path or EXPERIENCE_LOG_PATH)}
    recorded = 0
    run_date = str(payload.get("run_date", ""))
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        decisions = agent.get("decisions", [])
        if not isinstance(decisions, list):
            decisions = []
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            entry = _experience_from_decision(run_date, agent, decision)
            append_experience(entry, path)
            recorded += 1
    return {"recorded": recorded, "path": str(path or EXPERIENCE_LOG_PATH)}


def get_learning_status(
    path: Path | None = None,
    state_path: Path | None = None,
    threshold: int = DEFAULT_LEARNING_THRESHOLD,
) -> dict[str, Any]:
    entries = load_experiences(path)
    state = _load_state(state_path or LEARNING_STATE_PATH)
    summary = _summarize(entries, threshold=threshold, last_analyzed_count=int(state.get("last_analyzed_count", 0)))
    return summary.to_dict()


def load_learning_suggestions(path: Path | None = None) -> dict[str, Any]:
    """Load the latest human-reviewable learning suggestions."""
    target = path or SUGGESTIONS_PATH
    default_payload: dict[str, Any] = {
        "analyzed_at": "",
        "analyzed_count": 0,
        "threshold": DEFAULT_LEARNING_THRESHOLD,
        "suggestions": [],
    }
    if not target.exists():
        return default_payload
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_payload
    if not isinstance(payload, dict):
        return default_payload
    suggestions = payload.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    return {
        "analyzed_at": str(payload.get("analyzed_at", "")),
        "analyzed_count": int(payload.get("analyzed_count", 0) or 0),
        "threshold": int(payload.get("threshold", DEFAULT_LEARNING_THRESHOLD) or DEFAULT_LEARNING_THRESHOLD),
        "suggestions": [item for item in suggestions if isinstance(item, dict)],
    }


def trigger_learning_if_ready(
    path: Path | None = None,
    state_path: Path | None = None,
    suggestions_path: Path | None = None,
    evolution_path: Path | None = None,
    threshold: int = DEFAULT_LEARNING_THRESHOLD,
    force: bool = False,
) -> dict[str, Any]:
    """Analyze recent experiences and write suggestions when threshold is met."""
    entries = load_experiences(path)
    state_target = state_path or LEARNING_STATE_PATH
    state = _load_state(state_target)
    last_count = int(state.get("last_analyzed_count", 0))
    ready = force or len(entries) - last_count >= threshold
    if not ready:
        return get_learning_status(path, state_target, threshold)

    suggestions = generate_learning_suggestions(entries[-threshold:] if len(entries) >= threshold else entries)
    payload = {
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "analyzed_count": len(entries),
        "threshold": threshold,
        "suggestions": [item.to_dict() for item in suggestions],
    }
    target = suggestions_path or SUGGESTIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_strategy_evolution(payload, evolution_path or STRATEGY_EVOLUTION_PATH)
    _save_state(state_target, {"last_analyzed_count": len(entries), "last_analyzed_at": payload["analyzed_at"]})
    status = get_learning_status(path, state_target, threshold)
    status["suggestions"] = payload["suggestions"]
    return status


def generate_learning_suggestions(entries: list[dict[str, Any]]) -> list[LearningSuggestion]:
    if not entries:
        return []
    suggestions: list[LearningSuggestion] = []
    success_rate = _success_rate(entries)
    avg_return = _average_return(entries)
    ma_stats = _signal_stats(entries, "MA5")
    rsi_stats = _signal_stats(entries, "RSI")

    if ma_stats["count"] >= 5 and ma_stats["success_rate"] < 0.55:
        suggestions.append(
            LearningSuggestion(
                agent_id="technical_analyst",
                section="rules.ma_cross_bonus",
                metric="ma_signal_success_rate",
                current_value="from descriptor",
                suggested_value="lower_by_0.02",
                reason=f"MA相关理由在最近样本成功率约 {ma_stats['success_rate']:.1%}，建议降低均线信号权重。",
                confidence=0.62,
            )
        )
    if rsi_stats["count"] >= 5 and rsi_stats["success_rate"] > 0.65:
        suggestions.append(
            LearningSuggestion(
                agent_id="technical_analyst",
                section="rules.rsi_healthy_bonus",
                metric="rsi_signal_success_rate",
                current_value="from descriptor",
                suggested_value="raise_by_0.01",
                reason=f"RSI相关理由在最近样本成功率约 {rsi_stats['success_rate']:.1%}，可小幅提高RSI健康区间权重。",
                confidence=0.58,
            )
        )
    if success_rate < 0.45 or avg_return < 0:
        suggestions.append(
            LearningSuggestion(
                agent_id="risk_manager",
                section="risk_profile",
                metric="portfolio_outcome",
                current_value="current",
                suggested_value="tighten",
                reason=f"最近样本成功率 {success_rate:.1%}，平均收益 {avg_return:.2f}%，建议人工复核仓位和止损阈值。",
                confidence=0.55,
            )
        )
    if not suggestions:
        suggestions.append(
            LearningSuggestion(
                agent_id="master_agent",
                section="learning_notes",
                metric="stability",
                current_value=None,
                suggested_value="keep_current",
                reason=f"最近样本成功率 {success_rate:.1%}，平均收益 {avg_return:.2f}%，暂不建议自动调整。",
                confidence=0.5,
            )
        )
    return suggestions


def _experience_from_decision(run_date: str, agent: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return_pct = float(agent.get("total_return", 0.0) or 0.0) * 100.0
    return {
        "date": run_date,
        "agent_id": agent.get("agent_id", ""),
        "llm_model": agent.get("llm_model", ""),
        "stock_code": decision.get("stock_code", ""),
        "agent_outputs": {
            "final_decision": decision.get("action", decision.get("effective_action", "")),
            "position_size": decision.get("position_size", 0.0),
            "decision": decision,
        },
        "outcome": {
            "return_pct": round(return_pct, 6),
            "daily_pnl": agent.get("daily_pnl", 0.0),
            "result": "success" if return_pct > 0 else "fail" if return_pct < 0 else "flat",
        },
    }


def _summarize(entries: list[dict[str, Any]], threshold: int, last_analyzed_count: int) -> LearningSummary:
    total = len(entries)
    return LearningSummary(
        total_experiences=total,
        threshold=threshold,
        progress=min(threshold, max(0, total - last_analyzed_count)),
        ready=total - last_analyzed_count >= threshold,
        last_analyzed_count=last_analyzed_count,
        success_rate=round(_success_rate(entries), 6),
        average_return_pct=round(_average_return(entries), 6),
    )


def _signal_stats(entries: list[dict[str, Any]], keyword: str) -> dict[str, Any]:
    matched = [entry for entry in entries if keyword in json.dumps(entry.get("agent_outputs", {}), ensure_ascii=False)]
    return {"count": len(matched), "success_rate": _success_rate(matched)}


def _success_rate(entries: list[dict[str, Any]]) -> float:
    if not entries:
        return 0.0
    wins = 0
    for entry in entries:
        outcome = entry.get("outcome", {}) if isinstance(entry.get("outcome", {}), dict) else {}
        try:
            wins += 1 if float(outcome.get("return_pct", 0.0)) > 0 else 0
        except (TypeError, ValueError):
            continue
    return wins / len(entries)


def _average_return(entries: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for entry in entries:
        outcome = entry.get("outcome", {}) if isinstance(entry.get("outcome", {}), dict) else {}
        try:
            values.append(float(outcome.get("return_pct", 0.0)))
        except (TypeError, ValueError):
            continue
    return sum(values) / len(values) if values else 0.0


def _append_strategy_evolution(payload: dict[str, Any], path: Path = STRATEGY_EVOLUTION_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"\n## {payload['analyzed_at']} 学习分析", ""]
    for suggestion in payload.get("suggestions", []):
        lines.append(f"- `{suggestion['agent_id']}` / {suggestion['section']}: {suggestion['reason']}")
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stable_id(entry: dict[str, Any]) -> str:
    raw = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
