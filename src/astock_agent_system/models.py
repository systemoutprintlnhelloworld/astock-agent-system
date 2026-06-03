"""Core data models for the A-share agent workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Action = Literal["BUY", "SELL", "HOLD", "REJECT"]


@dataclass(slots=True)
class StockIdentity:
    stock_code: str
    stock_name: str
    sector: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StockQuote:
    stock_code: str
    stock_name: str
    date: str
    price: float
    change_pct: float
    volume: float
    amount: float
    sector: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StockBar:
    stock_code: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    turnover: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FinancialSnapshot:
    stock_code: str
    stock_name: str
    report_date: str
    pe_ttm: float
    pb: float
    roe: float
    debt_ratio: float
    revenue_growth: float
    profit_growth: float
    market_cap: float
    sector: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnalysisResult:
    agent_name: str
    stock_code: str
    score: float
    label: str
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskProfile:
    max_position_per_stock: float = 0.10
    max_total_position: float = 0.50
    stop_loss_pct: float = 0.05
    max_volatility: float = 0.35
    min_turnover: float = 100000000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PortfolioConfig:
    initial_capital: float = 100000.0
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage_rate: float = 0.001

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TradeDecision:
    stock_code: str
    action: Action
    confidence: float
    position_size: float
    target_price: float | None = None
    stop_loss: float | None = None
    time_horizon: str = "1个月"
    reasons: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StockAnalysisReport:
    stock: StockIdentity
    quote: StockQuote
    financial: FinancialSnapshot
    technical: AnalysisResult | None = None
    fundamental: AnalysisResult | None = None
    sentiment: AnalysisResult | None = None
    debate: AnalysisResult | None = None
    risk: AnalysisResult | None = None
    decision: TradeDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(slots=True)
class DailyRunReport:
    run_date: str
    candidates: list[StockIdentity]
    reports: list[StockAnalysisReport]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
