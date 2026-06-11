"""Configuration loading for the A-share agent system.

Real credentials are read from environment variables or the local ``.env`` file.
The checked-in YAML files provide safe defaults for offline development.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.getenv("ASTOCK_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "data" / "runtime" / "settings.override.json"
_DOTENV_LOADED_VALUES: dict[str, str] = {}


RUNTIME_ENV_FIELD_MAP = {
    ("data", "mode"): "DATA_MODE",
    ("data", "offline_data_path"): "OFFLINE_DATA_PATH",
    ("data", "dynamic_universe_limit"): "DYNAMIC_UNIVERSE_LIMIT",
    ("data", "provider_chain"): "DATA_PROVIDER_CHAIN",
    ("data", "tushare_token"): "TUSHARE_TOKEN",
    ("data", "alpha_vantage_api_key"): "ALPHA_VANTAGE_API_KEY",
    ("data", "jqdata_username"): "JQDATA_USERNAME",
    ("data", "jqdata_password"): "JQDATA_PASSWORD",
    ("data", "ifind_access_token"): "IFIND_ACCESS_TOKEN",
    ("data", "ifind_refresh_token"): "IFIND_REFRESH_TOKEN",
    ("data", "ifind_base_url"): "IFIND_BASE_URL",
    ("portfolio", "initial_capital"): "INITIAL_CAPITAL",
    ("risk", "max_position_per_stock"): "MAX_POSITION_PER_STOCK",
    ("risk", "max_total_position"): "MAX_TOTAL_POSITION",
    ("risk", "stop_loss_pct"): "STOP_LOSS_PCT",
    ("llm", "base_url"): "LLM_BASE_URL",
    ("llm", "api_key"): "LLM_API_KEY",
    ("llm", "default_model"): "LLM_DEFAULT_MODEL",
    ("llm", "timeout_seconds"): "LLM_TIMEOUT_SECONDS",
    ("llm", "max_retries"): "LLM_MAX_RETRIES",
    ("llm", "max_tokens"): "LLM_MAX_TOKENS",
    ("llm", "user_agent"): "LLM_USER_AGENT",
    ("llm", "request_profile"): "LLM_REQUEST_PROFILE",
    ("notification", "enabled"): "NOTIFICATION_ENABLED",
    ("notification", "smtp_host"): "SMTP_HOST",
    ("notification", "smtp_port"): "SMTP_PORT",
    ("notification", "smtp_username"): "SMTP_USERNAME",
    ("notification", "smtp_password"): "SMTP_PASSWORD",
    ("notification", "email_from"): "EMAIL_FROM",
    ("notification", "email_to"): "EMAIL_TO",
    ("notification", "webhook_url"): "NOTIFY_WEBHOOK_URL",
    ("storage", "mongo_uri"): "MONGO_URI",
    ("storage", "mongo_db"): "MONGO_DB",
    ("storage", "mongo_timeout_ms"): "MONGO_TIMEOUT_MS",
    ("storage", "redis_url"): "REDIS_URL",
    ("smart_search", "enabled"): "SMART_SEARCH_ENABLED",
    ("smart_search", "timeout_seconds"): "SMART_SEARCH_TIMEOUT_SECONDS",
    ("scheduler", "enabled"): "SCHEDULER_ENABLED",
    ("scheduler", "timezone"): "SCHEDULER_TIMEZONE",
    ("scheduler", "daily_run_time"): "SCHEDULER_DAILY_RUN_TIME",
    ("scheduler", "stop_loss_interval_minutes"): "SCHEDULER_STOP_LOSS_INTERVAL_MINUTES",
    ("scheduler", "notify_after_daily_run"): "SCHEDULER_NOTIFY_AFTER_DAILY_RUN",
    ("scheduler", "max_count"): "SCHEDULER_MAX_COUNT",
    ("scheduler", "history_days"): "SCHEDULER_HISTORY_DAYS",
    ("scheduler", "output_dir"): "SCHEDULER_OUTPUT_DIR",
    ("scheduler", "models"): "SCHEDULER_MODELS",
}


def _load_dotenv_into_environ(path: Path, *, skip_keys: set[str] | None = None) -> None:
    """Load local .env values without overriding real environment variables."""
    if not path.exists():
        return
    skip_keys = skip_keys or set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key in skip_keys:
            if _DOTENV_LOADED_VALUES.get(key) == os.environ.get(key):
                os.environ.pop(key, None)
                _DOTENV_LOADED_VALUES.pop(key, None)
            continue
        if key in os.environ:
            continue
        os.environ[key] = value
        _DOTENV_LOADED_VALUES[key] = value


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _to_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_or_default(name: str, default: str = "") -> str:
    """Return an environment value only when it is non-empty."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_nested_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_runtime_overrides(path: Path | None = None) -> dict[str, Any]:
    """Load runtime UI overrides persisted outside Git."""
    return _load_json(path or RUNTIME_CONFIG_PATH)


def save_runtime_overrides(payload: dict[str, Any], path: Path | None = None) -> Path:
    """Persist runtime UI overrides to a local JSON file."""
    target = path or RUNTIME_CONFIG_PATH
    current = load_runtime_overrides(target)
    merged = _merge_nested_dicts(current, payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _runtime_env_keys(runtime_overrides: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for (section_name, field_name), env_name in RUNTIME_ENV_FIELD_MAP.items():
        section = runtime_overrides.get(section_name, {})
        if isinstance(section, dict) and field_name in section:
            keys.add(env_name)
    return keys


@dataclass(slots=True)
class DataSettings:
    mode: str = "offline"
    offline_data_path: str = "data/samples/stocks.json"
    dynamic_universe_limit: int = 20
    provider_chain: list[str] = field(default_factory=lambda: ["tushare", "baostock", "akshare"])
    tushare_token: str = ""
    alpha_vantage_api_key: str = ""
    jqdata_username: str = ""
    jqdata_password: str = ""
    ifind_access_token: str = ""
    ifind_refresh_token: str = ""
    ifind_base_url: str = "https://quantapi.51ifind.com/api/v1"


@dataclass(slots=True)
class PortfolioSettings:
    initial_capital: float = 100000.0
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage_rate: float = 0.001


@dataclass(slots=True)
class RiskSettings:
    max_position_per_stock: float = 0.10
    max_total_position: float = 0.50
    stop_loss_pct: float = 0.05
    max_volatility: float = 0.35
    min_turnover: float = 100000000.0


@dataclass(slots=True)
class LLMSettings:
    base_url: str = "https://example.com/v1"
    api_key: str = ""
    default_model: str = ""
    timeout_seconds: int = 60
    max_retries: int = 3
    max_tokens: int = 512
    user_agent: str = ""
    request_profile: str = "openai"


@dataclass(slots=True)
class NotificationSettings:
    enabled: bool = False
    channels: list[str] = field(default_factory=list)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""
    webhook_url: str = ""


@dataclass(slots=True)
class StorageSettings:
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "astock_agent_system"
    mongo_timeout_ms: int = 3000
    redis_url: str = "redis://localhost:6379/0"


@dataclass(slots=True)
class SmartSearchSettings:
    enabled: bool = True
    timeout_seconds: int = 60


@dataclass(slots=True)
class SchedulerSettings:
    enabled: bool = False
    timezone: str = "Asia/Shanghai"
    daily_run_time: str = "15:05"
    stop_loss_interval_minutes: int = 5
    notify_after_daily_run: bool = False
    max_count: int = 3
    history_days: int = 24
    output_dir: str = "reports"
    models: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Settings:
    data: DataSettings = field(default_factory=DataSettings)
    portfolio: PortfolioSettings = field(default_factory=PortfolioSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    notification: NotificationSettings = field(default_factory=NotificationSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    smart_search: SmartSearchSettings = field(default_factory=SmartSearchSettings)
    scheduler: SchedulerSettings = field(default_factory=SchedulerSettings)


def load_settings(config_path: str | None = None) -> Settings:
    """Load safe defaults, optional YAML, and environment overrides."""
    runtime_overrides = load_runtime_overrides()
    _load_dotenv_into_environ(PROJECT_ROOT / ".env", skip_keys=_runtime_env_keys(runtime_overrides))
    raw = _merge_nested_dicts(
        _load_yaml(Path(config_path) if config_path else DEFAULT_CONFIG_PATH),
        runtime_overrides,
    )

    data_raw = raw.get("data", {}) if isinstance(raw.get("data", {}), dict) else {}
    portfolio_raw = raw.get("portfolio", {}) if isinstance(raw.get("portfolio", {}), dict) else {}
    risk_raw = raw.get("risk", {}) if isinstance(raw.get("risk", {}), dict) else {}
    llm_raw = raw.get("llm", {}) if isinstance(raw.get("llm", {}), dict) else {}
    notification_raw = raw.get("notification", {}) if isinstance(raw.get("notification", {}), dict) else {}
    storage_raw = raw.get("storage", {}) if isinstance(raw.get("storage", {}), dict) else {}
    smart_raw = raw.get("smart_search", {}) if isinstance(raw.get("smart_search", {}), dict) else {}
    scheduler_raw = raw.get("scheduler", {}) if isinstance(raw.get("scheduler", {}), dict) else {}

    data = DataSettings(
        mode=_env_or_default("DATA_MODE", str(data_raw.get("mode", "offline"))),
        offline_data_path=_env_or_default("OFFLINE_DATA_PATH", str(data_raw.get("offline_data_path", "data/samples/stocks.json"))),
        dynamic_universe_limit=_to_int(_env_or_default("DYNAMIC_UNIVERSE_LIMIT"), int(data_raw.get("dynamic_universe_limit", 20))),
        provider_chain=_split_csv(_env_or_default("DATA_PROVIDER_CHAIN"))
        or [str(item).strip() for item in data_raw.get("provider_chain", ["tushare", "baostock", "akshare"]) if str(item).strip()],
        tushare_token=_env_or_default("TUSHARE_TOKEN", str(data_raw.get("tushare_token", ""))),
        alpha_vantage_api_key=_env_or_default("ALPHA_VANTAGE_API_KEY", str(data_raw.get("alpha_vantage_api_key", ""))),
        jqdata_username=_env_or_default("JQDATA_USERNAME", str(data_raw.get("jqdata_username", ""))),
        jqdata_password=_env_or_default("JQDATA_PASSWORD", str(data_raw.get("jqdata_password", ""))),
        ifind_access_token=_env_or_default("IFIND_ACCESS_TOKEN", str(data_raw.get("ifind_access_token", ""))),
        ifind_refresh_token=_env_or_default("IFIND_REFRESH_TOKEN", str(data_raw.get("ifind_refresh_token", ""))),
        ifind_base_url=_env_or_default("IFIND_BASE_URL", str(data_raw.get("ifind_base_url", "https://quantapi.51ifind.com/api/v1"))).rstrip("/"),
    )
    portfolio = PortfolioSettings(
        initial_capital=_to_float(_env_or_default("INITIAL_CAPITAL"), float(portfolio_raw.get("initial_capital", 100000))),
        commission_rate=float(portfolio_raw.get("commission_rate", 0.0003)),
        stamp_tax_rate=float(portfolio_raw.get("stamp_tax_rate", 0.001)),
        slippage_rate=float(portfolio_raw.get("slippage_rate", 0.001)),
    )
    risk = RiskSettings(
        max_position_per_stock=_to_float(_env_or_default("MAX_POSITION_PER_STOCK"), float(risk_raw.get("max_position_per_stock", 0.10))),
        max_total_position=_to_float(_env_or_default("MAX_TOTAL_POSITION"), float(risk_raw.get("max_total_position", 0.50))),
        stop_loss_pct=_to_float(_env_or_default("STOP_LOSS_PCT"), float(risk_raw.get("stop_loss_pct", 0.05))),
        max_volatility=float(risk_raw.get("max_volatility", 0.35)),
        min_turnover=float(risk_raw.get("min_turnover", 100000000)),
    )
    llm = LLMSettings(
        base_url=_env_or_default("LLM_BASE_URL", str(llm_raw.get("base_url", "https://example.com/v1"))).rstrip("/"),
        api_key=_env_or_default("LLM_API_KEY", str(llm_raw.get("api_key", ""))),
        default_model=_env_or_default("LLM_DEFAULT_MODEL", str(llm_raw.get("default_model", ""))),
        timeout_seconds=_to_int(_env_or_default("LLM_TIMEOUT_SECONDS"), int(llm_raw.get("timeout_seconds", 60))),
        max_retries=_to_int(_env_or_default("LLM_MAX_RETRIES"), int(llm_raw.get("max_retries", 3))),
        max_tokens=_to_int(_env_or_default("LLM_MAX_TOKENS"), int(llm_raw.get("max_tokens", 512))),
        user_agent=_env_or_default("LLM_USER_AGENT", str(llm_raw.get("user_agent", ""))),
        request_profile=_env_or_default("LLM_REQUEST_PROFILE", str(llm_raw.get("request_profile", "openai"))).strip().lower(),
    )
    notification = NotificationSettings(
        enabled=_to_bool(_env_or_default("NOTIFICATION_ENABLED"), bool(notification_raw.get("enabled", False))),
        channels=list(notification_raw.get("channels", [])),
        smtp_host=_env_or_default("SMTP_HOST", str(notification_raw.get("smtp_host", ""))),
        smtp_port=_to_int(_env_or_default("SMTP_PORT"), int(notification_raw.get("smtp_port", 587))),
        smtp_username=_env_or_default("SMTP_USERNAME", str(notification_raw.get("smtp_username", ""))),
        smtp_password=_env_or_default("SMTP_PASSWORD", str(notification_raw.get("smtp_password", ""))),
        email_from=_env_or_default("EMAIL_FROM", str(notification_raw.get("email_from", ""))),
        email_to=_env_or_default("EMAIL_TO", str(notification_raw.get("email_to", ""))),
        webhook_url=_env_or_default("NOTIFY_WEBHOOK_URL", str(notification_raw.get("webhook_url", ""))),
    )
    storage = StorageSettings(
        mongo_uri=_env_or_default("MONGO_URI", str(storage_raw.get("mongo_uri", "mongodb://localhost:27017"))),
        mongo_db=_env_or_default("MONGO_DB", str(storage_raw.get("mongo_db", "astock_agent_system"))),
        mongo_timeout_ms=_to_int(_env_or_default("MONGO_TIMEOUT_MS"), int(storage_raw.get("mongo_timeout_ms", 3000))),
        redis_url=_env_or_default("REDIS_URL", str(storage_raw.get("redis_url", "redis://localhost:6379/0"))),
    )
    smart_search = SmartSearchSettings(
        enabled=_to_bool(_env_or_default("SMART_SEARCH_ENABLED"), bool(smart_raw.get("enabled", True))),
        timeout_seconds=_to_int(_env_or_default("SMART_SEARCH_TIMEOUT_SECONDS"), int(smart_raw.get("timeout_seconds", 60))),
    )
    scheduler = SchedulerSettings(
        enabled=_to_bool(_env_or_default("SCHEDULER_ENABLED"), bool(scheduler_raw.get("enabled", False))),
        timezone=_env_or_default("SCHEDULER_TIMEZONE", str(scheduler_raw.get("timezone", "Asia/Shanghai"))),
        daily_run_time=_env_or_default("SCHEDULER_DAILY_RUN_TIME", str(scheduler_raw.get("daily_run_time", "15:05"))),
        stop_loss_interval_minutes=_to_int(
            _env_or_default("STOP_LOSS_INTERVAL_MINUTES"),
            int(scheduler_raw.get("stop_loss_interval_minutes", 5)),
        ),
        notify_after_daily_run=_to_bool(
            _env_or_default("SCHEDULER_NOTIFY_AFTER_DAILY_RUN"),
            bool(scheduler_raw.get("notify_after_daily_run", False)),
        ),
        max_count=_to_int(_env_or_default("SCHEDULER_MAX_COUNT"), int(scheduler_raw.get("max_count", 3))),
        history_days=_to_int(_env_or_default("SCHEDULER_HISTORY_DAYS"), int(scheduler_raw.get("history_days", 24))),
        output_dir=_env_or_default("SCHEDULER_OUTPUT_DIR", str(scheduler_raw.get("output_dir", "reports"))),
        models=_split_csv(_env_or_default("SCHEDULER_MODELS"))
        or [str(item).strip() for item in scheduler_raw.get("models", []) if str(item).strip()],
    )
    return Settings(
        data=data,
        portfolio=portfolio,
        risk=risk,
        llm=llm,
        notification=notification,
        storage=storage,
        smart_search=smart_search,
        scheduler=scheduler,
    )
