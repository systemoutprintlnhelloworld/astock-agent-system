from __future__ import annotations

import getpass
import json
from types import SimpleNamespace

from astock_agent_system import cli_enhanced, config as config_module
from astock_agent_system.cli_enhanced import cmd_datasource_configure_jqdata
from astock_agent_system.config import load_settings


ISOLATED_ENV_KEYS = (
    "DATA_MODE",
    "OFFLINE_DATA_PATH",
    "DYNAMIC_UNIVERSE_LIMIT",
    "DATA_PROVIDER_CHAIN",
    "TUSHARE_TOKEN",
    "ALPHA_VANTAGE_API_KEY",
    "JQDATA_USERNAME",
    "JQDATA_PASSWORD",
    "IFIND_ACCESS_TOKEN",
    "IFIND_REFRESH_TOKEN",
    "IFIND_BASE_URL",
    "IWENCAI_BASE_URL",
    "IWENCAI_API_KEY",
    "IWENCAI_SKILLHUB_CLI",
    "INITIAL_CAPITAL",
    "MAX_POSITION_PER_STOCK",
    "MAX_TOTAL_POSITION",
    "STOP_LOSS_PCT",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_DEFAULT_MODEL",
    "LLM_REQUEST_PROFILE",
    "LLM_MAX_TOKENS",
    "LLM_USER_AGENT",
    "MONGO_TIMEOUT_MS",
    "SMART_SEARCH_ENABLED",
    "SCHEDULER_MODELS",
    "SCHEDULER_MAX_COUNT",
    "SCHEDULER_HISTORY_DAYS",
)


def isolate_runtime_config(monkeypatch, tmp_path):
    runtime_path = tmp_path / "settings.override.json"
    monkeypatch.setattr(config_module, "RUNTIME_CONFIG_PATH", runtime_path)
    for key in ISOLATED_ENV_KEYS:
        monkeypatch.setenv(key, "")
    return runtime_path


def test_load_settings_defaults_are_offline_and_non_secret(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
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


def test_smart_search_defaults_to_enabled_when_not_overridden(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "")

    settings = load_settings()

    assert settings.smart_search.enabled is True


def test_ifind_base_url_can_be_overridden(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setenv("IFIND_BASE_URL", "https://example.test/quantapi")

    settings = load_settings()

    assert settings.data.ifind_base_url == "https://example.test/quantapi"


def test_environment_overrides_non_secret_values(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setenv("INITIAL_CAPITAL", "250000")
    monkeypatch.setenv("MAX_POSITION_PER_STOCK", "0.15")
    monkeypatch.setenv("MAX_TOTAL_POSITION", "0.60")

    settings = load_settings()

    assert settings.portfolio.initial_capital == 250000
    assert settings.risk.max_position_per_stock == 0.15
    assert settings.risk.max_total_position == 0.60


def test_llm_request_profile_and_generation_overrides(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_REQUEST_PROFILE", "Claude_Code")
    monkeypatch.setenv("LLM_MAX_TOKENS", "256")
    monkeypatch.setenv("LLM_USER_AGENT", "test-agent/1.0")

    settings = load_settings()

    assert settings.llm.request_profile == "claude_code"
    assert settings.llm.max_tokens == 256
    assert settings.llm.user_agent == "test-agent/1.0"


def test_storage_timeout_override(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("MONGO_TIMEOUT_MS", "777")

    settings = load_settings()

    assert settings.storage.mongo_timeout_ms == 777


def test_scheduler_models_override(monkeypatch, tmp_path):
    isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("SCHEDULER_MODELS", "rule-baseline, gpt-5.4-mini, codex-auto-review")

    settings = load_settings()

    assert settings.scheduler.models == ["rule-baseline", "gpt-5.4-mini", "codex-auto-review"]


def test_empty_environment_does_not_mask_runtime_overrides(monkeypatch, tmp_path):
    runtime_path = isolate_runtime_config(monkeypatch, tmp_path)
    runtime_path.write_text(
        json.dumps(
            {
                "data": {
                    "mode": "online",
                    "provider_chain": ["tushare", "baostock"],
                    "tushare_token": "runtime-token",
                },
                "llm": {
                    "base_url": "https://runtime.example/v1",
                    "api_key": "runtime-llm-key",
                    "default_model": "gpt-runtime",
                    "request_profile": "auto",
                },
                "scheduler": {
                    "max_count": 1,
                    "history_days": 12,
                },
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.data.mode == "online"
    assert settings.data.provider_chain == ["tushare", "baostock"]
    assert settings.data.tushare_token == "runtime-token"
    assert settings.llm.base_url == "https://runtime.example/v1"
    assert settings.llm.api_key == "runtime-llm-key"
    assert settings.llm.default_model == "gpt-runtime"
    assert settings.llm.request_profile == "auto"
    assert settings.scheduler.max_count == 1
    assert settings.scheduler.history_days == 12


def test_datasource_configure_jqdata_persists_runtime_credentials(monkeypatch, tmp_path, capsys):
    runtime_path = isolate_runtime_config(monkeypatch, tmp_path)
    monkeypatch.setattr(config_module, "RUNTIME_CONFIG_PATH", runtime_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "jq-user")
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "jq-pass")
    monkeypatch.setattr(
        cli_enhanced,
        "_test_one_datasource",
        lambda *args, **kwargs: {"status": "ok", "checks": [{"name": "history", "status": "ok"}]},
    )

    exit_code = cmd_datasource_configure_jqdata(
        SimpleNamespace(config=None, username="", provider_chain="tushare,baostock")
    )
    payload = json.loads(capsys.readouterr().out)
    settings = load_settings()

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert settings.data.jqdata_username == "jq-user"
    assert settings.data.jqdata_password == "jq-pass"
    assert settings.data.provider_chain == ["tushare", "baostock", "jqdata"]
    assert payload["preflight"]["status"] == "ok"
