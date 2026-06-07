"""Agent Markdown descriptors and user preference loading.

The descriptors keep investment-agent instructions, tunable rule weights and
LLM prompt templates in human-readable Markdown files under ``config/agents``.
They are intentionally lightweight and local: no MCP/plugin runtime is needed
for the current fixed investment workflow.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from astock_agent_system.config import PROJECT_ROOT, _load_yaml


AGENT_CONFIG_DIR = PROJECT_ROOT / "config" / "agents"
AGENT_VERSION_DIR = AGENT_CONFIG_DIR / "versions"
USER_PROFILE_PATH = PROJECT_ROOT / "config" / "user_profile.yaml"


AGENT_ALIASES = {
    "technical": "technical_analyst",
    "fundamental": "fundamental_analyst",
    "sentiment": "sentiment_analyst",
    "risk": "risk_manager",
    "debate": "debate_room",
    "portfolio": "portfolio_manager",
    "screener": "screener",
    "master": "master_agent",
}


@dataclass(slots=True)
class UserProfile:
    """Local, non-secret user investment preferences."""

    risk_preference: str = "moderate"
    focus_areas: list[str] = field(default_factory=list)
    custom_rules: list[str] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "risk_preference": self.risk_preference,
            "focus_areas": ", ".join(self.focus_areas) if self.focus_areas else "未设置",
            "custom_rules": "\n".join(f"- {rule}" for rule in self.custom_rules) if self.custom_rules else "- 无",
        }


@dataclass(slots=True)
class AgentDescriptor:
    """Parsed view of one ``config/agents/*.md`` file."""

    agent_id: str
    name: str
    version: str
    updated_at: str
    update_reason: str
    description_path: Path
    raw_content: str
    rules: dict[str, Any] = field(default_factory=dict)
    prompt_template: str = ""
    system_prompt: str = ""
    learning_stats: dict[str, Any] = field(default_factory=dict)

    def render_prompt(self, context: dict[str, Any] | None = None) -> str:
        """Render ``{placeholder}`` values without requiring a template engine."""
        merged: dict[str, Any] = {}
        merged.update(self.learning_stats)
        merged.update(load_user_profile().to_context())
        if context:
            merged.update(context)

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in merged:
                return match.group(0)
            value = merged[key]
            if isinstance(value, (dict, list)):
                return str(value)
            return str(value)

        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, self.prompt_template)

    def get_rule_float(self, name: str, default: float) -> float:
        value = self.rules.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def to_public_dict(self, include_content: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "updated_at": self.updated_at,
            "update_reason": self.update_reason,
            "rules": self.rules,
            "has_prompt_template": bool(self.prompt_template),
            "path": str(self.description_path.relative_to(PROJECT_ROOT)),
        }
        if include_content:
            payload["content"] = self.raw_content
        return payload


def normalize_agent_id(agent_id: str) -> str:
    normalized = agent_id.strip().lower().replace("-", "_")
    return AGENT_ALIASES.get(normalized, normalized)


def load_user_profile(path: Path | None = None) -> UserProfile:
    raw = _load_yaml(path or USER_PROFILE_PATH)
    profile = raw.get("user_profile", raw) if isinstance(raw, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    focus = profile.get("focus_areas", [])
    rules = profile.get("custom_rules", [])
    return UserProfile(
        risk_preference=str(profile.get("risk_preference", "moderate")),
        focus_areas=[str(item) for item in focus] if isinstance(focus, list) else [],
        custom_rules=[str(item) for item in rules] if isinstance(rules, list) else [],
    )


def load_agent_descriptor(agent_id: str, directory: Path | None = None) -> AgentDescriptor:
    resolved_id = normalize_agent_id(agent_id)
    base_dir = directory or AGENT_CONFIG_DIR
    path = base_dir / f"{resolved_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"Agent descriptor not found: {path}")
    content = path.read_text(encoding="utf-8")
    machine_config = _extract_machine_config(content)
    metadata = machine_config.get("metadata", {}) if isinstance(machine_config.get("metadata", {}), dict) else {}
    rules = machine_config.get("rules", {}) if isinstance(machine_config.get("rules", {}), dict) else {}
    learning = machine_config.get("learning_stats", {}) if isinstance(machine_config.get("learning_stats", {}), dict) else {}
    return AgentDescriptor(
        agent_id=str(machine_config.get("agent_id") or metadata.get("agent_id") or resolved_id),
        name=str(machine_config.get("name") or metadata.get("name") or _extract_title(content) or resolved_id),
        version=str(machine_config.get("version") or metadata.get("version") or _extract_bullet(content, "版本") or "v1.0.0"),
        updated_at=str(metadata.get("updated_at") or _extract_bullet(content, "最后更新") or ""),
        update_reason=str(metadata.get("update_reason") or _extract_bullet(content, "更新原因") or ""),
        description_path=path,
        raw_content=content,
        rules=dict(rules),
        prompt_template=_extract_prompt_template(content),
        system_prompt=str(machine_config.get("system_prompt", "")),
        learning_stats=dict(learning),
    )


def list_agent_descriptors(directory: Path | None = None) -> list[AgentDescriptor]:
    base_dir = directory or AGENT_CONFIG_DIR
    descriptors: list[AgentDescriptor] = []
    for path in sorted(base_dir.glob("*.md")):
        try:
            descriptors.append(load_agent_descriptor(path.stem, base_dir))
        except (FileNotFoundError, OSError, ValueError):
            continue
    return descriptors


def backup_agent_descriptor(agent_id: str, directory: Path | None = None) -> Path:
    descriptor = load_agent_descriptor(agent_id, directory)
    version_dir = (directory or AGENT_CONFIG_DIR) / "versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    target = version_dir / f"{descriptor.agent_id}.{descriptor.version}.{stamp}.md"
    counter = 1
    while target.exists():
        target = version_dir / f"{descriptor.agent_id}.{descriptor.version}.{stamp}.{counter}.md"
        counter += 1
    shutil.copy2(descriptor.description_path, target)
    return target


def rollback_agent_descriptor(agent_id: str, version_file: str, directory: Path | None = None) -> Path:
    resolved_id = normalize_agent_id(agent_id)
    base_dir = directory or AGENT_CONFIG_DIR
    source = base_dir / "versions" / version_file
    if not source.exists():
        raise FileNotFoundError(f"Agent descriptor version not found: {source}")
    target = base_dir / f"{resolved_id}.md"
    if target.exists():
        backup_agent_descriptor(resolved_id, base_dir)
    shutil.copy2(source, target)
    return target


def _extract_machine_config(content: str) -> dict[str, Any]:
    match = re.search(r"##\s*机器可读配置\s*```(?:yaml|yml)?\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
    if not match:
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    payload = yaml.safe_load(match.group(1)) or {}
    return payload if isinstance(payload, dict) else {}


def _extract_prompt_template(content: str) -> str:
    match = re.search(r"##\s*Prompt模板.*?```(?:text|markdown)?\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_title(content: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_bullet(content: str, key: str) -> str:
    match = re.search(rf"^-\s*{re.escape(key)}\s*[:：]\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""
