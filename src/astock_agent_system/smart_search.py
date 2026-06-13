"""Helpers for invoking the local smart-search CLI from Python.

Windows often installs ``smart-search`` as an npm ``.CMD`` shim. Resolving the
actual executable path before ``subprocess.run`` avoids ``WinError 2`` in long
running CLI sessions whose PATH lookup differs from the interactive shell.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


DEFAULT_SMART_SEARCH_CLI = "smart-search"


def resolve_smart_search_cli(cli_name: str | None = None) -> str:
    """Return the resolved smart-search executable path, or an empty string."""
    configured = (cli_name or os.getenv("SMART_SEARCH_CLI") or DEFAULT_SMART_SEARCH_CLI).strip()
    candidates = [configured]
    if os.name == "nt" and not configured.lower().endswith((".cmd", ".bat", ".exe")):
        candidates.extend([f"{configured}.cmd", f"{configured}.CMD", f"{configured}.exe"])
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return ""


def run_smart_search_search(query: str, *, timeout_seconds: int | float = 60) -> dict[str, Any]:
    """Run ``smart-search search`` and return a normalized JSON-ish payload."""
    return _run_json_command(
        ["search", query, "--validation", "fast", "--format", "json"],
        timeout_seconds=timeout_seconds,
    )


def run_smart_search_doctor(*, timeout_seconds: int | float = 20) -> dict[str, Any]:
    """Run ``smart-search doctor`` for local diagnostics without exposing keys."""
    return _run_json_command(["doctor", "--format", "json"], timeout_seconds=timeout_seconds)


def _run_json_command(args: list[str], *, timeout_seconds: int | float) -> dict[str, Any]:
    resolved = resolve_smart_search_cli()
    if not resolved:
        return {
            "status": "error",
            "error": "smart-search CLI not found on PATH; install/configure smart-search or set SMART_SEARCH_CLI.",
            "error_code": "E-SMART-SEARCH-NOT-FOUND",
            "command": [DEFAULT_SMART_SEARCH_CLI, *args],
            "resolved_path": "",
        }
    command = [resolved, *args]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "error",
            "error": f"smart-search timed out after {timeout_seconds}s: {exc}",
            "error_code": "E-SMART-SEARCH-TIMEOUT",
            "command": command,
            "resolved_path": resolved,
        }
    except OSError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "error_code": "E-SMART-SEARCH-SPAWN",
            "command": command,
            "resolved_path": resolved,
        }
    if result.returncode != 0:
        return {
            "status": "error",
            "error": result.stderr.strip() or f"smart-search exit code {result.returncode}",
            "error_code": "E-SMART-SEARCH-EXIT",
            "returncode": result.returncode,
            "command": command,
            "resolved_path": resolved,
            "stdout": result.stdout.strip()[:2000],
        }
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"content": result.stdout.strip()}
    if not isinstance(payload, dict):
        payload = {"content": str(payload)}
    payload.setdefault("status", "ok")
    payload.setdefault("command", command)
    payload.setdefault("resolved_path", resolved)
    payload.setdefault("returncode", result.returncode)
    return payload
