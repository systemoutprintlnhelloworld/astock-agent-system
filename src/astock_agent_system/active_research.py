"""Global active A-share research and paper-trading tools.

This module implements the first independently usable global-active workflow.
It is intentionally local-first: the research entry point reads the SQLite
market warehouse, ranks sectors before stocks, and only uses online providers
when a caller explicitly asks for realtime refresh in a later phase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from astock_agent_system.backtest.virtual_account import VirtualAccount
from astock_agent_system.config import Settings, load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.data.local_store import DEFAULT_LOCAL_MARKET_DB, LocalMarketStore
from astock_agent_system.events import AgentEventEmitter


@dataclass(slots=True)
class ActiveResearchOptions:
    """Options shared by global active research and execution."""

    profile: str = "ultra-short"
    db_path: str | Path | None = None
    max_sectors: int = 5
    max_candidates: int = 60
    candidate_per_sector: int = 10
    max_buys: int = 5
    history_days: int = 20
    min_amount: float | None = None
    as_of_date: str = ""
    include_stale: bool = False
    refresh_realtime: bool = False


class LocalMarketWarehouseTool:
    """Read-only access to the local SQLite market warehouse."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.store = LocalMarketStore(path=path or DEFAULT_LOCAL_MARKET_DB)

    def coverage(self, *, stock_limit: int = 20, date_limit: int = 40) -> dict[str, Any]:
        return self.store.coverage_summary(stock_limit=stock_limit, date_limit=date_limit)

    def scan(self, options: ActiveResearchOptions) -> dict[str, Any]:
        return self.store.scan_candidates(
            limit=max(1, int(options.max_candidates or 60)),
            as_of_date=options.as_of_date or None,
            min_amount=options.min_amount,
            history_days=max(2, int(options.history_days or 20)),
            top_per_sector=max(1, int(options.candidate_per_sector or 10)),
            include_stale=bool(options.include_stale),
        )


class SectorHeatTool:
    """Rank sectors before individual stocks."""

    def rank(self, candidates: list[dict[str, Any]], *, max_sectors: int = 5) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in candidates:
            sector = str(item.get("sector") or "未分组")
            grouped.setdefault(sector, []).append(item)

        rows: list[dict[str, Any]] = []
        for sector, items in grouped.items():
            amount = sum(_to_float(item.get("amount")) for item in items)
            avg_score = _avg(_to_float(item.get("score")) for item in items)
            avg_change = _avg(_to_float(item.get("change_pct")) for item in items)
            avg_return_5d = _avg(_to_float(item.get("return_5d")) for item in items)
            avg_amount_ratio = _avg(_to_float(item.get("amount_ratio_20d")) for item in items)
            breadth = sum(1 for item in items if _to_float(item.get("change_pct")) > 0) / max(1, len(items))
            heat_score = (
                avg_score * 0.35
                + _clamp(avg_change * 8.0 + 0.5) * 0.20
                + _clamp(avg_return_5d * 4.0 + 0.5) * 0.15
                + _clamp((avg_amount_ratio - 0.8) / 1.4) * 0.15
                + breadth * 0.15
            )
            rows.append(
                {
                    "sector": sector,
                    "score": round(heat_score, 6),
                    "candidate_count": len(items),
                    "breadth": round(breadth, 6),
                    "amount": round(amount, 4),
                    "avg_change_pct": round(avg_change, 6),
                    "avg_return_5d": round(avg_return_5d, 6),
                    "avg_amount_ratio_20d": round(avg_amount_ratio, 6),
                    "signals": _sector_signals(avg_change, avg_return_5d, avg_amount_ratio, breadth),
                }
            )
        return sorted(rows, key=lambda item: (item["score"], item["amount"]), reverse=True)[: max(1, int(max_sectors or 5))]


class CandidateBatchTool:
    """Build sector-scoped candidate groups for active research."""

    def group(
        self,
        candidates: list[dict[str, Any]],
        sector_heat: list[dict[str, Any]],
        *,
        per_sector: int = 10,
    ) -> list[dict[str, Any]]:
        selected = {str(item.get("sector") or "") for item in sector_heat}
        groups: list[dict[str, Any]] = []
        for sector in selected:
            items = [item for item in candidates if str(item.get("sector") or "未分组") == sector]
            ranked = sorted(items, key=lambda item: (_to_float(item.get("score")), _to_float(item.get("amount"))), reverse=True)
            groups.append(
                {
                    "sector": sector,
                    "count": len(ranked[:per_sector]),
                    "candidates": [_with_ultra_short_tags(item) for item in ranked[:per_sector]],
                }
            )
        heat_order = {str(item.get("sector") or ""): idx for idx, item in enumerate(sector_heat)}
        return sorted(groups, key=lambda item: heat_order.get(str(item.get("sector") or ""), 999))


class RealtimeQuoteTool:
    """Optional realtime/quote refresh for selected candidates."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_agent = DataAgent(settings=self.settings)

    def refresh(self, candidates: list[dict[str, Any]], *, enabled: bool = False) -> list[dict[str, Any]]:
        if not enabled:
            return [{**item, "realtime_status": "skipped", "realtime_reason": "refresh_realtime=false"} for item in candidates]
        refreshed: list[dict[str, Any]] = []
        for item in candidates:
            stock_code = str(item.get("stock_code") or "")
            if not stock_code:
                refreshed.append({**item, "realtime_status": "skipped", "realtime_reason": "missing stock_code"})
                continue
            try:
                quote = self.data_agent.get_quote(stock_code)
                refreshed.append(
                    {
                        **item,
                        "price": round(float(quote.price), 4),
                        "change_pct": round(float(quote.change_pct), 6),
                        "amount": round(float(quote.amount), 4),
                        "realtime_status": "ok",
                        "realtime_date": quote.date,
                    }
                )
            except Exception as exc:  # pragma: no cover - provider/network guard
                refreshed.append({**item, "realtime_status": "error", "realtime_reason": str(exc)[:180]})
        return refreshed


class IntradaySignalTool:
    """Ultra-short signal scoring with local quote/K-line fallbacks."""

    def evaluate(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in candidates:
            change = _to_float(item.get("change_pct"))
            amount_ratio = _to_float(item.get("amount_ratio_20d"))
            volume_ratio = _to_float(item.get("volume_ratio_20d"))
            ret5 = _to_float(item.get("return_5d"))
            score = _clamp(_to_float(item.get("score")) * 0.45 + _clamp(change * 8 + 0.5) * 0.25 + _clamp((max(amount_ratio, volume_ratio) - 0.8) / 1.5) * 0.2 + _clamp(ret5 * 4 + 0.5) * 0.1)
            if change >= 0.095:
                timing = "skip_overheated"
            elif score >= 0.68 and amount_ratio >= 1.0:
                timing = "buy_now"
            elif score >= 0.58:
                timing = "watch_breakout"
            elif change < -0.03:
                timing = "skip_weak"
            else:
                timing = "wait_pullback"
            rows.append(
                {
                    "stock_code": item.get("stock_code", ""),
                    "stock_name": item.get("stock_name", ""),
                    "sector": item.get("sector", ""),
                    "timing": timing,
                    "timing_score": round(score, 6),
                    "reference_price": item.get("price", 0.0),
                    "invalid_price": round(_to_float(item.get("price")) * 0.97, 4),
                    "reason": _timing_reason(timing),
                }
            )
        return sorted(rows, key=lambda item: item["timing_score"], reverse=True)


class PortfolioBatchDecisionTool:
    """Convert ranked candidates into a portfolio-level paper action plan."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def decide(
        self,
        candidates: list[dict[str, Any]],
        timing: list[dict[str, Any]],
        *,
        max_buys: int = 5,
    ) -> list[dict[str, Any]]:
        timing_by_code = {str(item.get("stock_code") or ""): item for item in timing}
        allowed_timing = {"buy_now", "watch_breakout"}
        picks: list[dict[str, Any]] = []
        for item in candidates:
            code = str(item.get("stock_code") or "")
            signal = timing_by_code.get(code, {})
            if signal.get("timing") not in allowed_timing:
                continue
            picks.append({**item, "timing": signal})
            if len(picks) >= max(1, int(max_buys or 5)):
                break
        per_stock = min(float(self.settings.risk.max_position_per_stock), float(self.settings.risk.max_total_position) / max(1, len(picks) or 1))
        return [
            {
                "stock_code": item.get("stock_code", ""),
                "stock_name": item.get("stock_name", ""),
                "sector": item.get("sector", ""),
                "action": "BUY",
                "position_size": round(per_stock, 6),
                "confidence": round(_clamp(_to_float(item.get("score")) * 0.65 + _to_float(item.get("timing", {}).get("timing_score")) * 0.35), 6),
                "price": item.get("price", 0.0),
                "reason": "全局主动模式：板块热度、量价强度和超短线择时通过",
                "timing": item.get("timing", {}),
            }
            for item in picks
        ]


class T1TradingRuleTool:
    """A-share T+1 and paper-account action guard."""

    def check(self, actions: list[dict[str, Any]], account: VirtualAccount, *, trade_date: str) -> dict[str, Any]:
        approved: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for action in actions:
            stock_code = str(action.get("stock_code") or "")
            verb = str(action.get("action") or "").upper()
            position = account.positions.get(stock_code)
            if verb == "SELL" and position and position.last_buy_date == trade_date:
                blocked.append({**action, "blocked_reason": "T+1: 当日买入的新仓不能当日卖出"})
            elif verb == "SELL" and not position:
                blocked.append({**action, "blocked_reason": "账户无可卖持仓"})
            elif verb in {"BUY", "SELL", "HOLD"}:
                approved.append({**action, "t1_status": "approved"})
            else:
                blocked.append({**action, "blocked_reason": f"未知动作: {verb}"})
        return {
            "approved_actions": approved,
            "blocked_actions": blocked,
            "policy": "A股现货 T+1：当天新买股票不能当天卖出；已有持仓可卖。",
        }


class CatalystSearchTool:
    """Catalyst-search planning surface for smart-search/iWencai integration."""

    def plan(self, sector_heat: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "sector": item.get("sector", ""),
                "status": "planned",
                "queries": [
                    f"{item.get('sector', '')} 今日 A股 产业 新闻 催化",
                    f"{item.get('sector', '')} 公告 订单 政策",
                ],
                "tools": ["smart-search", "iwencai-skillhub"],
            }
            for item in sector_heat
        ]


def build_active_research_payload(
    *,
    settings: Settings | None = None,
    options: ActiveResearchOptions | None = None,
    event_emitter: AgentEventEmitter | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    settings = settings or load_settings()
    options = options or ActiveResearchOptions()
    emitter = event_emitter or AgentEventEmitter()
    run_id = run_id or str(uuid.uuid4())[:8]
    warehouse = LocalMarketWarehouseTool(options.db_path)
    emitter.emit("global_market_regime_evaluated", run_id=run_id, stage="global-active", message="读取本地市场库并评估全局主动研究输入")
    scan = warehouse.scan(options)
    candidates = [item for item in scan.get("candidates", []) if isinstance(item, dict)]
    sector_heat = SectorHeatTool().rank(candidates, max_sectors=options.max_sectors)
    emitter.emit("sector_rotation_ranked", run_id=run_id, stage="global-active", message=f"完成 {len(sector_heat)} 个热点板块排序", sector_heat=sector_heat)
    sector_groups = CandidateBatchTool().group(candidates, sector_heat, per_sector=max(1, int(options.candidate_per_sector or 10)))
    emitter.emit(
        "candidate_batch_generated",
        run_id=run_id,
        stage="global-active",
        message=f"生成 {sum(int(group.get('count', 0) or 0) for group in sector_groups if isinstance(group, dict))} 个板块候选",
        sector_candidates=sector_groups,
    )
    flattened = [candidate for group in sector_groups for candidate in group.get("candidates", []) if isinstance(candidate, dict)]
    refreshed = RealtimeQuoteTool(settings).refresh(flattened, enabled=options.refresh_realtime)
    timing = IntradaySignalTool().evaluate(refreshed)
    emitter.emit("intraday_signal_evaluated", run_id=run_id, stage="global-active", message=f"完成 {len(timing)} 个候选的超短线择时评估", timing=timing[:20])
    actions = PortfolioBatchDecisionTool(settings).decide(refreshed, timing, max_buys=options.max_buys)
    t1_check = T1TradingRuleTool().check(actions, VirtualAccount(settings=settings), trade_date=datetime.now().strftime("%Y-%m-%d"))
    catalysts = CatalystSearchTool().plan(sector_heat)
    emitter.emit("sector_catalyst_collected", run_id=run_id, stage="global-active", message=f"生成 {len(catalysts)} 条板块催化剂查询计划", catalyst_plan=catalysts)
    emitter.emit("portfolio_batch_decided", run_id=run_id, stage="global-active", message=f"生成 {len(actions)} 条组合级候选动作", actions=actions)
    emitter.emit("t1_rule_checked", run_id=run_id, stage="global-active", message="完成 A股 T+1 合规检查", t1_check=t1_check)
    payload = {
        "status": "ok" if candidates else scan.get("status", "empty"),
        "mode": "global_active_research",
        "profile": options.profile,
        "run_id": run_id,
        "source": "local_sqlite",
        "db_path": str(warehouse.store.path),
        "t1_policy": "A股现货 T+1：当天新买股票不能当天卖出；已有持仓可卖。",
        "scan": scan,
        "coverage": scan.get("coverage", {}),
        "sector_heat": sector_heat,
        "sector_candidates": sector_groups,
        "catalyst_plan": catalysts,
        "timing": timing,
        "portfolio_plan": {"actions": actions, **t1_check},
        "next_steps": [
            "这是全局主动研究层，不是真实下单；如需模拟执行请运行 agent global-active。",
            "对 catalyst_plan 中的板块查询运行 smart-search 或 iwencai-search，补齐新闻/公告催化。",
            "需要更接近盘中高频时，启用 --refresh-realtime 并确保 provider chain 可返回最新 quote。",
        ],
    }
    emitter.emit("global_active_run_completed", run_id=run_id, stage="global-active", message="全局主动研究完成", payload=payload)
    return payload


class GlobalActiveOrchestrator:
    """First portfolio-level global active paper-trading orchestrator."""

    def __init__(self, settings: Settings | None = None, event_emitter: AgentEventEmitter | None = None) -> None:
        self.settings = settings or load_settings()
        self.event_emitter = event_emitter or AgentEventEmitter()

    def run(self, *, options: ActiveResearchOptions | None = None, initial_capital: float | None = None) -> dict[str, Any]:
        run_id = str(uuid.uuid4())[:8]
        trade_date = datetime.now().strftime("%Y-%m-%d")
        self.event_emitter.emit("run_start", run_id=run_id, stage="global-active", message="启动全局主动超短线模拟盘轮次")
        research = build_active_research_payload(settings=self.settings, options=options, event_emitter=self.event_emitter, run_id=run_id)
        account = VirtualAccount(settings=self.settings, initial_capital=initial_capital)
        latest_prices: dict[str, float] = {}
        executed: list[dict[str, Any]] = []
        for action in research.get("portfolio_plan", {}).get("approved_actions", []):
            if not isinstance(action, dict) or action.get("action") != "BUY":
                continue
            price = _to_float(action.get("price"))
            if price <= 0:
                continue
            target_value = account.equity(latest_prices) * _to_float(action.get("position_size"))
            if account.buy(str(action.get("stock_code")), price, target_value, trade_date, reason="global_active_buy"):
                latest_prices[str(action.get("stock_code"))] = price
                trade = account.trades[-1].to_dict()
                executed.append(trade)
                self.event_emitter.emit("trade_executed", run_id=run_id, stage="global-active", message=f"全局主动模拟买入 {trade.get('stock_code')}", trade=trade)
        account.mark_to_market(trade_date, latest_prices)
        account_payload = account.to_dict(latest_prices)
        equity = _to_float(account_payload.get("equity"))
        total_return = (equity - account.initial_capital) / account.initial_capital if account.initial_capital else 0.0
        payload = {
            "status": "ok",
            "mode": "global_active",
            "run_id": run_id,
            "run_date": trade_date,
            "account_mode": "fresh_start",
            "fresh_start": True,
            "continue_from_storage": False,
            "model_count": 1,
            "research": research,
            "rankings": [{"rank": 1, "model": "global-active-rule", "return": round(total_return, 6), "cash": round(_to_float(account_payload.get("cash")), 4), "equity": round(equity, 4)}],
            "agents": [
                {
                    "agent_id": "agent-global-active-rule",
                    "llm_model": "global-active-rule",
                    "initial_capital": round(account.initial_capital, 4),
                    "equity": round(equity, 4),
                    "cash": round(_to_float(account_payload.get("cash")), 4),
                    "total_return": round(total_return, 6),
                    "daily_pnl": round(equity - account.initial_capital, 4),
                    "buy_count": sum(1 for trade in executed if trade.get("side") == "BUY"),
                    "sell_count": sum(1 for trade in executed if trade.get("side") == "SELL"),
                    "total_trades": len(executed),
                    "decisions": research.get("portfolio_plan", {}).get("actions", []),
                    "positions": _positions_as_rows(account_payload.get("positions", {}), latest_prices),
                    "trades": executed,
                }
            ],
            "t1_policy": research.get("t1_policy", ""),
        }
        self.event_emitter.emit("run_complete", run_id=run_id, stage="global-active", message=f"全局主动轮次完成，成交 {len(executed)} 笔", rankings=payload["rankings"])
        return payload


def _positions_as_rows(positions: Any, prices: dict[str, float]) -> list[dict[str, Any]]:
    if not isinstance(positions, dict):
        return []
    rows = []
    for code, item in positions.items():
        if isinstance(item, dict):
            rows.append({"stock_code": code, "current_price": prices.get(code, item.get("cost_basis", 0.0)), **item})
    return rows


def _with_ultra_short_tags(item: dict[str, Any]) -> dict[str, Any]:
    tags: list[str] = []
    if _to_float(item.get("amount_ratio_20d")) >= 1.2 or _to_float(item.get("volume_ratio_20d")) >= 1.2:
        tags.append("放量")
    if _to_float(item.get("return_5d")) > 0.02:
        tags.append("短期趋势")
    if _to_float(item.get("change_pct")) >= 0.07:
        tags.append("过热谨慎")
    if _to_float(item.get("amount")) < 100_000_000:
        tags.append("流动性偏低")
    if not tags:
        tags.append("待确认")
    return {**item, "ultra_short_tags": tags}


def _sector_signals(avg_change: float, avg_return_5d: float, avg_amount_ratio: float, breadth: float) -> list[str]:
    signals: list[str] = []
    if breadth >= 0.65:
        signals.append("板块扩散")
    if avg_amount_ratio >= 1.2:
        signals.append("量能放大")
    if avg_return_5d > 0.02:
        signals.append("短期趋势")
    if avg_change > 0.03:
        signals.append("当日强势")
    return signals or ["观察"]


def _timing_reason(timing: str) -> str:
    return {
        "buy_now": "量价与板块热度共振，允许小仓试错",
        "watch_breakout": "接近触发条件，等待突破确认",
        "wait_pullback": "信号未完全共振，等待回踩或量能确认",
        "skip_overheated": "涨幅过热，避免追高",
        "skip_weak": "短线走弱，跳过",
    }.get(timing, "等待更多证据")


def _avg(values: Any) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))
