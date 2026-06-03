"""Model benchmark utilities for OpenAI-compatible gateways."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from astock_agent_system.llm.client import LLMClient


DEFAULT_PROMPT = "请只输出 JSON：{\"score\": 0.5, \"label\": \"ok\", \"reason\": \"模型连通性测试\"}"


@dataclass(slots=True)
class ModelBenchResult:
    model: str
    status: str
    profile: str = ""
    latency_seconds: float = 0.0
    json_parseable: bool = False
    error: str = ""
    response: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelBench:
    """Run lightweight JSON-response checks against selected models."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def run(
        self,
        models: list[str] | None = None,
        prompt: str = DEFAULT_PROMPT,
        limit: int = 5,
    ) -> dict[str, Any]:
        if not self.client.is_configured:
            return {
                "status": "skipped",
                "reason": "LLM_API_KEY is not configured",
                "next_steps": [
                    "Set LLM_BASE_URL and LLM_API_KEY in .env or environment variables.",
                    "Run: python -m astock_agent_system.cli bench --list-models",
                ],
                "results": [],
            }

        explicit_models = [item for item in (models or []) if item]
        selected_models = list(explicit_models)
        if not selected_models:
            try:
                selected_models = self.client.list_models()
            except Exception as exc:  # pragma: no cover - external service guard
                error = _safe_error_text(str(exc), self.client.settings.api_key)
                return {
                    "status": "error",
                    "reason": "failed_to_list_models",
                    "error": error,
                    "model_count": 0,
                    "success_rate": 0.0,
                    "json_parse_rate": 0.0,
                    "next_steps": _next_steps_for_errors([error]),
                    "results": [],
                }
        if not explicit_models and self.client.settings.default_model and self.client.settings.default_model not in selected_models:
            selected_models.insert(0, self.client.settings.default_model)
        selected_models = selected_models[: max(1, limit)]

        if not selected_models:
            return {
                "status": "skipped",
                "reason": "No models were selected or returned by /models",
                "model_count": 0,
                "success_rate": 0.0,
                "json_parse_rate": 0.0,
                "next_steps": [
                    "Run with explicit models: python -m astock_agent_system.cli bench --models <model-id> --limit 1",
                    "Check that the configured gateway exposes /models or set LLM_DEFAULT_MODEL.",
                ],
                "results": [],
            }

        results: list[ModelBenchResult] = []
        for model in selected_models:
            start = time.perf_counter()
            try:
                chat = self.client.chat_json(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是严格的 JSON 输出测试助手。"},
                        {"role": "user", "content": prompt},
                    ],
                )
                latency = round(time.perf_counter() - start, 4)
                results.append(
                    ModelBenchResult(
                        model=model,
                        status="ok",
                        profile=chat.profile,
                        latency_seconds=latency,
                        json_parseable=chat.json_parseable,
                        response=chat.parsed,
                        diagnostics={"configured_profile": self.client.settings.request_profile},
                    )
                )
            except Exception as exc:  # pragma: no cover - external service guard
                latency = round(time.perf_counter() - start, 4)
                error = _safe_error_text(str(exc), self.client.settings.api_key)
                results.append(
                    ModelBenchResult(
                        model=model,
                        status="error",
                        profile=self.client.settings.request_profile,
                        latency_seconds=latency,
                        error=error,
                        diagnostics={
                            "configured_profile": self.client.settings.request_profile,
                            "error_type": exc.__class__.__name__,
                            "error_summary": error,
                        },
                    )
                )

        ok_count = sum(1 for item in results if item.status == "ok")
        json_count = sum(1 for item in results if item.json_parseable)
        errors = [item.error for item in results if item.error]
        if ok_count == len(results):
            status = "ok"
        elif ok_count > 0:
            status = "partial"
        else:
            status = "error"
        return {
            "status": status,
            "model_count": len(results),
            "ok_count": ok_count,
            "error_count": len(results) - ok_count,
            "success_rate": (ok_count / len(results)) if results else 0.0,
            "json_parse_rate": (json_count / len(results)) if results else 0.0,
            "next_steps": _next_steps_for_errors(errors) if status != "ok" else [],
            "results": [item.to_dict() for item in results],
        }


def _safe_error_text(text: str, api_key: str = "") -> str:
    sanitized = text
    if api_key:
        sanitized = sanitized.replace(api_key, "[REDACTED_API_KEY]")
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-[REDACTED]", sanitized)
    return sanitized


def _next_steps_for_errors(errors: list[str]) -> list[str]:
    """Return concise remediation hints without exposing credentials."""
    joined = "\n".join(errors).lower()
    steps = [
        "Verify LLM_BASE_URL includes the API version suffix, for example https://gateway.example/v1.",
        "Run: python -m astock_agent_system.cli bench --list-models",
        "Run one cheap model first: python -m astock_agent_system.cli bench --models <model-id> --limit 1",
    ]
    if "429" in joined or "rate" in joined:
        steps.append("429/rate limit: reduce --limit, wait, or choose a smaller model.")
    if "subscription_out_of_window" in joined or "activation window" in joined:
        steps.append("Subscription window: wait until the gateway daily activation window opens, or switch to an active key/model.")
    if "401" in joined or "403" in joined or "unauthorized" in joined or "forbidden" in joined:
        steps.append("Auth error: check that LLM_API_KEY belongs to this gateway and has model access.")
    if "invalid json" in joined or "non-object json" in joined:
        steps.append("Gateway shape issue: try LLM_REQUEST_PROFILE=auto or LLM_REQUEST_PROFILE=openai.")
    return list(dict.fromkeys(steps))
