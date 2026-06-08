"""Dependency-light render helpers for future Textual widgets."""

from apps.tui.widgets.agent_panel import render_agent_management_panel, render_learning_progress
from apps.tui.widgets.dashboard import (
    render_agent_flow,
    render_decision_logs,
    render_provider_diagnostics,
    render_rankings,
    render_run_observability,
    render_status_bar,
    render_stock_board,
    render_todo_strip,
)

__all__ = [
    "render_agent_flow",
    "render_agent_management_panel",
    "render_decision_logs",
    "render_learning_progress",
    "render_provider_diagnostics",
    "render_rankings",
    "render_run_observability",
    "render_status_bar",
    "render_stock_board",
    "render_todo_strip",
]
