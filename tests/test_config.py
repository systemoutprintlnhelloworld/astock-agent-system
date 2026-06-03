from __future__ import annotations

from astock_agent_system.config import load_settings


def test_load_settings_defaults_are_offline_and_non_secret(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")

    settings = load_settings()

    assert settings.data.mode == "offline"
    assert settings.data.offline_data_path.endswith("stocks.json")
    assert settings.portfolio.initial_capital > 0
    assert settings.risk.max_position_per_stock <= settings.risk.max_total_position
    assert settings.llm.api_key == ""
    assert settings.smart_search.enabled is False


def test_environment_overrides_non_secret_values(monkeypatch):
    monkeypatch.setenv("INITIAL_CAPITAL", "250000")
    monkeypatch.setenv("MAX_POSITION_PER_STOCK", "0.15")
    monkeypatch.setenv("MAX_TOTAL_POSITION", "0.60")

    settings = load_settings()

    assert settings.portfolio.initial_capital == 250000
    assert settings.risk.max_position_per_stock == 0.15
    assert settings.risk.max_total_position == 0.60


def test_llm_request_profile_and_generation_overrides(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_REQUEST_PROFILE", "Claude_Code")
    monkeypatch.setenv("LLM_MAX_TOKENS", "256")
    monkeypatch.setenv("LLM_USER_AGENT", "test-agent/1.0")

    settings = load_settings()

    assert settings.llm.request_profile == "claude_code"
    assert settings.llm.max_tokens == 256
    assert settings.llm.user_agent == "test-agent/1.0"


def test_storage_timeout_override(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("MONGO_TIMEOUT_MS", "777")

    settings = load_settings()

    assert settings.storage.mongo_timeout_ms == 777


def test_scheduler_models_override(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("SCHEDULER_MODELS", "rule-baseline, gpt-5.4-mini, codex-auto-review")

    settings = load_settings()

    assert settings.scheduler.models == ["rule-baseline", "gpt-5.4-mini", "codex-auto-review"]
