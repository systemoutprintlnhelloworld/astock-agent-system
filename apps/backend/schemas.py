"""Frontend-facing API and event schemas for the modern desktop UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


SCHEMA_VERSION = "2026-06-03"

AgentStatus = Literal["idle", "running", "completed", "failed", "warning", "skipped"]
DecisionAction = Literal["BUY", "SELL", "HOLD", "REJECT", "FORCE_SELL_EXECUTED", "FORCE_SELL_SIGNAL"]
EventType = Literal[
    "connection_established",
    "pong",
    "run_started",
    "agent_started",
    "agent_step",
    "agent_completed",
    "decision_made",
    "trade_executed",
    "risk_checked",
    "timeline_event",
    "llm_checked",
    "memory_updated",
    "config_updated",
    "run_completed",
    "run_failed",
    "error",
]

EVENT_TYPES: tuple[str, ...] = (
    "connection_established",
    "pong",
    "run_started",
    "agent_started",
    "agent_step",
    "agent_completed",
    "decision_made",
    "trade_executed",
    "risk_checked",
    "timeline_event",
    "llm_checked",
    "memory_updated",
    "config_updated",
    "run_completed",
    "run_failed",
    "error",
)


class ApiEnvelope(BaseModel):
    """Base response metadata shared by product-facing API endpoints."""

    status: str = "ok"
    schema_version: str = SCHEMA_VERSION
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BackendEvent(BaseModel):
    """WebSocket event envelope consumed by the React Flow/log UI."""

    type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: str = ""
    agent_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class FlowPosition(BaseModel):
    """React Flow node position."""

    x: float
    y: float


class AgentFlowNodeData(BaseModel):
    """Display metadata for one Agent node."""

    label: str
    status: AgentStatus = "idle"
    description: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentFlowNode(BaseModel):
    """React Flow compatible node contract."""

    id: str
    position: FlowPosition
    data: AgentFlowNodeData
    type: str = "agentNode"


class AgentFlowEdge(BaseModel):
    """React Flow compatible edge contract."""

    id: str
    source: str
    target: str
    animated: bool = True
    label: str = ""


class AgentFlowResponse(ApiEnvelope):
    """Agent flow graph response."""

    nodes: list[AgentFlowNode] = Field(default_factory=list)
    edges: list[AgentFlowEdge] = Field(default_factory=list)


class DecisionLogStep(BaseModel):
    """Expandable detail row for a decision log card."""

    id: str
    agent_id: str
    title: str
    summary: str = ""
    status: AgentStatus = "completed"
    started_at: str = ""
    finished_at: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class DecisionLogEntry(BaseModel):
    """Human-readable decision card for the transparent log UI."""

    id: str
    run_id: str = ""
    timestamp: str = ""
    agent_id: str = ""
    llm_model: str = ""
    stock_code: str = ""
    stock_name: str = ""
    action: str = "HOLD"
    confidence: float = 0.0
    position_size: float = 0.0
    summary: str = ""
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    steps: list[DecisionLogStep] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class DecisionLogResponse(ApiEnvelope):
    """Decision log list response."""

    items: list[DecisionLogEntry] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class StockCandidate(BaseModel):
    """Candidate stock row for the stock board."""

    stock_code: str
    stock_name: str
    sector: str = ""
    score: float = 0.0
    action: str = "HOLD"
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class HoldingRow(BaseModel):
    """Current paper holding row."""

    agent_id: str = ""
    llm_model: str = ""
    stock_code: str
    stock_name: str = ""
    shares: int = 0
    cost_basis: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_return: float = 0.0


class TradeRow(BaseModel):
    """Paper trade row."""

    agent_id: str = ""
    llm_model: str = ""
    date: str = ""
    stock_code: str
    stock_name: str = ""
    side: str = ""
    price: float = 0.0
    shares: int = 0
    amount: float = 0.0
    realized_pnl: float = 0.0
    reason: str = ""


class StockBoardResponse(ApiEnvelope):
    """Stock board response used by the holdings/candidates UI."""

    holdings: list[HoldingRow] = Field(default_factory=list)
    candidates: list[StockCandidate] = Field(default_factory=list)
    trades: list[TradeRow] = Field(default_factory=list)


class EquityMetricPoint(BaseModel):
    """One point in the long-term equity/performance chart."""

    date: str
    agent_id: str = ""
    llm_model: str = ""
    equity: float = 0.0
    cash: float = 0.0
    daily_pnl: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0


class EquityMetricsResponse(ApiEnvelope):
    """Equity curve response."""

    series: list[EquityMetricPoint] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class RankingRow(BaseModel):
    """Model leaderboard row."""

    rank: int
    agent_id: str
    llm_model: str
    total_return: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    equity: float = 0.0
    cash: float = 0.0
    daily_pnl: float = 0.0
    skipped_execution: bool = False
    skip_reason: str = ""


class RankingsResponse(ApiEnvelope):
    """LLM/rule account leaderboard response."""

    rankings: list[RankingRow] = Field(default_factory=list)


class RunStatusResponse(ApiEnvelope):
    """Current run status response."""

    status: str = "idle"
    run: dict[str, Any] | None = None


class EventTimelineItem(BaseModel):
    """One user-facing market/system event shown on the event timeline."""

    id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "system"
    category: str = "system"
    severity: Literal["info", "warning", "critical"] = "info"
    title: str
    summary: str = ""
    stock_code: str = ""
    url: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class EventTimelineResponse(ApiEnvelope):
    """Event timeline response for the modern UI."""

    items: list[EventTimelineItem] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class AgentMemoryCase(BaseModel):
    """Readable memory case for one model-driven Agent system."""

    id: str
    agent_id: str = ""
    llm_model: str = ""
    stock_code: str = ""
    stock_name: str = ""
    decision_date: str = ""
    action: str = "HOLD"
    reason: str = ""
    outcome: str = "unknown"
    pnl_pct: float = 0.0
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class AgentMemoryResponse(ApiEnvelope):
    """Readonly memory cases for a model-driven Agent system."""

    agent_id: str = ""
    items: list[AgentMemoryCase] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class AgentToolDefinition(BaseModel):
    """Tool/skill capability assigned to one Agent role."""

    agent_id: str
    agent_name: str
    tools: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    notes: str = ""


class AgentToolsResponse(ApiEnvelope):
    """Agent tool and skill catalog."""

    items: list[AgentToolDefinition] = Field(default_factory=list)


class LlmConfigCheckResponse(ApiEnvelope):
    """LLM configuration validation and model discovery result."""

    configured: bool = False
    base_url: str = ""
    default_model: str = ""
    request_profile: str = ""
    models: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    bench: dict[str, Any] | None = None
