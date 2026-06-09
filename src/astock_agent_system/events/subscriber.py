"""Event subscribers for different output targets."""

from __future__ import annotations

import json
from typing import Protocol

from astock_agent_system.events.emitter import AgentEvent


class EventSubscriber(Protocol):
    """Protocol for event subscribers."""

    def __call__(self, event: AgentEvent) -> None:
        """Handle a single event."""
        ...


class ConsoleSubscriber:
    """Simple console subscriber for debugging."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def __call__(self, event: AgentEvent) -> None:
        """Print event to console."""
        if self.verbose:
            print(json.dumps(event.to_dict(), ensure_ascii=False, indent=2))
        else:
            timestamp = event.timestamp.split("T")[1][:12]
            stage_info = f" [{event.stage}]" if event.stage else ""
            agent_info = f" {event.agent_id}" if event.agent_id else ""
            print(f"[{timestamp}]{stage_info}{agent_info} {event.type}: {event.payload.get('message', '')}")
