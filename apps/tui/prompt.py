"""Prompt-toolkit integration for command completion and history."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory


class SlashCommandCompleter(Completer):
    """Tab completion for slash commands and their arguments."""

    COMMANDS = {
        "/help": [],
        "/?": [],
        "/status": [],
        "/config": ["show", "test-llm"],
        "/models": ["set"],
        "/workflow": ["auto", "daily", "offline", "review"],
        "/start": ["--offline", "--models", "--max-count", "--days", "--foreground"],
        "/providers": [],
        "/dashboard": ["overview", "providers", "rankings", "stocks", "decisions", "flow", "agent", "learning"],
        "/agent": ["list", "view", "edit", "backup", "learning"],
        "/compact": [],
        "/theme": ["dark", "light"],
        "/lang": ["zh-CN", "en-US"],
        "/language": ["zh-CN", "en-US"],
        "/permission": ["ask", "auto", "deny"],
        "/sandbox": ["read-only", "workspace-write"],
        "/attachments": ["show", "preview"],
        "/history": [],
        "/memory": [],
        "/exit": [],
    }

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Generate completions for the current input."""
        text = document.text_before_cursor
        words = text.split()
        
        # No input yet - suggest all commands
        if not words or not text:
            for cmd in sorted(self.COMMANDS.keys()):
                yield Completion(cmd, start_position=0, display=cmd)
            return
        
        # Complete command name
        if len(words) == 1 and not text.endswith(" "):
            prefix = words[0].lower()
            for cmd in sorted(self.COMMANDS.keys()):
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix), display=cmd)
            return
        
        # Complete subcommands/arguments
        if len(words) >= 1:
            cmd = words[0].lower()
            if cmd not in self.COMMANDS:
                return
            
            subcommands = self.COMMANDS[cmd]
            if not subcommands:
                return
            
            # If we're still typing a word, complete it
            if not text.endswith(" "):
                prefix = words[-1].lower()
                for sub in subcommands:
                    if sub.lower().startswith(prefix):
                        yield Completion(sub, start_position=-len(prefix), display=sub)
            else:
                # Show all available subcommands
                for sub in subcommands:
                    yield Completion(sub, start_position=0, display=sub)


def create_prompt_session(history_file: Path | None = None) -> PromptSession[str]:
    """Create a prompt_toolkit session with history and completion."""
    if history_file is None:
        history_file = Path("data/runtime/tui_history.txt")
    
    history_file.parent.mkdir(parents=True, exist_ok=True)
    
    return PromptSession(
        history=FileHistory(str(history_file)),
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        enable_history_search=True,
    )
