"""Configuration loading for the A-share agent system.

Real credentials are read from environment variables or the local ``.env`` file.
The checked-in YAML files provide safe defaults for offline development.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def _load_dotenv_into_environ(path: Path) -> None:
    """Load local .env values without overriding real environment variables."""
    if not path.exists():
        return
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
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


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


@dataclass(slots=True)
class DataSettings:
    mode: str = "offline"
    offline_data_path: str = "data/samples/stocks.json"
    dynamic_universe_limit: int = 20
    tushare_token: str = ""


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
    enabled: bool = False
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
    _load_dotenv_into_environ(PROJECT_ROOT / ".env")
    raw = _load_yaml(Path(config_path) if config_path else DEFAULT_CONFIG_PATH)

    data_raw = raw.get("data", {}) if isinstance(raw.get("data", {}), dict) else {}
    portfolio_raw = raw.get("portfolio", {}) if isinstance(raw.get("portfolio", {}), dict) else {}
    risk_raw = raw.get("risk", {}) if isinstance(raw.get("risk", {}), dict) else {}
    llm_raw = raw.get("llm", {}) if isinstance(raw.get("llm", {}), dict) else {}
    notification_raw = raw.get("notification", {}) if isinstance(raw.get("notification", {}), dict) else {}
    storage_raw = raw.get("storage", {}) if isinstance(raw.get("storage", {}), dict) else {}
    smart_raw = raw.get("smart_search", {}) if isinstance(raw.get("smart_search", {}), dict) else {}
    scheduler_raw = raw.get("scheduler", {}) if isinstance(raw.get("scheduler", {}), dict) else {}

    data = DataSettings(
        mode=os.getenv("DATA_MODE", str(data_raw.get("mode", "offline"))),
        offline_data_path=os.getenv("OFFLINE_DATA_PATH", str(data_raw.get("offline_data_path", "data/samples/stocks.json"))),
        dynamic_universe_limit=_to_int(os.getenv("DYNAMIC_UNIVERSE_LIMIT"), int(data_raw.get("dynamic_universe_limit", 20))),
        tushare_token=os.getenv("TUSHARE_TOKEN", ""),
    )
    portfolio = PortfolioSettings(
        initial_capital=_to_float(os.getenv("INITIAL_CAPITAL"), float(portfolio_raw.get("initial_capital", 100000))),
        commission_rate=float(portfolio_raw.get("commission_rate", 0.0003)),
        stamp_tax_rate=float(portfolio_raw.get("stamp_tax_rate", 0.001)),
        slippage_rate=float(portfolio_raw.get("slippage_rate", 0.001)),
    )
    risk = RiskSettings(
        max_position_per_stock=_to_float(os.getenv("MAX_POSITION_PER_STOCK"), float(risk_raw.get("max_position_per_stock", 0.10))),
        max_total_position=_to_float(os.getenv("MAX_TOTAL_POSITION"), float(risk_raw.get("max_total_position", 0.50))),
        stop_loss_pct=_to_float(os.getenv("STOP_LOSS_PCT"), float(risk_raw.get("stop_loss_pct", 0.05))),
        max_volatility=float(risk_raw.get("max_volatility", 0.35)),
        min_turnover=float(risk_raw.get("min_turnover", 100000000)),
    )
    llm = LLMSettings(
        base_url=os.getenv("LLM_BASE_URL", str(llm_raw.get("base_url", "https://example.com/v1"))).rstrip("/"),
        api_key=os.getenv("LLM_API_KEY", ""),
        default_model=os.getenv("LLM_DEFAULT_MODEL", str(llm_raw.get("default_model", ""))),
        timeout_seconds=_to_int(os.getenv("LLM_TIMEOUT_SECONDS"), int(llm_raw.get("timeout_seconds", 60))),
        max_retries=_to_int(os.getenv("LLM_MAX_RETRIES"), int(llm_raw.get("max_retries", 3))),
        max_tokens=_to_int(os.getenv("LLM_MAX_TOKENS"), int(llm_raw.get("max_tokens", 512))),
        user_agent=os.getenv("LLM_USER_AGENT", str(llm_raw.get("user_agent", ""))),
        request_profile=os.getenv("LLM_REQUEST_PROFILE", str(llm_raw.get("request_profile", "openai"))).strip().lower(),
    )
    notification = NotificationSettings(
        enabled=_to_bool(os.getenv("NOTIFICATION_ENABLED"), bool(notification_raw.get("enabled", False))),
        channels=list(notification_raw.get("channels", [])),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=_to_int(os.getenv("SMTP_PORT"), 587),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("EMAIL_FROM", ""),
        email_to=os.getenv("EMAIL_TO", ""),
        webhook_url=os.getenv("NOTIFY_WEBHOOK_URL", ""),
    )
    storage = StorageSettings(
        mongo_uri=os.getenv("MONGO_URI", str(storage_raw.get("mongo_uri", "mongodb://localhost:27017"))),
        mongo_db=os.getenv("MONGO_DB", str(storage_raw.get("mongo_db", "astock_agent_system"))),
        mongo_timeout_ms=_to_int(os.getenv("MONGO_TIMEOUT_MS"), int(storage_raw.get("mongo_timeout_ms", 3000))),
        redis_url=os.getenv("REDIS_URL", str(storage_raw.get("redis_url", "redis://localhost:6379/0"))),
    )
    smart_search = SmartSearchSettings(
        enabled=_to_bool(os.getenv("SMART_SEARCH_ENABLED"), bool(smart_raw.get("enabled", False))),
        timeout_seconds=_to_int(os.getenv("SMART_SEARCH_TIMEOUT_SECONDS"), int(smart_raw.get("timeout_seconds", 60))),
    )
    scheduler = SchedulerSettings(
        enabled=_to_bool(os.getenv("SCHEDULER_ENABLED"), bool(scheduler_raw.get("enabled", False))),
        timezone=os.getenv("SCHEDULER_TIMEZONE", str(scheduler_raw.get("timezone", "Asia/Shanghai"))),
        daily_run_time=os.getenv("SCHEDULER_DAILY_RUN_TIME", str(scheduler_raw.get("daily_run_time", "15:05"))),
        stop_loss_interval_minutes=_to_int(
            os.getenv("STOP_LOSS_INTERVAL_MINUTES"),
            int(scheduler_raw.get("stop_loss_interval_minutes", 5)),
        ),
        notify_after_daily_run=_to_bool(
            os.getenv("SCHEDULER_NOTIFY_AFTER_DAILY_RUN"),
            bool(scheduler_raw.get("notify_after_daily_run", False)),
        ),
        max_count=_to_int(os.getenv("SCHEDULER_MAX_COUNT"), int(scheduler_raw.get("max_count", 3))),
        history_days=_to_int(os.getenv("SCHEDULER_HISTORY_DAYS"), int(scheduler_raw.get("history_days", 24))),
        output_dir=os.getenv("SCHEDULER_OUTPUT_DIR", str(scheduler_raw.get("output_dir", "reports"))),
        models=_split_csv(os.getenv("SCHEDULER_MODELS"))
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
