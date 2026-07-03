"""FastAPI adapter for the modern desktop UI.

This module is intentionally thin: it exposes product-facing HTTP/WebSocket
endpoints while delegating trading and LLM behavior to the existing Python
business core under ``src/astock_agent_system``.
"""

from __future__ import annotations

import asyncio
import copy
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
    AgentMemoryResponse,
    AgentToolsResponse,
    DecisionLogEntry,
    BackendEvent,
    DecisionLogResponse,
    EquityMetricPoint,
    EquityMetricsResponse,
    EventTimelineResponse,
    EVENT_TYPES,
    HoldingRow,
    LlmConfigCheckResponse,
    RankingRow,
    RankingsResponse,
    RunStatusResponse,
    StockCandidate,
    StockBoardResponse,
    TradeRow,
)
from astock_agent_system.agent_descriptor import (
    backup_agent_descriptor,
    list_agent_descriptors,
    load_agent_descriptor,
    load_user_profile,
    rollback_agent_descriptor,
)
from astock_agent_system.agent_learning import get_learning_status, load_learning_suggestions, trigger_learning_if_ready
from astock_agent_system.agent_memory import AgentMemoryStore
from astock_agent_system.config import Settings, load_settings, save_runtime_overrides
from astock_agent_system.data import DataAgent
from astock_agent_system.data.switch_history import load_switch_history, summarize_switch_history, switch_history_path
from astock_agent_system.event_timeline import EventTimelineService, filter_timeline_events
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


class LlmConfigCheckRequest(BaseModel):
    """Validate LLM settings without exposing or persisting secrets."""

    config: dict[str, Any] = Field(default_factory=dict)
    models: list[str] | None = None
    run_bench: bool = False
    limit: int = Field(default=5, ge=1, le=20)


class AgentRollbackRequest(BaseModel):
    """Request to restore one backed-up Agent Markdown descriptor."""

    version_file: str


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
        self.timeline_events: list[dict[str, Any]] = []

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

    def add_timeline_events(self, events: list[dict[str, Any]]) -> None:
        seen = {str(item.get("id", "")) for item in self.timeline_events}
        for event in events:
            event_id = str(event.get("id", ""))
            if event_id and event_id in seen:
                continue
            self.timeline_events.insert(0, event)
            if event_id:
                seen.add(event_id)
        self.timeline_events = self.timeline_events[:100]


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
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?$",
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

    @api.get("/api/data/providers")
    def get_data_providers() -> dict[str, Any]:
        diagnostics = DataAgent(settings=load_settings()).provider_diagnostics()
        return {
            "status": "ok",
            "diagnostics": diagnostics,
            "next_steps": [
                "DATA_PROVIDER_CHAIN controls online fallback order; offline samples remain the final fallback.",
                "AStock 当前只做模拟盘，数据源接入不会触发真实下单。",
            ],
        }

    @api.get("/api/datasource/status")
    def get_datasource_status() -> dict[str, Any]:
        """Return provider-chain diagnostics for CLI/TUI/GUI clients."""
        diagnostics = DataAgent(settings=load_settings()).provider_diagnostics()
        return {
            "status": "ok",
            "datasource": diagnostics,
            "next_steps": [
                "If the primary provider is unavailable, inspect missing credentials and provider-chain order.",
                "CLI: python -m astock_agent_system.cli datasource status",
            ],
        }

    @api.get("/api/datasource/history")
    def get_datasource_history() -> dict[str, Any]:
        """Return persisted datasource switch/attempt history for UI clients."""
        items = load_switch_history(limit=100)
        return {
            "status": "ok",
            "path": str(switch_history_path()),
            "summary": summarize_switch_history(items),
            "items": items,
            "next_steps": [
                "Run foreground CLI agent or datasource smoke commands to append fresh datasource attempts.",
                "Use CLI datasource history --format json for filtered local debugging.",
            ],
        }

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

    @api.post("/api/auto-investment/background")
    async def run_auto_investment_background(request: AutoInvestmentRequest) -> dict[str, Any]:
        if run_store.current_run is not None:
            return {"status": "busy", "run_id": run_store.current_run.get("run_id", ""), "run": run_store.current_run}
        run_id = str(uuid.uuid4())
        request_payload = request.model_dump()
        run_store.start(run_id, request_payload)
        await event_hub.broadcast(make_event("run_started", run_id=run_id, payload=request_payload))
        asyncio.create_task(_run_auto_investment_background(run_id, request))
        return {
            "status": "accepted",
            "run_id": run_id,
            "next_steps": [
                "Poll /api/runs/current for task status.",
                "Use /api/decisions, /api/stocks/board and /api/metrics/rankings after completion.",
            ],
        }

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
        await _broadcast_run_completion(run_id, result.status, result.task_name, result.message)
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

    @api.post("/api/events/poll")
    async def poll_events(limit: int = 20) -> dict[str, Any]:
        events = await asyncio.to_thread(EventTimelineService(load_settings()).poll, limit=limit)
        run_store.add_timeline_events(events)
        for event in events[:5]:
            await event_hub.broadcast(make_event("timeline_event", payload=event))
        return EventTimelineResponse(items=events, next_steps=_event_timeline_next_steps(events)).model_dump(mode="json")

    @api.get("/api/events/timeline")
    def get_event_timeline(category: str = "", source: str = "", limit: int = 50) -> dict[str, Any]:
        if not run_store.timeline_events:
            run_store.add_timeline_events(EventTimelineService(load_settings()).poll(limit=limit))
        items = filter_timeline_events(
            run_store.timeline_events,
            category=category or None,
            source=source or None,
            limit=limit,
        )
        return EventTimelineResponse(items=items, next_steps=_event_timeline_next_steps(items)).model_dump(mode="json")

    @api.get("/api/agents/{agent_id}/memory")
    def get_agent_memory(agent_id: str, stock_code: str = "", outcome: str = "", limit: int = 20) -> dict[str, Any]:
        items = AgentMemoryStore(load_settings()).list_cases(
            agent_id,
            limit=limit,
            stock_code=stock_code,
            outcome=outcome,
        )
        if not items:
            items = _memory_cases_from_current_run(agent_id, stock_code=stock_code, outcome=outcome, limit=limit)
        next_steps = [] if items else ["Run a benchmark round first; memory is isolated per model-driven Agent account."]
        return AgentMemoryResponse(agent_id=agent_id, items=items, next_steps=next_steps).model_dump(mode="json")

    @api.get("/api/agents/descriptors")
    def get_agent_descriptors(include_content: bool = False) -> dict[str, Any]:
        return {
            "status": "ok",
            "items": [descriptor.to_public_dict(include_content=include_content) for descriptor in list_agent_descriptors()],
            "user_profile": load_user_profile().to_context(),
            "next_steps": ["Use /api/agents/{agent_id}/descriptor to inspect one Agent Markdown file."],
        }

    @api.get("/api/agents/{agent_id}/descriptor")
    def get_agent_descriptor(agent_id: str, include_content: bool = True) -> dict[str, Any]:
        descriptor = load_agent_descriptor(agent_id)
        return {"status": "ok", "item": descriptor.to_public_dict(include_content=include_content)}

    @api.post("/api/agents/{agent_id}/descriptor/backup")
    def backup_agent_md(agent_id: str) -> dict[str, Any]:
        path = backup_agent_descriptor(agent_id)
        return {"status": "ok", "backup_path": str(path)}

    @api.post("/api/agents/{agent_id}/descriptor/rollback")
    def rollback_agent_md(agent_id: str, request: AgentRollbackRequest) -> dict[str, Any]:
        path = rollback_agent_descriptor(agent_id, request.version_file)
        return {"status": "ok", "restored_path": str(path)}

    @api.get("/api/agents/learning/status")
    def get_agent_learning_status() -> dict[str, Any]:
        return {"status": "ok", "learning": get_learning_status()}

    @api.get("/api/agents/learning/suggestions")
    def get_agent_learning_suggestions() -> dict[str, Any]:
        return {
            "status": "ok",
            "suggestions": load_learning_suggestions(),
            "next_steps": ["Review suggestions manually before changing any Agent Markdown descriptor."],
        }

    @api.post("/api/agents/learning/trigger")
    def trigger_agent_learning(force: bool = False) -> dict[str, Any]:
        return {"status": "ok", "learning": trigger_learning_if_ready(force=force)}

    @api.get("/api/agents/{agent_id}/memory/similar")
    def get_agent_similar_memory(agent_id: str, stock_code: str = "", outcome: str = "", limit: int = 20) -> dict[str, Any]:
        """Return readonly memory cases filtered by stock/outcome for CLI and future UI use."""
        cases = AgentMemoryStore(load_settings()).list_cases(
            agent_id=agent_id,
            stock_code=stock_code,
            outcome=outcome,
            limit=max(1, min(limit, 100)),
        )
        return AgentMemoryResponse(
            agent_id=agent_id,
            items=cases,
            next_steps=[
                "Memory cases are readonly and isolated by model-driven agent account.",
                "CLI: python -m astock_agent_system.cli agent memory --agent-id <agent-id>",
            ],
        ).model_dump(mode="json")

    @api.post("/api/config/test-llm")
    async def test_llm_config(request: LlmConfigCheckRequest | None = None) -> dict[str, Any]:
        payload = request or LlmConfigCheckRequest()
        settings = _settings_with_runtime_patch(load_settings(), _sanitize_runtime_config(payload.config))
        client = LLMClient(settings)
        diagnostics, warnings = _llm_config_diagnostics(settings)
        models: list[str] = []
        bench_payload: dict[str, Any] | None = None

        if client.is_configured:
            models_payload = await asyncio.to_thread(client.list_models_safe)
            if models_payload.get("status") == "ok":
                models = [str(item) for item in models_payload.get("models", [])]
                diagnostics.append(f"模型列表获取成功：{len(models)} 个模型")
            else:
                warnings.append(str(models_payload.get("reason", "模型列表获取失败")))
                for step in models_payload.get("next_steps", []):
                    diagnostics.append(str(step))
            if payload.run_bench:
                bench_models = payload.models or (models[: payload.limit] if models else None)
                bench_payload = await asyncio.to_thread(ModelBench(client).run, models=bench_models, limit=payload.limit)
        else:
            warnings.append("LLM Base URL 或 API Key 尚未配置，无法连接模型网关。")

        response = LlmConfigCheckResponse(
            configured=client.is_configured,
            base_url=settings.llm.base_url,
            default_model=settings.llm.default_model,
            request_profile=settings.llm.request_profile,
            models=models,
            diagnostics=diagnostics,
            warnings=warnings,
            bench=bench_payload,
        )
        await event_hub.broadcast(make_event("llm_checked", payload=response.model_dump(mode="json")))
        return response.model_dump(mode="json")

    @api.get("/api/agents/tools")
    def get_agent_tools() -> dict[str, Any]:
        return AgentToolsResponse(items=_agent_tool_catalog()).model_dump(mode="json")

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
            "provider_chain": settings.data.provider_chain,
            "has_tushare_token": bool(settings.data.tushare_token),
            "has_alpha_vantage_api_key": bool(settings.data.alpha_vantage_api_key),
            "has_jqdata_username": bool(settings.data.jqdata_username),
            "has_jqdata_password": bool(settings.data.jqdata_password),
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


async def _run_auto_investment_background(run_id: str, request: AutoInvestmentRequest) -> None:
    flow_task = asyncio.create_task(_broadcast_agent_flow(run_id))
    try:
        result = await asyncio.to_thread(_run_auto_investment_sync, request)
        await flow_task
        result_payload = result.to_dict()
        run_store.complete(run_id, result_payload)
        await _broadcast_run_completion(run_id, result.status, result.task_name, result.message)
    except Exception as exc:  # pragma: no cover - runtime safety net
        if not flow_task.done():
            await flow_task
        result_payload = {
            "task_name": "auto_investment",
            "status": "error",
            "started_at": "",
            "finished_at": _now_iso(),
            "message": str(exc),
            "payload": {},
        }
        run_store.complete(run_id, result_payload)
        await event_hub.broadcast(make_event("run_failed", run_id=run_id, payload={"status": "error", "message": str(exc)}))


async def _broadcast_run_completion(run_id: str, status: str, task_name: str, message: str) -> None:
    event_type = "run_completed" if status == "ok" else "run_failed"
    for decision in run_store.decisions:
        await event_hub.broadcast(make_event("decision_made", run_id=run_id, agent_id=decision.agent_id, payload=decision.model_dump(mode="json")))
    for trade in run_store.trades:
        await event_hub.broadcast(make_event("trade_executed", run_id=run_id, agent_id=trade.agent_id, payload=trade.model_dump(mode="json")))
    await event_hub.broadcast(
        make_event(
            event_type,
            run_id=run_id,
            payload={"task_name": task_name, "status": status, "message": message},
        )
    )


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
            "provider_chain": "list[str]",
            "tushare_token": "str",
            "alpha_vantage_api_key": "str",
            "jqdata_username": "str",
            "jqdata_password": "str",
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
        ("data", "provider_chain"): "DATA_PROVIDER_CHAIN",
        ("data", "tushare_token"): "TUSHARE_TOKEN",
        ("data", "alpha_vantage_api_key"): "ALPHA_VANTAGE_API_KEY",
        ("data", "jqdata_username"): "JQDATA_USERNAME",
        ("data", "jqdata_password"): "JQDATA_PASSWORD",
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


def _settings_with_runtime_patch(settings: Settings, payload: dict[str, Any]) -> Settings:
    """Apply a sanitized config patch to an in-memory copy only."""
    patched = copy.deepcopy(settings)
    for section, values in payload.items():
        target = getattr(patched, section, None)
        if target is None or not isinstance(values, dict):
            continue
        for field_name, value in values.items():
            if hasattr(target, field_name):
                setattr(target, field_name, value)
    return patched


def _llm_config_diagnostics(settings: Settings) -> tuple[list[str], list[str]]:
    diagnostics: list[str] = []
    warnings: list[str] = []
    if settings.llm.base_url:
        diagnostics.append(f"Base URL 已设置：{settings.llm.base_url}")
    else:
        warnings.append("LLM Base URL 为空。")
    if settings.llm.api_key:
        diagnostics.append("API Key 已设置且不会回显到前端。")
    else:
        warnings.append("LLM API Key 为空。")
    if settings.llm.default_model:
        diagnostics.append(f"默认模型：{settings.llm.default_model}")
    else:
        warnings.append("默认模型为空；Benchmark 可使用模型列表中的第一个模型或 rule-baseline。")
    if settings.llm.request_profile not in {"openai", "codex", "anthropic", "claude_code", "auto"}:
        warnings.append(f"请求档位 {settings.llm.request_profile!r} 不是常用值，请确认网关兼容。")
    return diagnostics, warnings


def _event_timeline_next_steps(events: list[dict[str, Any]]) -> list[str]:
    if not events:
        return ["No timeline events yet. Trigger /api/events/poll after configuring data sources."]
    categories = {str(event.get("category", "")) for event in events}
    next_steps = ["重大事件会进入 Agent 输入流；普通新闻和公告按批次汇总。"]
    if "data_source" in categories:
        next_steps.append("切换 online 并配置 provider chain 后，可接入真实公告、新闻和行情事件。")
    return next_steps


def _memory_cases_from_current_run(agent_id: str, *, stock_code: str = "", outcome: str = "", limit: int = 20) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, decision in enumerate(run_store.decisions):
        if decision.agent_id != agent_id:
            continue
        if stock_code and decision.stock_code != stock_code:
            continue
        case = {
            "id": f"{agent_id}-runtime-{index}",
            "agent_id": decision.agent_id,
            "llm_model": decision.llm_model,
            "stock_code": decision.stock_code,
            "stock_name": decision.stock_name,
            "decision_date": decision.timestamp,
            "action": decision.action,
            "reason": "；".join(decision.reasons[:3]) or decision.summary,
            "outcome": "unknown",
            "pnl_pct": 0.0,
            "tags": [decision.action.lower(), "runtime"],
            "raw": decision.model_dump(mode="json"),
        }
        if outcome and case["outcome"] != outcome:
            continue
        cases.append(case)
        if len(cases) >= max(1, limit):
            break
    return cases


def _agent_tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "agent_id": "data_agent",
            "agent_name": "数据 Agent",
            "tools": ["DataAgent.get_history", "DataAgent.get_quote", "DataAgent.get_financial"],
            "data_sources": ["offline samples", "Tushare", "AkShare"],
            "skills": ["行情读取", "财务数据归一化", "数据源降级"],
            "notes": "负责把行情、财务、公告和新闻输入整理为后续 Agent 可用的结构化上下文。",
        },
        {
            "agent_id": "screener",
            "agent_name": "股票筛选 Agent",
            "tools": ["StockScreener.screen"],
            "data_sources": ["DataAgent", "历史K线", "财务摘要"],
            "skills": ["动态股票池", "候选股评分"],
            "notes": "按配置的候选数量为每个模型驱动系统生成同一批候选标的，保证 Benchmark 公平。",
        },
        {
            "agent_id": "technical_analyst",
            "agent_name": "技术分析 Agent",
            "tools": ["TechnicalAnalyst.analyze"],
            "data_sources": ["历史价格", "成交量"],
            "skills": ["趋势", "动量", "波动"],
            "notes": "输出技术面评分、信号和风险提示。",
        },
        {
            "agent_id": "fundamental_analyst",
            "agent_name": "基本面分析 Agent",
            "tools": ["FundamentalAnalyst.analyze"],
            "data_sources": ["财务指标", "估值指标"],
            "skills": ["盈利质量", "估值过滤"],
            "notes": "约束纯技术信号，避免高风险基本面标的进入组合。",
        },
        {
            "agent_id": "sentiment_analyst",
            "agent_name": "舆情分析 Agent",
            "tools": ["SentimentAnalyst.analyze"],
            "data_sources": ["样例舆情", "AkShare 新闻", "smart-search"],
            "skills": ["新闻摘要", "市场情绪"],
            "notes": "Phase 2 事件流会持续把新闻和公告输入到该 Agent。",
        },
        {
            "agent_id": "debate_room",
            "agent_name": "多 Agent 讨论室",
            "tools": ["DebateRoom.analyze"],
            "data_sources": ["技术面", "基本面", "舆情面"],
            "skills": ["观点汇总", "冲突识别"],
            "notes": "把多个分析结论合并为可审计的共识。",
        },
        {
            "agent_id": "risk_manager",
            "agent_name": "风控 Agent",
            "tools": ["RiskManager.analyze", "TradingTaskScheduler.run_stop_loss_check"],
            "data_sources": ["当前持仓", "实时/最新价格", "风险配置"],
            "skills": ["止损", "仓位上限", "波动约束"],
            "notes": "任何模型复核结果都必须服从风控约束。",
        },
        {
            "agent_id": "portfolio_manager",
            "agent_name": "组合 Agent",
            "tools": ["PortfolioManager.decide", "VirtualAccount.buy", "VirtualAccount.sell"],
            "data_sources": ["分析报告", "风控结果", "账户快照"],
            "skills": ["买卖动作", "仓位分配", "模拟交易执行"],
            "notes": "每个模型驱动系统拥有独立 VirtualAccount，收益和记忆不互相污染。",
        },
    ]


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
