"""iWencai SkillHub integration boundary.

The SkillHub CLI is optional and installed outside this repository. This module
does not pretend to be a market-data provider; it is a research/news source
adapter for announcement-search style skills when the local CLI and API key are
available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


INSTALLER_URL = "https://www.iwencai.com/skillhub/static/0.0.4/download_and_install.sh"
REQUIRED_SKILL = "announcement-search"
OFFICIAL_CLI = "iwencai-skillhub-cli"
LEGACY_CLI = "skillhub"
PROJECT_SKILL_INSTALL_DIR = "data/runtime/skillhub/skills"


@dataclass(frozen=True, slots=True)
class SkillHubCli:
    command_prefix: list[str]
    display_path: str
    bridge: str = "native"


@dataclass(slots=True)
class SkillHubAttempt:
    command: list[str]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": _redact_command(self.command),
            "exit_code": self.exit_code,
            "stdout": _redact_text(self.stdout)[:2000],
            "stderr": _redact_text(self.stderr)[:2000],
            "error": _redact_text(self.error)[:1000],
        }


@dataclass(slots=True)
class SkillHubSearchResult:
    status: str
    query: str
    items: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[SkillHubAttempt] = field(default_factory=list)
    reason: str = ""
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "items": self.items,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "reason": self.reason,
            "next_steps": self.next_steps,
        }


class IwencaiSkillHub:
    """Thin wrapper around the local iWencai SkillHub CLI."""

    def __init__(self, *, base_url: str, api_key: str, cli: str = OFFICIAL_CLI, timeout_seconds: float = 20.0) -> None:
        self.base_url = (base_url or "https://openapi.iwencai.com").rstrip("/")
        self.api_key = api_key or ""
        self.cli = cli or OFFICIAL_CLI
        self.timeout_seconds = timeout_seconds

    def status(self) -> dict[str, Any]:
        cli = _resolve_cli(self.cli)
        legacy_path = shutil.which(LEGACY_CLI)
        official_path = shutil.which(OFFICIAL_CLI)
        iwencai_path = shutil.which("iwencai")
        return {
            "status": "ok" if cli and self.api_key else "needs_config",
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "configured_cli": self.cli,
            "skillhub_found": bool(cli),
            "skillhub_path": cli.display_path if cli else "",
            "skillhub_bridge": cli.bridge if cli else "",
            "official_cli_found": bool(official_path),
            "official_cli_path": official_path or "",
            "legacy_skillhub_found": bool(legacy_path),
            "legacy_skillhub_path": legacy_path or "",
            "iwencai_cli_found": bool(iwencai_path),
            "iwencai_cli_path": iwencai_path or "",
            "required_skill": REQUIRED_SKILL,
            "installer_url": INSTALLER_URL,
            "install_command": f"{OFFICIAL_CLI} install {REQUIRED_SKILL}",
            "project_install_command": f"{OFFICIAL_CLI} --dir {PROJECT_SKILL_INSTALL_DIR} install {REQUIRED_SKILL} --force",
            "next_steps": self.next_steps(cli_found=bool(cli)),
        }

    def next_steps(self, *, cli_found: bool | None = None) -> list[str]:
        if cli_found is None:
            cli_found = bool(_resolve_cli(self.cli))
        steps: list[str] = []
        if not cli_found:
            steps.append(f"Install SkillHub from the official installer: {INSTALLER_URL}")
        if not self.api_key:
            steps.append("Save IWENCAI_API_KEY locally with datasource configure-iwencai or shell profile.")
        steps.append(f"Install or verify the SkillHub skill: {OFFICIAL_CLI} install {REQUIRED_SKILL}")
        steps.append(
            f"For project-local installs, run: {OFFICIAL_CLI} --dir {PROJECT_SKILL_INSTALL_DIR} "
            f"install {REQUIRED_SKILL} --force"
        )
        return steps

    def search_announcements(self, *, stock_code: str = "", query: str = "", limit: int = 5) -> SkillHubSearchResult:
        query_text = _build_query(stock_code=stock_code, query=query)
        cli = _resolve_cli(self.cli)
        if not self.api_key:
            return SkillHubSearchResult(
                status="skipped",
                query=query_text,
                reason="IWENCAI_API_KEY is not configured.",
                next_steps=self.next_steps(cli_found=bool(cli)),
            )
        if not cli:
            return SkillHubSearchResult(
                status="skipped",
                query=query_text,
                reason="SkillHub CLI is not installed or not on PATH.",
                next_steps=self.next_steps(cli_found=False),
            )

        commands = _candidate_commands(cli, query_text, limit)
        attempts: list[SkillHubAttempt] = []
        env = self._env()
        for command in commands:
            attempt = SkillHubAttempt(command=command)
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                    env=env,
                )
                attempt.exit_code = completed.returncode
                attempt.stdout = completed.stdout or ""
                attempt.stderr = completed.stderr or ""
                attempts.append(attempt)
                if completed.returncode == 0:
                    return SkillHubSearchResult(
                        status="ok",
                        query=query_text,
                        items=_parse_items(completed.stdout),
                        attempts=attempts,
                    )
            except Exception as exc:  # pragma: no cover - external CLI guard
                attempt.error = str(exc)
                attempts.append(attempt)
        return SkillHubSearchResult(
            status="error",
            query=query_text,
            attempts=attempts,
            reason=f"SkillHub CLI did not return a successful {REQUIRED_SKILL} result.",
            next_steps=[
                f"Run {OFFICIAL_CLI} install {REQUIRED_SKILL} and retry.",
                f"For project-local installs, run {OFFICIAL_CLI} --dir {PROJECT_SKILL_INSTALL_DIR} install {REQUIRED_SKILL} --force.",
                "If the official CLI syntax differs, set IWENCAI_SKILLHUB_CLI to the wrapper command/path used on this machine.",
            ],
        )

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["IWENCAI_BASE_URL"] = self.base_url
        env["IWENCAI_API_KEY"] = self.api_key
        env["WSLENV"] = _merge_wslenv(
            env.get("WSLENV", ""),
            ["IWENCAI_BASE_URL/u", "IWENCAI_API_KEY/u"],
        )
        return env


def _build_query(*, stock_code: str, query: str) -> str:
    parts = [item.strip() for item in (stock_code, query or "公告") if item and item.strip()]
    return " ".join(parts) or "A股 公告"


def _resolve_cli(configured_cli: str) -> SkillHubCli | None:
    for name in _unique_cli_names(configured_cli):
        path = shutil.which(name)
        if path:
            return SkillHubCli(command_prefix=[path], display_path=path)
    return _resolve_wsl_cli()


def _unique_cli_names(configured_cli: str) -> list[str]:
    names: list[str] = []
    for name in (configured_cli, OFFICIAL_CLI, LEGACY_CLI, "iwencai"):
        clean = (name or "").strip()
        if clean and clean not in names:
            names.append(clean)
    return names


def _resolve_wsl_cli() -> SkillHubCli | None:
    if os.name != "nt":
        return None
    bash_path = shutil.which("bash")
    if not bash_path:
        return None
    try:
        completed = subprocess.run(
            [
                bash_path,
                "-lc",
                (
                    f'export PATH="$HOME/.local/bin:$PATH"; command -v {OFFICIAL_CLI} || '
                    f'{{ if [ -x "$HOME/.local/bin/{OFFICIAL_CLI}" ]; then '
                    f'printf "%s\\n" "$HOME/.local/bin/{OFFICIAL_CLI}"; fi; }}'
                ),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:  # pragma: no cover - host shell availability guard
        return None
    cli_path = (completed.stdout or "").strip().splitlines()[-1:] or []
    if cli_path:
        return SkillHubCli(command_prefix=[bash_path, "-lc"], display_path=f"wsl:{cli_path[0]}", bridge="wsl")
    return None


def _merge_wslenv(current: str, entries: list[str]) -> str:
    """Mark iWencai variables for Windows-to-WSL propagation without embedding secrets in commands."""

    parts = [item for item in (current or "").split(":") if item]
    for entry in entries:
        if entry not in parts:
            parts.append(entry)
    return ":".join(parts)


def _candidate_commands(cli: SkillHubCli, query: str, limit: int) -> list[list[str]]:
    limit_text = str(max(1, limit))
    if cli.bridge == "wsl":
        return [
            [*cli.command_prefix, _wsl_command("run", REQUIRED_SKILL, "--query", query, "--limit", limit_text)],
            [*cli.command_prefix, _wsl_command("skill", "run", REQUIRED_SKILL, "--query", query, "--limit", limit_text)],
            [*cli.command_prefix, _wsl_command(REQUIRED_SKILL, "--query", query, "--limit", limit_text)],
        ]
    return [
        [*cli.command_prefix, "run", REQUIRED_SKILL, "--query", query, "--limit", limit_text],
        [*cli.command_prefix, "skill", "run", REQUIRED_SKILL, "--query", query, "--limit", limit_text],
        [*cli.command_prefix, REQUIRED_SKILL, "--query", query, "--limit", limit_text],
    ]


def _wsl_command(*parts: str) -> str:
    quoted = " ".join(_shell_quote(part) for part in parts)
    return f'export PATH="$HOME/.local/bin:$PATH"; {OFFICIAL_CLI} {quoted}'


def _shell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _parse_items(stdout: str) -> list[dict[str, Any]]:
    text = (stdout or "").strip()
    if not text:
        return []
    try:
        import json

        payload = json.loads(text)
    except Exception:
        return [{"text": line.strip()} for line in text.splitlines() if line.strip()][:20]
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "announcements"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item if isinstance(item, dict) else {"text": str(item)} for item in value]
        return [payload]
    if isinstance(payload, list):
        return [item if isinstance(item, dict) else {"text": str(item)} for item in payload]
    return [{"text": str(payload)}]


def _redact_command(command: list[str]) -> list[str]:
    return [_redact_text(part) for part in command]


def _redact_text(text: str) -> str:
    value = text or ""
    for name in ("IWENCAI_API_KEY", "api_key", "token", "Authorization"):
        if name in value:
            value = value.replace(name, f"{name[:4]}***")
    return value
