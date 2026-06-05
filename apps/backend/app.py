"""FastAPI adapter for the modern desktop UI.

This module is intentionally thin: it exposes product-facing HTTP/WebSocket
endpoints while delegating trading and LLM behavior to the existing Python
business core under ``src/astock_agent_system``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from apps.backend.adapters import (
    decision_logs_from_result,
    equity_metrics_from_result,
    rankings_from_result,
    stock_board_from_result,
)
from apps.backend.schemas import (
    AgentFlowEdge,
    AgentFlowNode,
    AgentFlowNodeData,
    AgentFlowResponse,
    DecisionLogEntry,
    BackendEvent,
    DecisionLogResponse,
    EquityMetricPoint,
    EquityMetricsResponse,
    EVENT_TYPES,
    HoldingRow,
    RankingRow,
    RankingsResponse,
    RunStatusResponse,
    StockCandidate,
    StockBoardResponse,
    TradeRow,
)
from astock_agent_system.config import Settings, load_settings, save_runtime_overrides
from astock_agent_system.llm import LLMClient, ModelBench
from astock_agent_system.scheduler import TradingTaskScheduler


APP_TITLE = "AStock Agent Modern Backend"


class BenchRequest(BaseModel):
    """Request payload for a lightweight LLM benchmark."""

    models: list[str] | None = None
    prompt: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
    list_models: bool = False


class AutoInvestmentRequest(BaseModel):
    """Request payload for one automatic paper-investment round."""

    models: list[str] | None = None
    offline: bool = False
    max_count: int | None = Field(default=None, ge=1, le=100)
    days: int | None = Field(default=None, ge=1, le=365)


class ConfigUpdateRequest(BaseModel):
    """Partial runtime configuration patch from the modern UI."""

    config: dict[str, Any] = Field(default_factory=dict)


class EventHub:
    """Small in-process broadcaster for the first desktop UI skeleton."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        await websocket.send_json(make_event("connection_established", payload={"event_types": sorted(EVENT_TYPES)}))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        dead_connections: list[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(event)
            except Exception:  # pragma: no cover - depends on client lifecycle
                dead_connections.append(websocket)
        for websocket in dead_connections:
            self.disconnect(websocket)


class RunStore:
    """In-memory state bridge until Mongo-backed API reads are added."""

    def __init__(self) -> None:
        self.current_run: dict[str, Any] | None = None
        self.last_run: dict[str, Any] | None = None
        self.last_result: dict[str, Any] | None = None
        self.decisions: list[DecisionLogEntry] = []
        self.holdings: list[HoldingRow] = []
        self.candidates: list[StockCandidate] = []
        self.trades: list[TradeRow] = []
        self.equity_series: list[EquityMetricPoint] = []
        self.rankings: list[RankingRow] = []

    def start(self, run_id: str, request_payload: dict[str, Any]) -> None:
        self.current_run = {
            "run_id": run_id,
            "status": "running",
            "started_at": _now_iso(),
            "request": request_payload,
        }

    def complete(self, run_id: str, result_payload: dict[str, Any]) -> None:
        status = str(result_payload.get("status", "unknown"))
        completed = {
            "run_id": run_id,
            "status": status,
            "finished_at": _now_iso(),
            "task_name": result_payload.get("task_name", ""),
            "message": result_payload.get("message", ""),
        }
        self.current_run = None
        self.last_run = completed
        self.last_result = result_payload
        self.decisions = decision_logs_from_result(result_payload, run_id)
        self.holdings, self.candidates, self.trades = stock_board_from_result(result_payload)
        self.equity_series = equity_metrics_from_result(result_payload)
        self.rankings = rankings_from_result(result_payload)

    def status_response(self) -> RunStatusResponse:
        if self.current_run is not None:
            return RunStatusResponse(status="running", run=self.current_run)
        return RunStatusResponse(status="idle", run=self.last_run)


event_hub = EventHub()
run_store = RunStore()


def create_app() -> FastAPI:
    """Create the FastAPI app used by Tauri sidecar and local dev servers."""
    api = FastAPI(title=APP_TITLE, version="0.1.0")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app": APP_TITLE,
            "time": _now_iso(),
            "event_types": sorted(EVENT_TYPES),
        }

    @api.get("/api/config")
    def get_config() -> dict[str, Any]:
        return {"status": "ok", "config": settings_to_public_dict(load_settings())}

    @api.post("/api/config")
    async def update_config(request: ConfigUpdateRequest) -> dict[str, Any]:
        overrides = _sanitize_runtime_config(request.config)
        if overrides:
            save_runtime_overrides(overrides)
            _apply_runtime_overrides_to_environ(overrides)
            await event_hub.broadcast(
                make_event(
                    "config_updated",
                    payload={"sections": sorted(overrides), "message": "runtime configuration updated"},
                )
            )
        return {"status": "ok", "config": settings_to_public_dict(load_settings())}

    @api.post("/api/bench")
    async def run_bench(request: BenchRequest) -> dict[str, Any]:
        settings = load_settings()
        client = LLMClient(settings)
        if request.list_models:
            payload = await asyncio.to_thread(client.list_models_safe)
        else:
            payload = await asyncio.to_thread(
                ModelBench(client).run,
                models=request.models,
                prompt=request.prompt or "请只输出 JSON：{\"score\": 0.5, \"label\": \"ok\", \"reason\": \"模型连通性测试\"}",
                limit=request.limit,
            )
        return payload

    @api.post("/api/auto-investment")
    async def run_auto_investment(request: AutoInvestmentRequest) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        request_payload = request.model_dump()
        run_store.start(run_id, request_payload)
        await event_hub.broadcast(make_event("run_started", run_id=run_id, payload=request_payload))
        flow_task = asyncio.create_task(_broadcast_agent_flow(run_id))
        result = await asyncio.to_thread(_run_auto_investment_sync, request)
        await flow_task
        result_payload = result.to_dict()
        run_store.complete(run_id, result_payload)
        event_type = "run_completed" if result.status == "ok" else "run_failed"
        for decision in run_store.decisions:
            await event_hub.broadcast(make_event("decision_made", run_id=run_id, agent_id=decision.agent_id, payload=decision.model_dump(mode="json")))
        for trade in run_store.trades:
            await event_hub.broadcast(make_event("trade_executed", run_id=run_id, agent_id=trade.agent_id, payload=trade.model_dump(mode="json")))
        await event_hub.broadcast(
            make_event(
                event_type,
                run_id=run_id,
                payload={"task_name": result.task_name, "status": result.status, "message": result.message},
            )
        )
        return {"status": result.status, "run_id": run_id, "result": result_payload}

    @api.get("/api/agents/flow")
    def get_agent_flow() -> dict[str, Any]:
        return AgentFlowResponse(nodes=_default_flow_nodes(), edges=_default_flow_edges()).model_dump(mode="json")

    @api.get("/api/decisions")
    def get_decisions() -> dict[str, Any]:
        next_steps = [] if run_store.decisions else ["Run /api/auto-investment to create decision records."]
        return DecisionLogResponse(items=run_store.decisions, next_steps=next_steps).model_dump(mode="json")

    @api.get("/api/stocks/board")
    def get_stock_board() -> dict[str, Any]:
        return StockBoardResponse(holdings=run_store.holdings, candidates=run_store.candidates, trades=run_store.trades).model_dump(mode="json")

    @api.get("/api/metrics/equity")
    def get_equity_metrics() -> dict[str, Any]:
        next_steps = [] if run_store.equity_series else ["Persist multi-day snapshots before charting equity."]
        return EquityMetricsResponse(series=run_store.equity_series, next_steps=next_steps).model_dump(mode="json")

    @api.get("/api/metrics/rankings")
    def get_rankings() -> dict[str, Any]:
        return RankingsResponse(rankings=run_store.rankings).model_dump(mode="json")

    @api.get("/api/runs/current")
    def get_current_run() -> dict[str, Any]:
        return run_store.status_response().model_dump(mode="json")

    @api.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        await event_hub.connect(websocket)
        try:
            while True:
                message = await websocket.receive_json()
                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json(make_event("pong", payload={"echo": message.get("payload", {})}))
        except WebSocketDisconnect:
            event_hub.disconnect(websocket)

    return api


def make_event(
    event_type: str,
    *,
    run_id: str = "",
    agent_id: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a frontend-safe event envelope."""
    safe_type = event_type if event_type in EVENT_TYPES else "error"
    return BackendEvent(type=safe_type, timestamp=_now_iso(), run_id=run_id, agent_id=agent_id, payload=payload or {}).model_dump(mode="json")


def settings_to_public_dict(settings: Settings) -> dict[str, Any]:
    """Return configuration metadata without exposing local secrets."""
    return {
        "data": {
            "mode": settings.data.mode,
            "offline_data_path": settings.data.offline_data_path,
            "dynamic_universe_limit": settings.data.dynamic_universe_limit,
            "has_tushare_token": bool(settings.data.tushare_token),
        },
        "portfolio": {
            "initial_capital": settings.portfolio.initial_capital,
            "commission_rate": settings.portfolio.commission_rate,
            "stamp_tax_rate": settings.portfolio.stamp_tax_rate,
            "slippage_rate": settings.portfolio.slippage_rate,
        },
        "risk": {
            "max_position_per_stock": settings.risk.max_position_per_stock,
            "max_total_position": settings.risk.max_total_position,
            "stop_loss_pct": settings.risk.stop_loss_pct,
            "max_volatility": settings.risk.max_volatility,
            "min_turnover": settings.risk.min_turnover,
        },
        "llm": {
            "base_url": settings.llm.base_url,
            "has_api_key": bool(settings.llm.api_key),
            "default_model": settings.llm.default_model,
            "request_profile": settings.llm.request_profile,
            "max_tokens": settings.llm.max_tokens,
            "timeout_seconds": settings.llm.timeout_seconds,
            "max_retries": settings.llm.max_retries,
            "has_user_agent": bool(settings.llm.user_agent),
        },
        "notification": {
            "enabled": settings.notification.enabled,
            "channels": settings.notification.channels,
            "smtp_host": settings.notification.smtp_host,
            "smtp_port": settings.notification.smtp_port,
            "has_smtp_username": bool(settings.notification.smtp_username),
            "has_smtp_password": bool(settings.notification.smtp_password),
            "has_email_from": bool(settings.notification.email_from),
            "has_email_to": bool(settings.notification.email_to),
            "has_webhook_url": bool(settings.notification.webhook_url),
        },
        "storage": {
            "mongo_uri": _redact_url_credentials(settings.storage.mongo_uri),
            "mongo_db": settings.storage.mongo_db,
            "mongo_timeout_ms": settings.storage.mongo_timeout_ms,
            "redis_url": _redact_url_credentials(settings.storage.redis_url),
        },
        "scheduler": {
            "enabled": settings.scheduler.enabled,
            "timezone": settings.scheduler.timezone,
            "daily_run_time": settings.scheduler.daily_run_time,
            "stop_loss_interval_minutes": settings.scheduler.stop_loss_interval_minutes,
            "notify_after_daily_run": settings.scheduler.notify_after_daily_run,
            "max_count": settings.scheduler.max_count,
            "history_days": settings.scheduler.history_days,
            "output_dir": settings.scheduler.output_dir,
            "models": settings.scheduler.models,
        },
    }


def _run_auto_investment_sync(request: AutoInvestmentRequest):
    settings = load_settings()
    if request.offline:
        settings.data.mode = "offline"
    if request.max_count is not None:
        settings.scheduler.max_count = int(request.max_count)
    if request.days is not None:
        settings.scheduler.history_days = int(request.days)
    return TradingTaskScheduler(settings=settings).run_auto_investment(models=request.models)


async def _broadcast_agent_flow(run_id: str) -> None:
    phases = [
        ("data_agent", "正在读取行情、财务与仓位快照"),
        ("screener", "正在筛选今日候选股票池"),
        ("technical_analyst", "技术分析 Agent 正在评估趋势与形态"),
        ("fundamental_analyst", "基本面 Agent 正在评估财务质量"),
        ("sentiment_analyst", "舆情 Agent 正在聚合市场情绪"),
        ("debate_room", "多 Agent 正在汇总观点并形成讨论结论"),
        ("risk_manager", "风控 Agent 正在检查止损与仓位上限"),
        ("portfolio_manager", "组合 Agent 正在生成执行动作"),
    ]
    total_steps = len(phases)
    for index, (agent_id, message) in enumerate(phases, start=1):
        progress = round(index / total_steps, 2)
        await event_hub.broadcast(
            make_event(
                "agent_started",
                run_id=run_id,
                agent_id=agent_id,
                payload={"message": message, "progress": progress, "step": index, "total_steps": total_steps},
            )
        )
        await asyncio.sleep(0.25)
        await event_hub.broadcast(
            make_event(
                "agent_step",
                run_id=run_id,
                agent_id=agent_id,
                payload={"message": message, "progress": progress, "step": index, "total_steps": total_steps},
            )
        )
        await asyncio.sleep(0.2)
        complete_event = "risk_checked" if agent_id == "risk_manager" else "agent_completed"
        await event_hub.broadcast(
            make_event(
                complete_event,
                run_id=run_id,
                agent_id=agent_id,
                payload={"message": f"{message} - 已完成", "progress": progress, "step": index, "total_steps": total_steps},
            )
        )
        await asyncio.sleep(0.12)


def _sanitize_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_fields: dict[str, dict[str, str]] = {
        "data": {
            "mode": "str",
            "offline_data_path": "str",
            "dynamic_universe_limit": "int",
            "tushare_token": "str",
        },
        "portfolio": {
            "initial_capital": "float",
            "commission_rate": "float",
            "stamp_tax_rate": "float",
            "slippage_rate": "float",
        },
        "risk": {
            "max_position_per_stock": "float",
            "max_total_position": "float",
            "stop_loss_pct": "float",
            "max_volatility": "float",
            "min_turnover": "float",
        },
        "llm": {
            "base_url": "str",
            "api_key": "str",
            "default_model": "str",
            "request_profile": "str",
            "max_tokens": "int",
            "timeout_seconds": "int",
            "max_retries": "int",
            "user_agent": "str",
        },
        "notification": {
            "enabled": "bool",
            "channels": "list[str]",
            "smtp_host": "str",
            "smtp_port": "int",
            "smtp_username": "str",
            "smtp_password": "str",
            "email_from": "str",
            "email_to": "str",
            "webhook_url": "str",
        },
        "storage": {
            "mongo_uri": "str",
            "mongo_db": "str",
            "mongo_timeout_ms": "int",
            "redis_url": "str",
        },
        "scheduler": {
            "enabled": "bool",
            "timezone": "str",
            "daily_run_time": "str",
            "stop_loss_interval_minutes": "int",
            "notify_after_daily_run": "bool",
            "max_count": "int",
            "history_days": "int",
            "output_dir": "str",
            "models": "list[str]",
        },
    }
    sanitized: dict[str, Any] = {}
    for section, fields in allowed_fields.items():
        section_payload = payload.get(section)
        if not isinstance(section_payload, dict):
            continue
        clean_section: dict[str, Any] = {}
        for field_name, field_type in fields.items():
            if field_name not in section_payload:
                continue
            value = section_payload[field_name]
            if field_type == "bool":
                clean_section[field_name] = bool(value)
            elif field_type == "int":
                try:
                    clean_section[field_name] = int(value)
                except (TypeError, ValueError):
                    continue
            elif field_type == "float":
                try:
                    clean_section[field_name] = float(value)
                except (TypeError, ValueError):
                    continue
            elif field_type == "list[str]":
                if isinstance(value, list):
                    clean_section[field_name] = [str(item).strip() for item in value if str(item).strip()]
                elif isinstance(value, str):
                    clean_section[field_name] = [item.strip() for item in value.split(",") if item.strip()]
            else:
                clean_section[field_name] = str(value).strip() if value is not None else ""
        if clean_section:
            sanitized[section] = clean_section
    return sanitized


def _apply_runtime_overrides_to_environ(payload: dict[str, Any]) -> None:
    env_mapping = {
        ("data", "mode"): "DATA_MODE",
        ("data", "offline_data_path"): "OFFLINE_DATA_PATH",
        ("data", "dynamic_universe_limit"): "DYNAMIC_UNIVERSE_LIMIT",
        ("data", "tushare_token"): "TUSHARE_TOKEN",
        ("portfolio", "initial_capital"): "INITIAL_CAPITAL",
        ("risk", "max_position_per_stock"): "MAX_POSITION_PER_STOCK",
        ("risk", "max_total_position"): "MAX_TOTAL_POSITION",
        ("risk", "stop_loss_pct"): "STOP_LOSS_PCT",
        ("llm", "base_url"): "LLM_BASE_URL",
        ("llm", "api_key"): "LLM_API_KEY",
        ("llm", "default_model"): "LLM_DEFAULT_MODEL",
        ("llm", "request_profile"): "LLM_REQUEST_PROFILE",
        ("llm", "max_tokens"): "LLM_MAX_TOKENS",
        ("llm", "timeout_seconds"): "LLM_TIMEOUT_SECONDS",
        ("llm", "max_retries"): "LLM_MAX_RETRIES",
        ("llm", "user_agent"): "LLM_USER_AGENT",
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
        ("scheduler", "enabled"): "SCHEDULER_ENABLED",
        ("scheduler", "timezone"): "SCHEDULER_TIMEZONE",
        ("scheduler", "daily_run_time"): "SCHEDULER_DAILY_RUN_TIME",
        ("scheduler", "stop_loss_interval_minutes"): "STOP_LOSS_INTERVAL_MINUTES",
        ("scheduler", "notify_after_daily_run"): "SCHEDULER_NOTIFY_AFTER_DAILY_RUN",
        ("scheduler", "max_count"): "SCHEDULER_MAX_COUNT",
        ("scheduler", "history_days"): "SCHEDULER_HISTORY_DAYS",
        ("scheduler", "output_dir"): "SCHEDULER_OUTPUT_DIR",
        ("scheduler", "models"): "SCHEDULER_MODELS",
    }
    for (section, field_name), env_name in env_mapping.items():
        section_payload = payload.get(section)
        if not isinstance(section_payload, dict) or field_name not in section_payload:
            continue
        value = section_payload[field_name]
        if isinstance(value, list):
            os.environ[env_name] = ",".join(str(item) for item in value)
        elif isinstance(value, bool):
            os.environ[env_name] = "true" if value else "false"
        else:
            os.environ[env_name] = str(value)


def _default_flow_nodes() -> list[AgentFlowNode]:
    return [
        AgentFlowNode(id="data_agent", position={"x": 0, "y": 120}, data=AgentFlowNodeData(label="数据 Agent")),
        AgentFlowNode(id="screener", position={"x": 220, "y": 120}, data=AgentFlowNodeData(label="股票筛选")),
        AgentFlowNode(id="technical_analyst", position={"x": 460, "y": 0}, data=AgentFlowNodeData(label="技术分析")),
        AgentFlowNode(id="fundamental_analyst", position={"x": 460, "y": 120}, data=AgentFlowNodeData(label="基本面分析")),
        AgentFlowNode(id="sentiment_analyst", position={"x": 460, "y": 240}, data=AgentFlowNodeData(label="舆情分析")),
        AgentFlowNode(id="debate_room", position={"x": 720, "y": 120}, data=AgentFlowNodeData(label="多 Agent 讨论")),
        AgentFlowNode(id="risk_manager", position={"x": 960, "y": 120}, data=AgentFlowNodeData(label="风控检查")),
        AgentFlowNode(id="portfolio_manager", position={"x": 1200, "y": 120}, data=AgentFlowNodeData(label="组合执行")),
    ]


def _default_flow_edges() -> list[AgentFlowEdge]:
    edge_pairs = [
        ("data_agent", "screener"),
        ("screener", "technical_analyst"),
        ("screener", "fundamental_analyst"),
        ("screener", "sentiment_analyst"),
        ("technical_analyst", "debate_room"),
        ("fundamental_analyst", "debate_room"),
        ("sentiment_analyst", "debate_room"),
        ("debate_room", "risk_manager"),
        ("risk_manager", "portfolio_manager"),
    ]
    return [AgentFlowEdge(id=f"{source}-{target}", source=source, target=target, animated=True) for source, target in edge_pairs]


def _redact_url_credentials(value: str) -> str:
    if not value:
        return value
    parts = urlsplit(value)
    if "@" not in parts.netloc:
        return value
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"[REDACTED]@{host}", parts.path, parts.query, parts.fragment))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


app = create_app()
