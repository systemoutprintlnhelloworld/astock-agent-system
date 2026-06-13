"""Multi-LLM paper-trading competition orchestrator.

Each LLM model owns an independent virtual account. The orchestrator runs the
same market observation workflow for every model and records a leaderboard.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from astock_agent_system.agent_descriptor import load_agent_descriptor
from astock_agent_system.agent_learning import load_experiences, record_competition_experience, trigger_learning_if_ready
from astock_agent_system.agents import MasterAgent
from astock_agent_system.backtest.virtual_account import VirtualAccount
from astock_agent_system.config import Settings, load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.events import AgentEventEmitter
from astock_agent_system.llm import LLMClient
from astock_agent_system.models import StockAnalysisReport


logger = logging.getLogger(__name__)


def _compact_persist_error(exc: Exception) -> dict[str, str]:
    text = str(exc)
    lower = text.lower()
    if "mongo" in lower or "serverselectiontimeout" in lower or "connection refused" in lower or "winerror 10061" in lower:
        return {
            "code": "E-MONGO-CONNECT",
            "reason": "MongoDB 未连接或不可达；本轮交易已完成，仅跳过排行榜/成交持久化。调试时可用 --no-persist。",
        }
    return {"code": "E-PERSIST", "reason": text[:180] or "持久化失败"}


@dataclass(slots=True)
class AgentCompetitionResult:
    """Result for one LLM model's independent paper account."""

    agent_id: str
    llm_model: str
    initial_capital: float
    equity: float
    cash: float
    total_return: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    buy_count: int
    sell_count: int
    daily_pnl: float = 0.0
    restored_from_snapshot: bool = False
    previous_snapshot_date: str = ""
    previous_equity: float = 0.0
    skipped_execution: bool = False
    skip_reason: str = ""
    decisions: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MultiAgentOrchestrator:
    """Run multiple LLM models as independent paper-trading agents."""

    def __init__(
        self,
        settings: Settings | None = None,
        data_agent: DataAgent | None = None,
        event_emitter: AgentEventEmitter | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.data_agent = data_agent or DataAgent(settings=self.settings)
        self.event_emitter = event_emitter or AgentEventEmitter()
        self._last_snapshot_restore: dict[str, Any] = {
            "status": "not_requested",
            "requested": False,
            "loaded_count": 0,
            "requested_agent_ids": [],
            "missing_agent_ids": [],
        }

    def run_competition(
        self,
        models: list[str] | None = None,
        max_count: int = 3,
        history_days: int = 24,
        initial_capital: float | None = None,
        trade_date: str | None = None,
        persist: bool = True,
        continue_from_storage: bool = True,
        collect_learning: bool | None = None,
    ) -> dict[str, Any]:
        """Run one simulated trading round for each model.

        This is intentionally dependency-light: it uses the existing
        ``MasterAgent`` and ``VirtualAccount`` so the competition works before
        VeighNa is installed. The order execution adapter can later be swapped
        to VeighNa while preserving this public result shape.
        """
        selected_models = _normalize_models(models, self.settings.llm.default_model)
        run_date = trade_date or datetime.now().strftime("%Y-%m-%d")
        run_id = str(uuid.uuid4())[:8]
        self.event_emitter.emit(
            "run_start",
            run_id=run_id,
            stage="competition",
            message=f"开始运行 {len(selected_models)} 个模型的自动投资轮次",
            models=selected_models,
            max_count=max_count,
            history_days=history_days,
            trade_date=run_date,
            persist=persist,
            continue_from_storage=continue_from_storage,
            account_mode="continue_from_storage" if continue_from_storage else "fresh_start",
        )
        if continue_from_storage:
            snapshot_by_agent = self._load_account_snapshots(selected_models)
            snapshot_restore = self._snapshot_restore_summary(selected_models, snapshot_by_agent)
        else:
            snapshot_by_agent = {}
            requested_agent_ids = [_agent_id_for_model(model) for model in selected_models]
            self._last_snapshot_restore = {
                "status": "fresh_start",
                "requested": False,
                "loaded_count": 0,
                "requested_agent_ids": requested_agent_ids,
                "missing_agent_ids": requested_agent_ids,
                "reason": "continue_from_storage=false",
            }
            snapshot_restore = dict(self._last_snapshot_restore)
        results: list[AgentCompetitionResult] = []

        for idx, model in enumerate(selected_models, 1):
            agent_id = _agent_id_for_model(model)
            
            self.event_emitter.emit(
                "agent_start",
                run_id=run_id,
                agent_id=agent_id,
                model=model,
                message=f"启动智能体 {model} [{idx}/{len(selected_models)}]",
                progress={"current": idx, "total": len(selected_models)},
            )
            
            model_settings = copy.deepcopy(self.settings)
            if model != "rule-baseline":
                model_settings.llm.default_model = model
            result = self._run_one_agent(
                agent_id=agent_id,
                llm_model=model,
                settings=model_settings,
                max_count=max_count,
                history_days=history_days,
                initial_capital=initial_capital,
                trade_date=run_date,
                previous_snapshot=snapshot_by_agent.get(agent_id),
                run_id=run_id,
            )
            results.append(result)
            
            self.event_emitter.emit(
                "agent_complete",
                run_id=run_id,
                agent_id=agent_id,
                model=model,
                message=f"智能体 {model} 运行完成",
                equity=result.equity,
                total_return=result.total_return,
                trades=result.total_trades,
            )

        rankings = sorted(results, key=lambda item: item.total_return, reverse=True)
        restored_account_count = sum(1 for item in results if item.restored_from_snapshot)
        skipped_agent_count = sum(1 for item in results if item.skipped_execution)
        snapshot_restore.update(
            {
                "restored_account_count": restored_account_count,
                "skipped_agent_count": skipped_agent_count,
                "skipped_agent_ids": [item.agent_id for item in results if item.skipped_execution],
            }
        )
        payload = {
            "status": "ok",
            "run_id": run_id,
            "run_date": run_date,
            "account_mode": "continue_from_storage" if continue_from_storage else "fresh_start",
            "continue_from_storage": bool(continue_from_storage),
            "fresh_start": not bool(continue_from_storage),
            "snapshot_restore": snapshot_restore,
            "restored_account_count": restored_account_count,
            "skipped_agent_count": skipped_agent_count,
            "model_count": len(results),
            "rankings": [_ranking_row(item, rank + 1) for rank, item in enumerate(rankings)],
            "agents": [item.to_dict() for item in results],
        }
        if persist:
            payload["persisted"] = self._persist_competition(payload)
        should_collect_learning = persist if collect_learning is None else collect_learning
        if should_collect_learning:
            self.event_emitter.emit(
                "learning_analysis_triggered",
                run_id=run_id,
                stage="learning",
                message="记录本轮决策经验并按阈值检查学习建议",
            )
            payload["learning"] = self._record_learning_safely(payload)
            learning_payload = payload["learning"] if isinstance(payload.get("learning"), dict) else {}
            record_result = learning_payload.get("record_result", {}) if isinstance(learning_payload.get("record_result"), dict) else {}
            status = learning_payload.get("status", learning_payload) if isinstance(learning_payload, dict) else {}
            suggestions = status.get("suggestions", []) if isinstance(status, dict) else []
            self.event_emitter.emit(
                "learning_experience_recorded",
                run_id=run_id,
                stage="learning",
                message=f"本轮记录经验 {record_result.get('recorded', 0)} 条",
                learning=learning_payload,
            )
            if suggestions:
                self.event_emitter.emit(
                    "learning_suggestion_generated",
                    run_id=run_id,
                    stage="learning",
                    message=f"生成 {len(suggestions)} 条学习建议，等待人工审查",
                    suggestions=suggestions,
                )
        self.event_emitter.emit(
            "run_complete",
            run_id=run_id,
            stage="competition",
            message=f"运行完成，共 {len(results)} 个模型",
            rankings=[{"rank": rank + 1, "model": item.llm_model, "return": item.total_return} for rank, item in enumerate(rankings)],
        )
        return payload

    def _run_one_agent(
        self,
        agent_id: str,
        llm_model: str,
        settings: Settings,
        max_count: int,
        history_days: int,
        initial_capital: float | None,
        trade_date: str,
        previous_snapshot: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> AgentCompetitionResult:
        account = (
            VirtualAccount.from_snapshot(previous_snapshot, settings=settings, initial_capital=initial_capital)
            if previous_snapshot
            else VirtualAccount(settings=settings, initial_capital=initial_capital)
        )
        previous_equity = _to_float(previous_snapshot.get("equity"), account.initial_capital) if previous_snapshot else account.initial_capital

        if _is_same_trade_date_snapshot(previous_snapshot, trade_date):
            return _result_from_existing_snapshot(
                agent_id=agent_id,
                llm_model=llm_model,
                account=account,
                previous_snapshot=previous_snapshot or {},
                trade_date=trade_date,
                previous_equity=previous_equity,
            )

        report = MasterAgent(
            settings=settings,
            data_agent=self.data_agent,
            event_emitter=self.event_emitter,
            run_id=run_id,
            agent_id=agent_id,
            model=llm_model,
        ).run_daily(max_count=max_count, history_days=history_days)

        latest_prices: dict[str, float] = {}
        decisions: list[dict[str, Any]] = []
        for stock_report in report.reports:
            quote = stock_report.quote
            decision = stock_report.decision
            latest_prices[quote.stock_code] = quote.price
            if decision is None:
                continue
            override = self._llm_review_decision(stock_report, llm_model, settings)
            effective = _effective_decision(stock_report, override, settings)
            decision_row = _decision_row(stock_report, agent_id, llm_model, effective, override)
            decisions.append(decision_row)
            self.event_emitter.emit(
                "decision_made",
                run_id=run_id,
                agent_id=agent_id,
                model=llm_model,
                stage="decision",
                message=f"{llm_model} 对 {quote.stock_code} 给出 {effective['action']} 决策",
                decision=decision_row,
            )
            if effective["action"] == "BUY" and effective["position_size"] > 0:
                target_value = account.equity(latest_prices) * effective["position_size"]
                account.buy(quote.stock_code, quote.price, target_value, trade_date, reason="agent_buy")
                self.event_emitter.emit(
                    "trade_executed",
                    run_id=run_id,
                    agent_id=agent_id,
                    model=llm_model,
                    stage="trade",
                    message=f"模拟买入 {quote.stock_code}",
                    stock_code=quote.stock_code,
                    stock_name=quote.stock_name,
                    side="BUY",
                    price=quote.price,
                    position_size=effective["position_size"],
                )
            elif effective["action"] == "SELL":
                account.sell(quote.stock_code, quote.price, None, trade_date, reason="agent_sell")
                self.event_emitter.emit(
                    "trade_executed",
                    run_id=run_id,
                    agent_id=agent_id,
                    model=llm_model,
                    stage="trade",
                    message=f"模拟卖出 {quote.stock_code}",
                    stock_code=quote.stock_code,
                    stock_name=quote.stock_name,
                    side="SELL",
                    price=quote.price,
                    position_size=effective["position_size"],
                )

        self._apply_forced_stop_loss(account, latest_prices, trade_date)
        account.mark_to_market(trade_date, latest_prices)

        account_payload = account.to_dict(latest_prices)
        equity = float(account_payload["equity"])
        total_return = (equity - account.initial_capital) / account.initial_capital if account.initial_capital else 0.0
        daily_pnl = equity - previous_equity
        trades = account_payload["trades"]
        return AgentCompetitionResult(
            agent_id=agent_id,
            llm_model=llm_model,
            initial_capital=round(account.initial_capital, 4),
            equity=round(equity, 4),
            cash=round(float(account_payload["cash"]), 4),
            total_return=round(total_return, 6),
            max_drawdown=round(_max_drawdown(account.equity_curve), 6),
            win_rate=round(_win_rate(trades), 6),
            total_trades=len(trades),
            buy_count=sum(1 for trade in trades if trade.get("side") == "BUY"),
            sell_count=sum(1 for trade in trades if trade.get("side") == "SELL"),
            daily_pnl=round(daily_pnl, 4),
            restored_from_snapshot=bool(previous_snapshot),
            previous_snapshot_date=str(previous_snapshot.get("date", "")) if previous_snapshot else "",
            previous_equity=round(previous_equity, 4),
            decisions=decisions,
            positions=_positions_as_rows(account_payload.get("positions", {}), latest_prices),
            trades=trades,
        )

    def _apply_forced_stop_loss(self, account: VirtualAccount, latest_prices: dict[str, float], trade_date: str) -> None:
        for stock_code, position in list(account.positions.items()):
            price = latest_prices.get(stock_code, position.cost_basis)
            if price <= position.cost_basis * (1.0 - self.settings.risk.stop_loss_pct):
                account.sell(stock_code, price, None, trade_date, reason="forced_stop_loss")

    def _llm_review_decision(
        self,
        report: StockAnalysisReport,
        llm_model: str,
        settings: Settings,
    ) -> dict[str, Any]:
        """Ask one LLM model to review the rule-based decision.

        This is intentionally optional. If the key/model is missing or the
        gateway rate-limits/fails, the model account falls back to the rule
        decision so the competition can still run unattended.
        """
        if getattr(settings.data, "mode", "").lower() == "offline":
            return {"source": "rule_fallback", "reason": "offline_mode"}
        if llm_model == "rule-baseline" or not settings.llm.api_key or not settings.llm.base_url:
            return {"source": "rule_fallback", "reason": "llm_not_configured"}

        client = LLMClient(settings)
        if not client.is_configured:
            return {"source": "rule_fallback", "reason": "llm_not_configured"}

        payload = _compact_report_for_llm(report)
        system_prompt = "你是严格遵守风控的A股模拟盘基金经理，只输出JSON。"
        prompt = (
            "你正在管理一个独立的A股模拟盘账户。请复核规则Agent的报告，"
            "在不违反风控的前提下给出你的最终动作。只能输出JSON："
            "{\"action\":\"BUY/HOLD/SELL/REJECT\",\"confidence\":0到1,"
            "\"position_size\":0到0.2,\"reason\":\"一句话理由\"}。"
            "如果风险经理已拒绝，必须输出REJECT。报告如下：\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        try:
            descriptor = load_agent_descriptor("master_agent")
            if descriptor.prompt_template:
                system_prompt = descriptor.system_prompt or system_prompt
                prompt = descriptor.render_prompt(
                    {
                        "report_json": json.dumps(payload, ensure_ascii=False),
                        "learning_context": _recent_learning_context(),
                    }
                )
        except (FileNotFoundError, OSError, ValueError):
            pass
        try:
            result = client.chat_json(
                model=llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            parsed = dict(result.parsed)
            parsed["source"] = "llm"
            parsed["json_parseable"] = result.json_parseable
            return parsed
        except Exception as exc:  # pragma: no cover - external gateway guard
            logger.warning("LLM review fallback for %s/%s: %s", llm_model, report.stock.stock_code, exc)
            return {"source": "rule_fallback", "reason": str(exc)}

    def _load_account_snapshots(self, models: list[str]) -> dict[str, dict[str, Any]]:
        """Load latest stored account snapshots for selected models.

        Storage is optional. If MongoDB/pymongo is unavailable, the competition
        simply starts from fresh virtual accounts for this run.
        """
        requested_agent_ids = [_agent_id_for_model(model) for model in models]
        try:
            from astock_agent_system.storage import MongoClient

            mongo = MongoClient(self.settings)
            snapshots: dict[str, dict[str, Any]] = {}
            for model in models:
                agent_id = _agent_id_for_model(model)
                snapshot = mongo.get_latest_position_snapshot(agent_id)
                if snapshot:
                    snapshots[agent_id] = snapshot
            mongo.close()
            self._last_snapshot_restore = {
                "status": "ok" if snapshots else "empty",
                "requested": True,
                "loaded_count": len(snapshots),
                "requested_agent_ids": requested_agent_ids,
                "missing_agent_ids": [agent_id for agent_id in requested_agent_ids if agent_id not in snapshots],
            }
            return snapshots
        except Exception as exc:
            compact = _compact_persist_error(exc)
            logger.warning("Loading previous account snapshots skipped: %s", exc)
            self._last_snapshot_restore = {
                "status": "skipped",
                "requested": True,
                "loaded_count": 0,
                "requested_agent_ids": requested_agent_ids,
                "missing_agent_ids": requested_agent_ids,
                "error": compact,
            }
            return {}

    def _snapshot_restore_summary(
        self,
        models: list[str],
        snapshot_by_agent: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Return explicit account-restore metadata for CLI logs and run summaries."""

        requested_agent_ids = [_agent_id_for_model(model) for model in models]
        summary = dict(getattr(self, "_last_snapshot_restore", {}) or {})
        if not summary.get("requested"):
            summary = {
                "status": "ok" if snapshot_by_agent else "empty",
                "requested": True,
                "loaded_count": len(snapshot_by_agent),
                "requested_agent_ids": requested_agent_ids,
                "missing_agent_ids": [agent_id for agent_id in requested_agent_ids if agent_id not in snapshot_by_agent],
            }
        summary.setdefault("requested_agent_ids", requested_agent_ids)
        summary["loaded_count"] = int(summary.get("loaded_count", len(snapshot_by_agent)) or 0)
        summary["missing_agent_ids"] = [agent_id for agent_id in requested_agent_ids if agent_id not in snapshot_by_agent]
        return summary

    def _record_learning_safely(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            recorded = record_competition_experience(payload)
            status = trigger_learning_if_ready()
            return {"recorded": recorded, "record_result": recorded, "status": status}
        except Exception as exc:  # pragma: no cover - learning persistence is best-effort
            logger.warning("Agent learning collection skipped: %s", exc)
            return {"recorded": {"recorded": 0}, "status": "skipped", "reason": str(exc)}

    def _persist_competition(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from astock_agent_system.storage import MongoClient

            mongo = MongoClient(self.settings)
            snapshot_count = 0
            trade_count = 0
            decision_count = 0
            for agent in payload.get("agents", []):
                if not isinstance(agent, dict):
                    continue
                mongo.save_position_snapshot(
                    {
                        "agent_id": agent["agent_id"],
                        "run_id": payload.get("run_id", ""),
                        "date": payload["run_date"],
                        "initial_capital": agent["initial_capital"],
                        "equity": agent["equity"],
                        "cash": agent["cash"],
                        "positions": agent.get("positions", []),
                        "daily_pnl": agent.get("daily_pnl", agent["equity"] - agent["initial_capital"]),
                        "total_pnl": agent["equity"] - agent["initial_capital"],
                        "previous_equity": agent.get("previous_equity", agent["initial_capital"]),
                        "previous_snapshot_date": agent.get("previous_snapshot_date", ""),
                        "skipped_execution": agent.get("skipped_execution", False),
                        "skip_reason": agent.get("skip_reason", ""),
                    }
                )
                snapshot_count += 1
                for trade in agent.get("trades", []):
                    trade_payload = dict(trade)
                    trade_payload.update(
                        {
                            "agent_id": agent["agent_id"],
                            "run_id": payload.get("run_id", ""),
                            "llm_model": agent["llm_model"],
                            "action": trade.get("side"),
                            "amount": float(trade.get("price", 0.0)) * float(trade.get("shares", 0.0)),
                        }
                    )
                    mongo.save_trade(trade_payload)
                    trade_count += 1
                for decision in agent.get("decisions", []):
                    mongo.save_agent_decision(decision)
                    decision_count += 1
            mongo.save_llm_ranking({"date": payload["run_date"], "run_id": payload.get("run_id", ""), "rankings": payload["rankings"]})
            mongo.close()
            return {
                "status": "ok",
                "snapshots": snapshot_count,
                "trades": trade_count,
                "decisions": decision_count,
                "ranking": True,
            }
        except Exception as exc:
            compact = _compact_persist_error(exc)
            logger.warning("Persisting competition skipped: %s %s", compact["code"], compact["reason"])
            return {"status": "skipped", **compact}


def _normalize_models(models: list[str] | None, default_model: str = "") -> list[str]:
    selected = [item.strip() for item in (models or []) if item and item.strip()]
    if selected:
        return selected
    if default_model:
        return [default_model]
    return ["rule-baseline"]


def _agent_id_for_model(model: str) -> str:
    return "agent-" + "".join(ch.lower() if ch.isalnum() else "-" for ch in model).strip("-")


def _recent_learning_context(limit: int = 5) -> str:
    entries = load_experiences(limit=limit)
    if not entries:
        return "暂无足够历史经验。"
    lines: list[str] = []
    for entry in entries:
        outcome = entry.get("outcome", {}) if isinstance(entry.get("outcome", {}), dict) else {}
        lines.append(
            f"- {entry.get('date', '')} {entry.get('stock_code', '')}: "
            f"模型={entry.get('llm_model', '')}, "
            f"收益={outcome.get('return_pct', 0)}%, "
            f"结果={outcome.get('result', '')}"
        )
    return "\n".join(lines)


def _is_same_trade_date_snapshot(snapshot: dict[str, Any] | None, trade_date: str) -> bool:
    """Return True when the daily trading round already ran for this date."""
    if not snapshot:
        return False
    return str(snapshot.get("date", "")) == trade_date


def _result_from_existing_snapshot(
    agent_id: str,
    llm_model: str,
    account: VirtualAccount,
    previous_snapshot: dict[str, Any],
    trade_date: str,
    previous_equity: float,
) -> AgentCompetitionResult:
    """Build an idempotent result without executing duplicate daily trades."""
    latest_prices = _latest_prices_from_snapshot(previous_snapshot)
    account.mark_to_market(trade_date, latest_prices)
    account_payload = account.to_dict(latest_prices)
    equity = _to_float(previous_snapshot.get("equity"), float(account_payload["equity"]))
    total_return = (equity - account.initial_capital) / account.initial_capital if account.initial_capital else 0.0
    positions = _positions_as_rows(account_payload.get("positions", {}), latest_prices)
    return AgentCompetitionResult(
        agent_id=agent_id,
        llm_model=llm_model,
        initial_capital=round(account.initial_capital, 4),
        equity=round(equity, 4),
        cash=round(float(account_payload["cash"]), 4),
        total_return=round(total_return, 6),
        max_drawdown=round(_max_drawdown(account.equity_curve), 6),
        win_rate=0.0,
        total_trades=0,
        buy_count=0,
        sell_count=0,
        daily_pnl=round(equity - previous_equity, 4),
        restored_from_snapshot=True,
        previous_snapshot_date=str(previous_snapshot.get("date", "")),
        previous_equity=round(previous_equity, 4),
        skipped_execution=True,
        skip_reason="already_ran_for_trade_date",
        decisions=[],
        positions=positions,
        trades=[],
    )


def _latest_prices_from_snapshot(snapshot: dict[str, Any]) -> dict[str, float]:
    positions = snapshot.get("positions", [])
    if isinstance(positions, dict):
        iterable = positions.values()
    elif isinstance(positions, list):
        iterable = positions
    else:
        iterable = []
    prices: dict[str, float] = {}
    for item in iterable:
        if not isinstance(item, dict):
            continue
        stock_code = str(item.get("stock_code", "")).strip()
        if not stock_code:
            continue
        price = _to_float(item.get("current_price"), _to_float(item.get("cost_basis"), 0.0))
        if price > 0:
            prices[stock_code] = price
    return prices


def _decision_row(
    report: StockAnalysisReport,
    agent_id: str,
    llm_model: str,
    effective: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    decision = report.decision
    explanation_data = decision.explanation_data if decision and isinstance(decision.explanation_data, dict) else {}
    return {
        "agent_id": agent_id,
        "llm_model": llm_model,
        "stock_code": report.stock.stock_code,
        "stock_name": report.stock.stock_name,
        "timestamp": datetime.now(),
        "action": effective["action"],
        "confidence": effective["confidence"],
        "position_size": effective["position_size"],
        "reasons": decision.reasons if decision else [],
        "risk_notes": decision.risk_notes if decision else [],
        "technical_score": report.technical.score if report.technical else 0.0,
        "fundamental_score": report.fundamental.score if report.fundamental else 0.0,
        "sentiment_score": report.sentiment.score if report.sentiment else 0.0,
        "risk_score": report.risk.score if report.risk else 0.0,
        "rule_action": decision.action if decision else "HOLD",
        "llm_review": override,
        "objective_data": explanation_data.get("objective_data", {}),
        "agent_chain": explanation_data.get("agent_chain", {}),
        "explanation_data": explanation_data,
    }


def _compact_report_for_llm(report: StockAnalysisReport) -> dict[str, Any]:
    decision = report.decision
    return {
        "stock": report.stock.to_dict(),
        "quote": report.quote.to_dict(),
        "technical": report.technical.to_dict() if report.technical else None,
        "fundamental": report.fundamental.to_dict() if report.fundamental else None,
        "sentiment": report.sentiment.to_dict() if report.sentiment else None,
        "risk": report.risk.to_dict() if report.risk else None,
        "rule_decision": decision.to_dict() if decision else None,
    }


def _effective_decision(report: StockAnalysisReport, override: dict[str, Any], settings: Settings) -> dict[str, Any]:
    decision = report.decision
    if decision is None:
        return {"action": "HOLD", "confidence": 0.0, "position_size": 0.0}

    # Risk veto remains mandatory. LLMs may not override it.
    risk_approved = bool(report.risk and report.risk.metadata.get("approved", False))
    if not risk_approved or decision.action == "REJECT":
        return {"action": "REJECT", "confidence": 1.0, "position_size": 0.0}

    action = str(override.get("action", decision.action)).upper()
    if action not in {"BUY", "HOLD", "SELL", "REJECT"}:
        action = decision.action
    confidence = _clamp_float(override.get("confidence"), decision.confidence, 0.0, 1.0)
    if action == "BUY":
        default_size = decision.position_size if decision.action == "BUY" else settings.risk.max_position_per_stock * 0.25
        requested_size = _clamp_float(override.get("position_size"), default_size, 0.0, settings.risk.max_position_per_stock)
        position_size = min(requested_size, settings.risk.max_position_per_stock) * max(0.25, confidence)
    else:
        position_size = 0.0
    return {"action": action, "confidence": round(confidence, 4), "position_size": round(position_size, 6)}


def _clamp_float(value: Any, default: float, lower: float, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(lower, min(upper, number))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ranking_row(result: AgentCompetitionResult, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "agent_id": result.agent_id,
        "llm_model": result.llm_model,
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "equity": result.equity,
        "cash": result.cash,
        "daily_pnl": result.daily_pnl,
        "restored_from_snapshot": result.restored_from_snapshot,
        "previous_snapshot_date": result.previous_snapshot_date,
        "buy_count": result.buy_count,
        "sell_count": result.sell_count,
        "skipped_execution": result.skipped_execution,
        "skip_reason": result.skip_reason,
    }


def _positions_as_rows(positions: Any, latest_prices: dict[str, float]) -> list[dict[str, Any]]:
    if not isinstance(positions, dict):
        return []
    rows: list[dict[str, Any]] = []
    for stock_code, item in positions.items():
        if not isinstance(item, dict):
            continue
        price = latest_prices.get(str(stock_code), float(item.get("cost_basis", 0.0) or 0.0))
        shares = int(item.get("shares", 0) or 0)
        cost_basis = float(item.get("cost_basis", 0.0) or 0.0)
        market_value = shares * price
        rows.append(
            {
                "stock_code": str(stock_code),
                "shares": shares,
                "cost_basis": round(cost_basis, 4),
                "last_buy_date": str(item.get("last_buy_date", "")),
                "current_price": round(price, 4),
                "market_value": round(market_value, 4),
                "unrealized_pnl": round((price - cost_basis) * shares, 4),
                "unrealized_return": round((price - cost_basis) / cost_basis, 6) if cost_basis else 0.0,
            }
        )
    return rows


def _max_drawdown(equity_curve: list[dict[str, float | str]]) -> float:
    peak = 0.0
    max_dd = 0.0
    for row in equity_curve:
        equity = float(row.get("equity", 0.0))
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd


def _win_rate(trades: list[dict[str, Any]]) -> float:
    sells = [trade for trade in trades if trade.get("side") == "SELL"]
    if not sells:
        return 0.0
    wins = sum(1 for trade in sells if float(trade.get("realized_pnl", 0.0)) > 0)
    return wins / len(sells)
