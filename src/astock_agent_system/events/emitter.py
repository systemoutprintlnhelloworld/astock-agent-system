"""Event emitter for Agent execution tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal

EventType = Literal[
    "run_start",
    "run_complete",
    "run_error",
    "stage_start",
    "stage_complete",
    "screening_start",
    "screening_complete",
    "analysis_start",
    "analysis_complete",
    "data_fetch_start",
    "data_fetch_complete",
    "agent_chain_step",
    "agent_start",
    "agent_step",
    "agent_complete",
    "agent_error",
    "decision_made",
    "trade_executed",
    "metric_updated",
    "llm_request",
    "llm_response",
    "data_fetched",
    "data_source_switched",
    "progress_update",
    "learning_experience_recorded",
    "learning_analysis_triggered",
    "learning_suggestion_generated",
    "memory_case_retrieved",
]


@dataclass(slots=True)
class AgentEvent:
    """Single event during Agent execution."""

    type: EventType
    timestamp: str
    run_id: str = ""
    agent_id: str = ""
    model: str = ""
    stage: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EventCallback = Callable[[AgentEvent], None]


class AgentEventEmitter:
    """Event emitter that broadcasts Agent execution events to subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[EventCallback] = []

    def subscribe(self, callback: EventCallback) -> None:
        """Register a callback to receive all events."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        """Remove a previously registered callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(
        self,
        event_type: EventType,
        run_id: str = "",
        agent_id: str = "",
        model: str = "",
        stage: str = "",
        **payload: Any,
    ) -> None:
        """Emit an event to all subscribers."""
        event = AgentEvent(
            type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=run_id,
            agent_id=agent_id,
            model=model,
            stage=stage,
            payload=payload,
        )
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception:
                pass

    def clear(self) -> None:
        """Remove all subscribers."""
        self._subscribers.clear()
