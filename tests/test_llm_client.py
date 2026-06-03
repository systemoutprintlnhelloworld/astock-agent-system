from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from astock_agent_system.cli import build_parser
from astock_agent_system.config import LLMSettings
from astock_agent_system.llm.bench import ModelBench
from astock_agent_system.llm.client import LLMClient, LLMRequestError


TEST_API_KEY = "sk-" + "test-secret"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload)
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self.response


def test_openai_profile_keeps_chat_completions_shape() -> None:
    settings = LLMSettings(
        base_url="https://gateway.test/v1",
        api_key=TEST_API_KEY,
        request_profile="openai",
        max_tokens=123,
    )
    client = LLMClient(settings)
    fake_session = _FakeSession(_FakeResponse({"choices": [{"message": {"content": "{\"ok\": true}"}}]}))
    client.session = fake_session  # type: ignore[assignment]

    result = client.chat_json(model="demo-model", messages=[{"role": "user", "content": "ping"}])

    assert result.profile == "openai"
    assert result.json_parseable is True
    call = fake_session.calls[0]
    assert call["url"] == "https://gateway.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {TEST_API_KEY}"
    assert call["json"]["max_tokens"] == 123


def test_anthropic_profile_uses_messages_shape() -> None:
    settings = LLMSettings(
        base_url="https://gateway.test/v1",
        api_key=TEST_API_KEY,
        request_profile="anthropic",
        max_tokens=321,
    )
    client = LLMClient(settings)
    fake_session = _FakeSession(_FakeResponse({"content": [{"type": "text", "text": "{\"ok\": true}"}]}))
    client.session = fake_session  # type: ignore[assignment]

    result = client.chat_json(
        model="claude-demo",
        messages=[{"role": "system", "content": "system prompt"}, {"role": "user", "content": "ping"}],
    )

    assert result.profile == "anthropic"
    assert result.json_parseable is True
    call = fake_session.calls[0]
    assert call["url"] == "https://gateway.test/v1/messages"
    assert call["headers"]["x-api-key"] == TEST_API_KEY
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    assert call["json"]["system"] == "system prompt"
    assert call["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert call["json"]["max_tokens"] == 321


def test_gateway_error_snippet_is_sanitized() -> None:
    settings = LLMSettings(
        base_url="https://gateway.test/v1",
        api_key=TEST_API_KEY,
        request_profile="openai",
    )
    client = LLMClient(settings)
    error_text = f'{{"error":"Authorization: Bearer {TEST_API_KEY}; key {TEST_API_KEY} is blocked"}}'
    client.session = _FakeSession(_FakeResponse({}, status_code=400, text=error_text))  # type: ignore[assignment]

    with pytest.raises(LLMRequestError) as exc_info:
        client.chat_json(model="demo-model", messages=[{"role": "user", "content": "ping"}])

    message = str(exc_info.value)
    assert "status=400" in message
    assert TEST_API_KEY not in message
    assert f"Bearer {TEST_API_KEY}" not in message
    assert "[REDACTED" in message


def test_list_models_safe_includes_next_steps_for_subscription_window() -> None:
    settings = LLMSettings(
        base_url="https://gateway.test/v1",
        api_key=TEST_API_KEY,
        request_profile="openai",
    )
    client = LLMClient(settings)
    error_text = '{"code":"SUBSCRIPTION_OUT_OF_WINDOW","message":"subscription is outside its daily activation window"}'
    client.session = _FakeSession(_FakeResponse({}, status_code=403, text=error_text))  # type: ignore[assignment]

    payload = client.list_models_safe()

    assert payload["status"] == "error"
    assert TEST_API_KEY not in payload["reason"]
    assert any("Subscription window" in item for item in payload["next_steps"])


def test_bench_command_aliases_are_wired() -> None:
    parser = build_parser()

    bench_args = parser.parse_args(["bench", "--list-models"])
    legacy_args = parser.parse_args(["bench-models", "--list-models"])

    assert bench_args.func.__name__ == "_cmd_bench_models"
    assert legacy_args.func.__name__ == "_cmd_bench_models"


def test_model_bench_reports_error_status_and_next_steps() -> None:
    class _FakeBenchClient:
        is_configured = True
        settings = SimpleNamespace(api_key=TEST_API_KEY, default_model="", request_profile="auto")

        def list_models(self) -> list[str]:
            return ["bad-model"]

        def chat_json(self, **kwargs: Any) -> Any:
            raise RuntimeError(f"429 rate limit for {TEST_API_KEY}")

    payload = ModelBench(_FakeBenchClient()).run(limit=1)  # type: ignore[arg-type]

    assert payload["status"] == "error"
    assert payload["ok_count"] == 0
    assert payload["error_count"] == 1
    assert TEST_API_KEY not in payload["results"][0]["error"]
    assert any("429/rate limit" in item for item in payload["next_steps"])


def test_model_bench_does_not_prepend_default_model_to_explicit_models() -> None:
    captured_models: list[str] = []

    class _FakeBenchClient:
        is_configured = True
        settings = SimpleNamespace(api_key=TEST_API_KEY, default_model="default-model", request_profile="auto")

        def chat_json(self, **kwargs: Any) -> Any:
            captured_models.append(str(kwargs["model"]))
            return SimpleNamespace(profile="openai", json_parseable=True, parsed={"ok": True})

    payload = ModelBench(_FakeBenchClient()).run(models=["explicit-model"], limit=1)  # type: ignore[arg-type]

    assert payload["status"] == "ok"
    assert captured_models == ["explicit-model"]


def test_model_bench_reports_partial_status() -> None:
    class _FakeBenchClient:
        is_configured = True
        settings = SimpleNamespace(api_key=TEST_API_KEY, default_model="", request_profile="auto")

        def chat_json(self, **kwargs: Any) -> Any:
            if kwargs["model"] == "bad-model":
                raise RuntimeError(f"Gateway status=403 forbidden for {TEST_API_KEY}")
            return SimpleNamespace(profile="openai", json_parseable=True, parsed={"ok": True})

    payload = ModelBench(_FakeBenchClient()).run(models=["good-model", "bad-model"], limit=2)  # type: ignore[arg-type]

    assert payload["status"] == "partial"
    assert payload["ok_count"] == 1
    assert payload["error_count"] == 1
    assert payload["success_rate"] == 0.5
    assert any("Auth error" in item for item in payload["next_steps"])
