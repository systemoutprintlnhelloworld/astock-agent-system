from __future__ import annotations

import pytest

from astock_agent_system import config as config_module


@pytest.fixture(autouse=True)
def isolate_local_runtime_config(monkeypatch, tmp_path):  # noqa: ANN001 - pytest fixture helpers
    runtime_path = tmp_path / "settings.override.json"
    monkeypatch.setattr(config_module, "RUNTIME_CONFIG_PATH", runtime_path)
    config_module._DOTENV_LOADED_VALUES.clear()
    for env_name in set(config_module.RUNTIME_ENV_FIELD_MAP.values()):
        monkeypatch.setenv(env_name, "")
