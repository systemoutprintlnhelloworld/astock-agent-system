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
from pathlib import Path
from typing import Any
from urllib.parse import quote


INSTALLER_URL = "https://www.iwencai.com/skillhub/static/0.0.4/download_and_install.sh"
SCREENER_URL = "https://www.iwencai.com/screener"
REQUIRED_SKILL = "announcement-search"
DEFAULT_TOOL_SKILLS = (
    "announcement-search",
    "stock-news-search",
    "industry-research",
    "policy-search",
)
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
    skill: str = REQUIRED_SKILL
    items: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[SkillHubAttempt] = field(default_factory=list)
    reason: str = ""
    next_steps: list[str] = field(default_factory=list)
    manual_screener_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "skill": self.skill,
            "items": self.items,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "reason": self.reason,
            "next_steps": self.next_steps,
            "manual_screener_url": self.manual_screener_url,
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
        skill_state = _skill_install_status(cli, DEFAULT_TOOL_SKILLS)
        capabilities = _cli_capabilities(cli)
        installed_skill_names = list(skill_state.get("installed_skill_names", []))
        return {
            "status": "ok" if cli and self.api_key and skill_state["installed"] and capabilities["run_supported"] else "needs_config",
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "configured_cli": self.cli,
            "skillhub_found": bool(cli),
            "skillhub_path": cli.display_path if cli else "",
            "skillhub_bridge": cli.bridge if cli else "",
            "required_skill_installed": skill_state["installed"],
            "required_skill_paths": skill_state["paths"],
            "tool_mode": "multi-skill",
            "tool_skills": list(DEFAULT_TOOL_SKILLS),
            "installed_skill_names": installed_skill_names,
            "skill_installation": skill_state.get("skill_installation", {}),
            "direct_run_supported": capabilities["run_supported"],
            "cli_capability_detail": capabilities["detail"],
            "official_cli_found": bool(official_path),
            "official_cli_path": official_path or "",
            "legacy_skillhub_found": bool(legacy_path),
            "legacy_skillhub_path": legacy_path or "",
            "iwencai_cli_found": bool(iwencai_path),
            "iwencai_cli_path": iwencai_path or "",
            "required_skill": REQUIRED_SKILL,
            "default_tool_skills": list(DEFAULT_TOOL_SKILLS),
            "installer_url": INSTALLER_URL,
            "screener_url": SCREENER_URL,
            "manual_screener_url": _screener_url(_build_query(stock_code="", query="公告")),
            "install_command": f"{OFFICIAL_CLI} install {REQUIRED_SKILL}",
            "project_install_command": f"{OFFICIAL_CLI} --dir {PROJECT_SKILL_INSTALL_DIR} install {REQUIRED_SKILL} --force",
            "tool_install_commands": [f"{OFFICIAL_CLI} install {skill}" for skill in DEFAULT_TOOL_SKILLS],
            "next_steps": self.next_steps(
                cli_found=bool(cli),
                skill_installed=skill_state["installed"],
                run_supported=capabilities["run_supported"],
            ),
        }

    def next_steps(
        self,
        *,
        cli_found: bool | None = None,
        skill_installed: bool | None = None,
        run_supported: bool | None = None,
    ) -> list[str]:
        if cli_found is None:
            cli = _resolve_cli(self.cli)
            cli_found = bool(cli)
        else:
            cli = _resolve_cli(self.cli) if cli_found and (skill_installed is None or run_supported is None) else None
        steps: list[str] = []
        if not cli_found:
            steps.append(f"Install SkillHub from the official installer: {INSTALLER_URL}")
        if not self.api_key:
            steps.append("Save IWENCAI_API_KEY locally with datasource configure-iwencai or shell profile.")
        if skill_installed is None:
            skill_installed = _skill_install_status(cli)["installed"] if cli else False
        if not skill_installed:
            steps.append(f"Install or verify the SkillHub skill: {OFFICIAL_CLI} install {REQUIRED_SKILL}")
        steps.append(
            f"For project-local installs, run: {OFFICIAL_CLI} --dir {PROJECT_SKILL_INSTALL_DIR} "
            f"install {REQUIRED_SKILL} --force"
        )
        if run_supported is None:
            run_supported = _cli_capabilities(cli)["run_supported"] if cli else False
        if cli_found and not run_supported:
            steps.append(
                "The installed iWencai SkillHub store CLI exposes install-only behavior here; "
                "direct announcement search needs an official run-capable CLI or host tool integration."
            )
            steps.append(f"Manual web screener fallback: {_screener_url(_build_query(stock_code='', query='公告'))}")
        return steps

    def search_announcements(self, *, stock_code: str = "", query: str = "", limit: int = 5) -> SkillHubSearchResult:
        return self.run_skill(skill=REQUIRED_SKILL, stock_code=stock_code, query=query or "公告", limit=limit)

    def run_skill(self, *, skill: str = REQUIRED_SKILL, stock_code: str = "", query: str = "", limit: int = 5) -> SkillHubSearchResult:
        """Run any run-capable iWencai SkillHub skill as a research tool."""

        skill_name = _normalize_skill(skill)
        query_text = _build_query(stock_code=stock_code, query=query)
        cli = _resolve_cli(self.cli)
        if not self.api_key:
            return SkillHubSearchResult(
                status="skipped",
                query=query_text,
                skill=skill_name,
                reason="IWENCAI_API_KEY is not configured.",
                next_steps=self.next_steps(cli_found=bool(cli)),
            )
        if not cli:
            return SkillHubSearchResult(
                status="skipped",
                query=query_text,
                skill=skill_name,
                reason="SkillHub CLI is not installed or not on PATH.",
                next_steps=self.next_steps(cli_found=False),
            )
        capabilities = _cli_capabilities(cli)
        if not capabilities["run_supported"]:
            return SkillHubSearchResult(
                status="skipped",
                query=query_text,
                skill=skill_name,
                reason="Installed SkillHub CLI does not expose a direct run/search command.",
                next_steps=self.next_steps(
                    cli_found=True,
                    skill_installed=_skill_install_status(cli, [skill_name])["installed"],
                    run_supported=False,
                )
                + [f"Open iWencai screener manually for this query: {_screener_url(query_text)}"],
                manual_screener_url=_screener_url(query_text),
            )

        commands = _candidate_commands(cli, skill_name, query_text, limit)
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
                        skill=skill_name,
                        items=_parse_items(completed.stdout),
                        attempts=attempts,
                    )
            except Exception as exc:  # pragma: no cover - external CLI guard
                attempt.error = str(exc)
                attempts.append(attempt)
        return SkillHubSearchResult(
            status="error",
            query=query_text,
            skill=skill_name,
            attempts=attempts,
            reason=f"SkillHub CLI did not return a successful {skill_name} result.",
            next_steps=[
                f"Run {OFFICIAL_CLI} install {skill_name} and retry.",
                f"For project-local installs, run {OFFICIAL_CLI} --dir {PROJECT_SKILL_INSTALL_DIR} install {skill_name} --force.",
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


def _screener_url(query: str) -> str:
    return f"{SCREENER_URL}?query={quote(query or 'A股 公告', safe='')}"


def _normalize_skill(skill: str) -> str:
    value = str(skill or "").strip()
    return value or REQUIRED_SKILL


def _installed_names_from_paths(paths: list[str], skill_names: list[str]) -> set[str]:
    installed: set[str] = set()
    lowered_paths = [path.lower() for path in paths]
    for skill_name in skill_names:
        needle = skill_name.lower()
        if any(needle in path for path in lowered_paths):
            installed.add(skill_name)
    return installed


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


def _skill_install_status(cli: SkillHubCli | None, skills: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    skill_names = [_normalize_skill(skill) for skill in (skills or (REQUIRED_SKILL,))]
    skill_names = list(dict.fromkeys(skill_names))
    paths = _local_skill_paths(skill_names)
    probes: list[dict[str, Any]] = []
    installed_skill_names = _installed_names_from_paths(paths, skill_names)
    if cli:
        if cli.bridge == "wsl":
            paths.extend(_wsl_skill_paths(cli, skill_names))
            paths = sorted(dict.fromkeys(paths))
            installed_skill_names.update(_installed_names_from_paths(paths, skill_names))
        for args in (("list",), ("skill", "list")):
            attempt = _run_cli_probe(cli, *args)
            probes.append(_attempt_summary(attempt))
            text = _attempt_text(attempt)
            if attempt.exit_code != 0:
                continue
            for skill_name in skill_names:
                if skill_name in text:
                    installed_skill_names.add(skill_name)
            if installed_skill_names:
                break
    skill_installation = {
        skill_name: {
            "installed": skill_name in installed_skill_names,
            "paths": [path for path in paths if skill_name.lower() in path.lower()],
        }
        for skill_name in skill_names
    }
    installed = REQUIRED_SKILL in installed_skill_names if REQUIRED_SKILL in skill_names else all(skill_name in installed_skill_names for skill_name in skill_names)
    return {
        "installed": installed,
        "paths": paths,
        "probes": probes,
        "installed_skill_names": sorted(installed_skill_names),
        "skill_installation": skill_installation,
    }


def _cli_capabilities(cli: SkillHubCli | None) -> dict[str, Any]:
    if not cli:
        return {"run_supported": False, "detail": "SkillHub CLI is not installed or not on PATH.", "probes": []}

    run_help = _run_cli_probe(cli, "run", "--help")
    probes = [_attempt_summary(run_help)]
    run_text = _attempt_text(run_help).lower()
    negative_markers = (
        "no such command",
        "unknown command",
        "invalid choice",
        "unrecognized arguments",
        "not found",
    )
    run_supported = run_help.exit_code == 0 and not any(marker in run_text for marker in negative_markers)
    if run_supported:
        return {"run_supported": True, "detail": "CLI accepts `run --help`.", "probes": probes}

    top_help = _run_cli_probe(cli, "--help")
    probes.append(_attempt_summary(top_help))
    detail = _first_nonempty(_attempt_text(run_help), _attempt_text(top_help))
    if _looks_install_only(_attempt_text(top_help)):
        detail = "CLI help only exposes install/store behavior; direct run/search support was not detected."
    return {"run_supported": False, "detail": _redact_text(detail)[:1000], "probes": probes}


def _local_skill_paths(skill_names: list[str] | tuple[str, ...] | None = None) -> list[str]:
    names = [_normalize_skill(skill) for skill in (skill_names or (REQUIRED_SKILL,))]
    roots = [Path.cwd() / PROJECT_SKILL_INSTALL_DIR, _project_root() / PROJECT_SKILL_INSTALL_DIR]
    paths: dict[str, None] = {}
    for root in roots:
        if not root.exists():
            continue
        for skill_name in names:
            direct = root / skill_name
            if direct.exists():
                paths[str(direct.resolve())] = None
            for match in root.rglob(f"*{skill_name}*"):
                paths[str(match.resolve())] = None
                if len(paths) >= 40:
                    break
    return sorted(paths)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _wsl_skill_paths(cli: SkillHubCli, skill_names: list[str] | tuple[str, ...] | None = None) -> list[str]:
    if cli.bridge != "wsl":
        return []
    names = [_normalize_skill(skill) for skill in (skill_names or (REQUIRED_SKILL,))]
    find_expr = " -o ".join(f'-iname "*{_shell_quote_for_double(skill_name)}*"' for skill_name in names)
    script = (
        'export PATH="$HOME/.local/bin:$PATH"; '
        f'for root in "$HOME/.iwencai-skillhub" "$HOME/.local/share/iwencai-skillhub" '
        f'"$HOME/.cache/iwencai-skillhub" "$PWD/{PROJECT_SKILL_INSTALL_DIR}"; do '
        '[ -e "$root" ] || continue; '
        f'find "$root" -maxdepth 5 \\( {find_expr} \\) -print 2>/dev/null; '
        'done'
    )
    attempt = _run_wsl_script(cli, script)
    if attempt.exit_code != 0:
        return []
    return [f"wsl:{line.strip()}" for line in attempt.stdout.splitlines() if line.strip()]


def _run_cli_probe(cli: SkillHubCli, *args: str) -> SkillHubAttempt:
    command = _probe_command(cli, *args)
    attempt = SkillHubAttempt(command=command)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        attempt.exit_code = completed.returncode
        attempt.stdout = completed.stdout or ""
        attempt.stderr = completed.stderr or ""
    except Exception as exc:  # pragma: no cover - external CLI guard
        attempt.error = str(exc)
    return attempt


def _run_wsl_script(cli: SkillHubCli, script: str) -> SkillHubAttempt:
    command = [*cli.command_prefix, script]
    attempt = SkillHubAttempt(command=command)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        attempt.exit_code = completed.returncode
        attempt.stdout = completed.stdout or ""
        attempt.stderr = completed.stderr or ""
    except Exception as exc:  # pragma: no cover - external CLI guard
        attempt.error = str(exc)
    return attempt


def _probe_command(cli: SkillHubCli, *args: str) -> list[str]:
    if cli.bridge == "wsl":
        return [*cli.command_prefix, _wsl_command(*args)]
    return [*cli.command_prefix, *args]


def _attempt_text(attempt: SkillHubAttempt) -> str:
    return "\n".join(item for item in (attempt.stdout, attempt.stderr, attempt.error) if item)


def _attempt_summary(attempt: SkillHubAttempt) -> dict[str, Any]:
    return {
        "command": _redact_command(attempt.command),
        "exit_code": attempt.exit_code,
        "stdout": _redact_text(attempt.stdout)[:500],
        "stderr": _redact_text(attempt.stderr)[:500],
        "error": _redact_text(attempt.error)[:500],
    }


def _first_nonempty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return "CLI did not expose direct run/search support."


def _looks_install_only(help_text: str) -> bool:
    text = (help_text or "").lower()
    return "install" in text and " run" not in text and "search" not in text


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


def _candidate_commands(cli: SkillHubCli, skill: str, query: str, limit: int) -> list[list[str]]:
    skill_name = _normalize_skill(skill)
    limit_text = str(max(1, limit))
    if cli.bridge == "wsl":
        return [
            [*cli.command_prefix, _wsl_command("run", skill_name, "--query", query, "--limit", limit_text)],
            [*cli.command_prefix, _wsl_command("skill", "run", skill_name, "--query", query, "--limit", limit_text)],
            [*cli.command_prefix, _wsl_command(skill_name, "--query", query, "--limit", limit_text)],
        ]
    return [
        [*cli.command_prefix, "run", skill_name, "--query", query, "--limit", limit_text],
        [*cli.command_prefix, "skill", "run", skill_name, "--query", query, "--limit", limit_text],
        [*cli.command_prefix, skill_name, "--query", query, "--limit", limit_text],
    ]


def _wsl_command(*parts: str) -> str:
    quoted = " ".join(_shell_quote(part) for part in parts)
    return f'export PATH="$HOME/.local/bin:$PATH"; {OFFICIAL_CLI} {quoted}'


def _shell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _shell_quote_for_double(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


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
