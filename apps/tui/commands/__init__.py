"""Slash command handlers for the AStock TUI."""

from apps.tui.commands.agent import handle_agent_command
from apps.tui.commands.slash import handle_slash_command

__all__ = ["handle_agent_command", "handle_slash_command"]
