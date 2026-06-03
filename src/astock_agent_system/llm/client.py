"""OpenAI-compatible LLM client with retry and JSON parsing helpers."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from astock_agent_system.config import LLMSettings, Settings, load_settings


CHAT_COMPLETION_PROFILES = ("openai", "codex")
ANTHROPIC_MESSAGE_PROFILES = ("anthropic", "claude_code")
REQUEST_PROFILES = (*CHAT_COMPLETION_PROFILES, *ANTHROPIC_MESSAGE_PROFILES)


class LLMNotConfiguredError(RuntimeError):
    """Raised when an LLM call needs credentials that are not configured."""


class LLMRequestError(RuntimeError):
    """Raised when the compatible gateway cannot complete a request."""


@dataclass(slots=True)
class ChatResult:
    model: str
    content: str
    parsed: dict[str, Any]
    raw: dict[str, Any]
    json_parseable: bool
    profile: str = "openai"

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "profile": self.profile,
            "content": self.content,
            "parsed": self.parsed,
            "json_parseable": self.json_parseable,
        }


class LLMClient:
    """Small OpenAI-compatible client.

    Credentials are read from Settings, which itself only reads API keys from
    environment variables. Do not pass or log real keys in application code.
    """

    def __init__(self, settings: Settings | LLMSettings | None = None) -> None:
        if settings is None:
            self.settings = load_settings().llm
        elif isinstance(settings, LLMSettings):
            self.settings = settings
        else:
            self.settings = settings.llm
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.api_key and self.settings.base_url)

    def list_models(self) -> list[str]:
        """Return model ids from the compatible `/models` endpoint."""
        payload = self._request_json("GET", "/models")
        data = payload.get("data", [])
        models: list[str] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id"):
                    models.append(str(item["id"]))
                elif isinstance(item, str):
                    models.append(item)
        return models

    def list_models_safe(self) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "status": "skipped",
                "reason": "LLM_API_KEY is not configured",
                "next_steps": ["Set LLM_BASE_URL and LLM_API_KEY, then retry: python -m astock_agent_system.cli bench --list-models"],
                "models": [],
            }
        try:
            models = self.list_models()
        except Exception as exc:  # pragma: no cover - external service guard
            reason = _sanitize_text(str(exc), self.settings.api_key)
            return {"status": "error", "reason": reason, "next_steps": _next_steps_for_error_text(reason), "models": []}
        return {"status": "ok", "count": len(models), "next_steps": [], "models": models}

    def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        profile: str | None = None,
    ) -> ChatResult:
        """Call the configured chat endpoint and parse assistant content as JSON."""
        selected_model = model or self.settings.default_model
        if not selected_model:
            raise LLMRequestError("No model specified. Set LLM_DEFAULT_MODEL or pass model explicitly.")

        selected_profile = _normalize_profile(profile or self.settings.request_profile)
        if selected_profile == "auto":
            response, used_profile = self._request_chat_auto(selected_model, messages, temperature)
        else:
            response, used_profile = self._request_chat_profile(selected_profile, selected_model, messages, temperature)

        content = self._extract_content(response, used_profile)
        parsed, parseable = _parse_json_content(content)
        return ChatResult(
            model=selected_model,
            content=content,
            parsed=parsed,
            raw=response,
            json_parseable=parseable,
            profile=used_profile,
        )

    def _request_chat_auto(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> tuple[dict[str, Any], str]:
        errors: list[str] = []
        for candidate in REQUEST_PROFILES:
            try:
                return self._request_chat_profile(candidate, model, messages, temperature, max_attempts=1)
            except LLMRequestError as exc:
                errors.append(f"{candidate}: {exc}")
        joined = " | ".join(errors)
        raise LLMRequestError(f"No LLM request profile worked. {joined}")

    def _request_chat_profile(
        self,
        profile: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_attempts: int | None = None,
    ) -> tuple[dict[str, Any], str]:
        if profile in CHAT_COMPLETION_PROFILES:
            return self._request_chat_completion(profile, model, messages, temperature, max_attempts), profile
        if profile in ANTHROPIC_MESSAGE_PROFILES:
            return self._request_anthropic_message(profile, model, messages, temperature, max_attempts), profile
        raise LLMRequestError(f"Unsupported LLM request profile: {profile}")

    def _request_chat_completion(
        self,
        profile: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.settings.max_tokens,
        }
        return self._request_json("POST", "/chat/completions", json_body=payload, profile=profile, max_attempts=max_attempts)

    def _request_anthropic_message(
        self,
        profile: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        system_prompt, anthropic_messages = _to_anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": self.settings.max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        return self._request_json("POST", "/messages", json_body=payload, profile=profile, max_attempts=max_attempts)

    def _request_json(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        profile: str = "openai",
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise LLMNotConfiguredError("LLM_API_KEY is not configured")

        url = f"{self.settings.base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = self._headers_for_profile(profile)
        attempts = max(1, max_attempts if max_attempts is not None else self.settings.max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_body,
                    timeout=self.settings.timeout_seconds,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = LLMRequestError(_http_error_message(profile, response, self.settings.api_key))
                    if attempt < attempts - 1:
                        time.sleep(_retry_sleep_seconds(attempt, response))
                        continue
                    raise last_error
                if response.status_code >= 400:
                    raise LLMRequestError(_http_error_message(profile, response, self.settings.api_key))
                data = response.json()
                if not isinstance(data, dict):
                    raise LLMRequestError("Gateway returned non-object JSON")
                return data
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(_retry_sleep_seconds(attempt, None))
                    continue
            except LLMRequestError:
                raise
            except json.JSONDecodeError as exc:
                last_error = exc
                snippet = _response_snippet(response, self.settings.api_key) if "response" in locals() else ""
                raise LLMRequestError(f"Gateway returned invalid JSON. profile={profile}; body={snippet}") from exc
        raise LLMRequestError(f"Gateway request failed after retries: {last_error}")

    def _headers_for_profile(self, profile: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.settings.user_agent:
            headers["User-Agent"] = self.settings.user_agent

        if profile in ANTHROPIC_MESSAGE_PROFILES:
            headers["x-api-key"] = self.settings.api_key
            headers["anthropic-version"] = "2023-06-01"
            if profile == "claude_code":
                headers["anthropic-beta"] = "claude-code-20250219"
            return headers

        headers["Authorization"] = "Bearer " + self.settings.api_key
        if profile == "codex":
            headers.setdefault("User-Agent", self.settings.user_agent or "astock-agent-system codex-compatible")
            headers["X-Stainless-Lang"] = "python"
            headers["X-Stainless-Arch"] = "other"
            headers["X-Stainless-Runtime"] = "python"
        return headers

    @staticmethod
    def _extract_content(payload: dict[str, Any], profile: str = "openai") -> str:
        if profile in ANTHROPIC_MESSAGE_PROFILES:
            content = _extract_anthropic_content(payload)
            if content:
                return content
        return _extract_openai_content(payload)


def _extract_openai_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message", {})
    if isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts)
    return ""


def _extract_anthropic_content(payload: dict[str, Any]) -> str:
    content = payload.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if isinstance(payload.get("completion"), str):
        return str(payload["completion"])
    return ""


def _normalize_profile(profile: str | None) -> str:
    normalized = (profile or "openai").strip().lower().replace("-", "_")
    aliases = {
        "openai_compatible": "openai",
        "chat_completions": "openai",
        "chat_completion": "openai",
        "claude": "anthropic",
        "anthropic_messages": "anthropic",
        "claude_code": "claude_code",
        "claudecode": "claude_code",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized == "auto" or normalized in REQUEST_PROFILES:
        return normalized
    raise LLMRequestError(f"Unsupported LLM request profile: {normalized}")


def _to_anthropic_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    converted: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip().lower()
        content = str(message.get("content", ""))
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        converted.append({"role": role, "content": content})
    if not converted:
        converted.append({"role": "user", "content": "{}"})
    return "\n".join(system_parts), converted


def _http_error_message(profile: str, response: requests.Response, api_key: str = "") -> str:
    body = _response_snippet(response, api_key)
    return f"Gateway HTTP error. profile={profile}; status={response.status_code}; body={body}"


def _response_snippet(response: requests.Response | None, api_key: str = "", limit: int = 700) -> str:
    if response is None:
        return ""
    text = getattr(response, "text", "") or ""
    text = _sanitize_text(text, api_key)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _sanitize_text(text: str, api_key: str = "") -> str:
    sanitized = text
    if api_key:
        sanitized = sanitized.replace(api_key, "[REDACTED_API_KEY]")
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-[REDACTED]", sanitized)
    sanitized = re.sub(r'("?(?:authorization|x-api-key)"?\s*[:=]\s*)"?[^",}\s]+"?', r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


def _next_steps_for_error_text(text: str) -> list[str]:
    lowered = text.lower()
    steps = [
        "Verify LLM_BASE_URL includes the API version suffix, for example https://gateway.example/v1.",
        "If /models works but chat fails, run: python -m astock_agent_system.cli bench --models <model-id> --limit 1.",
    ]
    if "subscription_out_of_window" in lowered or "activation window" in lowered:
        steps.append("Subscription window: wait until the gateway daily activation window opens, or switch to an active key/model.")
    if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        steps.append("Auth error: check that the key belongs to this gateway and has model access.")
    if "429" in lowered or "rate" in lowered:
        steps.append("429/rate limit: reduce request count, wait, or choose a smaller model.")
    return list(dict.fromkeys(steps))


def _retry_sleep_seconds(attempt: int, response: requests.Response | None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(30.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
    return min(30.0, 2.0**attempt)


def _parse_json_content(content: str) -> tuple[dict[str, Any], bool]:
    text = _strip_code_fence(content.strip())
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, True
            return {"value": parsed}, True
        except json.JSONDecodeError:
            continue
    return {"raw": content, "json_parse_error": "assistant content is not valid JSON"}, False


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text
