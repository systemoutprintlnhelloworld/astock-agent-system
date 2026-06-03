"""Automatic task scheduler for daily analysis and paper-trading risk checks."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from astock_agent_system.agents import MasterAgent
from astock_agent_system.backtest import VirtualAccount
from astock_agent_system.config import Settings, load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.notification import build_notifier
from astock_agent_system.orchestrator import MultiAgentOrchestrator
from astock_agent_system.reporting import save_daily_report


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScheduledTaskResult:
    """Structured result for scheduled jobs."""

    task_name: str
    status: str
    started_at: str
    finished_at: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradingTaskScheduler:
    """Run automatic daily analysis and stop-loss checks.

    APScheduler is optional. Direct methods such as ``run_daily_analysis`` and
    ``check_stop_loss`` work without it, which keeps tests and local smoke runs
    dependency-light.
    """

    def __init__(self, settings: Settings | None = None, data_agent: DataAgent | None = None) -> None:
        self.settings = settings or load_settings()
        self.data_agent = data_agent or DataAgent(settings=self.settings)

    def run_daily_analysis(self) -> ScheduledTaskResult:
        """Run the daily candidate screening and analysis pipeline once."""
        started = _now_text()
        try:
            report = MasterAgent(settings=self.settings, data_agent=self.data_agent).run_daily(
                max_count=self.settings.scheduler.max_count,
                history_days=self.settings.scheduler.history_days,
            )
            saved_files = save_daily_report(report, self.settings.scheduler.output_dir)
            persisted = self._persist_agent_decisions(report.to_dict())
            notifications = []
            if self.settings.scheduler.notify_after_daily_run:
                body = f"完成 {len(report.reports)} 只股票自动分析，报告：{saved_files.get('daily_markdown', '')}"
                notifications = [item.to_dict() for item in build_notifier(self.settings).send("A股 Agent 自动分析完成", body)]
            return ScheduledTaskResult(
                task_name="daily_analysis",
                status="ok",
                started_at=started,
                finished_at=_now_text(),
                message=f"generated {len(report.reports)} reports",
                payload={
                    "run_date": report.run_date,
                    "candidate_count": len(report.candidates),
                    "report_count": len(report.reports),
                    "saved_files": saved_files,
                    "persisted_decisions": persisted,
                    "notification": notifications,
                },
            )
        except Exception as exc:  # pragma: no cover - scheduler safety guard
            logger.exception("Scheduled daily analysis failed")
            return ScheduledTaskResult(
                task_name="daily_analysis",
                status="error",
                started_at=started,
                finished_at=_now_text(),
                message=str(exc),
            )

    def run_auto_investment(self, models: list[str] | None = None) -> ScheduledTaskResult:
        """Run one full automatic paper-investment round.

        This is the scheduler-facing entry point for the autonomous mode: each
        selected LLM model manages its own virtual account, results are
        persisted to MongoDB, and stop-loss is checked immediately afterwards.
        The orchestrator is date-idempotent, so repeated runs on the same trade
        date read the existing snapshot instead of duplicating trades.
        """
        started = _now_text()
        try:
            selected_models = models if models is not None else self.settings.scheduler.models or None
            competition = MultiAgentOrchestrator(settings=self.settings, data_agent=self.data_agent).run_competition(
                models=selected_models,
                max_count=self.settings.scheduler.max_count,
                history_days=self.settings.scheduler.history_days,
                initial_capital=self.settings.portfolio.initial_capital,
                persist=True,
                continue_from_storage=True,
            )
            stop_loss = self.check_stop_loss()
            notifications = []
            if self.settings.scheduler.notify_after_daily_run:
                notifications = [
                    item.to_dict()
                    for item in build_notifier(self.settings).send(
                        "A股 Agent 自动投资轮次完成",
                        _auto_investment_notification_body(competition, stop_loss.to_dict()),
                    )
                ]
            return ScheduledTaskResult(
                task_name="auto_investment",
                status="ok" if competition.get("status") == "ok" and stop_loss.status in {"ok", "alert"} else "error",
                started_at=started,
                finished_at=_now_text(),
                message=_auto_investment_message(competition, stop_loss.to_dict()),
                payload={
                    "competition": competition,
                    "stop_loss": stop_loss.to_dict(),
                    "notification": notifications,
                },
            )
        except Exception as exc:  # pragma: no cover - scheduler safety guard
            logger.exception("Scheduled auto investment failed")
            return ScheduledTaskResult(
                task_name="auto_investment",
                status="error",
                started_at=started,
                finished_at=_now_text(),
                message=str(exc),
            )

    def check_stop_loss(self) -> ScheduledTaskResult:
        """Check latest persisted paper positions for stop-loss triggers.

        In paper-trading mode this method restores each latest virtual account,
        executes allowed forced stop-loss sells, then persists the updated
        snapshot and trade records. A-share T+1 is still respected by
        ``VirtualAccount.sell``; same-day buys produce a blocked signal instead
        of an illegal sell.
        """
        started = _now_text()
        try:
            trade_date = datetime.now().strftime("%Y-%m-%d")
            snapshots = self._load_latest_position_snapshots()
            triggers: list[dict[str, Any]] = []
            updated_snapshots: list[dict[str, Any]] = []
            executed_trades: list[dict[str, Any]] = []
            for snapshot in snapshots:
                agent_id = str(snapshot.get("agent_id", "unknown"))
                account = VirtualAccount.from_snapshot(snapshot, settings=self.settings)
                latest_prices: dict[str, float] = {}
                agent_triggers: list[dict[str, Any]] = []
                for position in snapshot.get("positions", []) or []:
                    if not isinstance(position, dict):
                        continue
                    stock_code = str(position.get("stock_code", ""))
                    cost_basis = _to_float(position.get("cost_basis"))
                    shares = int(_to_float(position.get("shares")))
                    if not stock_code or cost_basis <= 0 or shares <= 0:
                        continue
                    quote = self.data_agent.get_quote(stock_code)
                    latest_prices[stock_code] = quote.price
                    threshold = cost_basis * (1.0 - self.settings.risk.stop_loss_pct)
                    if quote.price <= threshold:
                        executed = account.sell(stock_code, quote.price, None, trade_date, reason="forced_stop_loss")
                        trigger = {
                            "agent_id": agent_id,
                            "stock_code": stock_code,
                            "stock_name": quote.stock_name,
                            "shares": shares,
                            "cost_basis": round(cost_basis, 4),
                            "current_price": round(quote.price, 4),
                            "threshold": round(threshold, 4),
                            "stop_loss_pct": self.settings.risk.stop_loss_pct,
                            "trade_date": trade_date,
                            "action": "FORCE_SELL_EXECUTED" if executed else "FORCE_SELL_SIGNAL",
                            "execution_status": "executed" if executed else _blocked_stop_loss_reason(position, trade_date),
                        }
                        triggers.append(trigger)
                        agent_triggers.append(trigger)
                if agent_triggers:
                    account.mark_to_market(trade_date, latest_prices)
                    account_payload = account.to_dict(latest_prices)
                    updated_snapshots.append(_stop_loss_snapshot(agent_id, snapshot, account_payload, latest_prices, trade_date, agent_triggers))
                    for trade in account_payload.get("trades", []):
                        if isinstance(trade, dict) and trade.get("reason") == "forced_stop_loss":
                            trade_payload = dict(trade)
                            trade_payload.update(
                                {
                                    "agent_id": agent_id,
                                    "action": trade.get("side"),
                                    "amount": float(trade.get("price", 0.0)) * float(trade.get("shares", 0.0)),
                                }
                            )
                            executed_trades.append(trade_payload)
            persisted = self._persist_stop_loss_results(triggers, updated_snapshots, executed_trades)
            status = "ok" if not triggers else "alert"
            return ScheduledTaskResult(
                task_name="stop_loss_check",
                status=status,
                started_at=started,
                finished_at=_now_text(),
                message=f"checked {len(snapshots)} position snapshots, triggers={len(triggers)}, executed={len(executed_trades)}",
                payload={
                    "trigger_count": len(triggers),
                    "execution_count": len(executed_trades),
                    "triggers": triggers,
                    "updated_snapshots": updated_snapshots,
                    "executed_trades": executed_trades,
                    "persisted": persisted,
                },
            )
        except Exception as exc:  # pragma: no cover - scheduler safety guard
            logger.exception("Scheduled stop-loss check failed")
            return ScheduledTaskResult(
                task_name="stop_loss_check",
                status="error",
                started_at=started,
                finished_at=_now_text(),
                message=str(exc),
            )

    def run_forever(self) -> None:
        """Start APScheduler and keep the current process alive."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise SystemExit("APScheduler is not installed. Run: pip install -e .[scheduler]") from exc

        hour, minute = _parse_hhmm(self.settings.scheduler.daily_run_time)
        scheduler = BackgroundScheduler(timezone=self.settings.scheduler.timezone)
        scheduler.add_job(
            self.run_auto_investment,
            trigger="cron",
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            id="auto_investment",
            replace_existing=True,
        )
        scheduler.add_job(
            self.check_stop_loss,
            trigger="interval",
            minutes=max(1, self.settings.scheduler.stop_loss_interval_minutes),
            id="stop_loss_check",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "Scheduler started: daily=%s timezone=%s stop_loss_interval=%s minutes",
            self.settings.scheduler.daily_run_time,
            self.settings.scheduler.timezone,
            self.settings.scheduler.stop_loss_interval_minutes,
        )
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def _persist_agent_decisions(self, report_payload: dict[str, Any]) -> int:
        try:
            from astock_agent_system.storage import MongoClient

            mongo = MongoClient(self.settings)
            count = 0
            for item in report_payload.get("reports", []) or []:
                if not isinstance(item, dict):
                    continue
                decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
                stock = item.get("stock") if isinstance(item.get("stock"), dict) else {}
                technical = item.get("technical") if isinstance(item.get("technical"), dict) else {}
                fundamental = item.get("fundamental") if isinstance(item.get("fundamental"), dict) else {}
                sentiment = item.get("sentiment") if isinstance(item.get("sentiment"), dict) else {}
                risk = item.get("risk") if isinstance(item.get("risk"), dict) else {}
                if not decision:
                    continue
                mongo.save_agent_decision(
                    {
                        "agent_id": "master-agent",
                        "stock_code": stock.get("stock_code") or decision.get("stock_code"),
                        "timestamp": datetime.now(),
                        "action": decision.get("action"),
                        "confidence": decision.get("confidence", 0.0),
                        "position_size": decision.get("position_size", 0.0),
                        "reasons": decision.get("reasons", []),
                        "risk_notes": decision.get("risk_notes", []),
                        "technical_score": technical.get("score", 0.0),
                        "fundamental_score": fundamental.get("score", 0.0),
                        "sentiment_score": sentiment.get("score", 0.0),
                        "risk_score": risk.get("score", 0.0),
                    }
                )
                count += 1
            mongo.close()
            return count
        except Exception as exc:
            logger.warning("Persisting agent decisions skipped: %s", exc)
            return 0

    def _load_latest_position_snapshots(self) -> list[dict[str, Any]]:
        try:
            from astock_agent_system.storage import MongoClient

            mongo = MongoClient(self.settings)
            snapshots = mongo.get_latest_position_snapshots()
            mongo.close()
            return snapshots
        except Exception as exc:
            logger.warning("Stop-loss check skipped position storage read: %s", exc)
            return []

    def _persist_stop_loss_results(
        self,
        triggers: list[dict[str, Any]],
        updated_snapshots: list[dict[str, Any]],
        executed_trades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not triggers and not updated_snapshots and not executed_trades:
            return {"status": "skipped", "reason": "no stop-loss triggers"}
        try:
            from astock_agent_system.storage import MongoClient

            mongo = MongoClient(self.settings)
            for trigger in triggers:
                mongo.save_agent_decision(
                    {
                        "agent_id": trigger["agent_id"],
                        "stock_code": trigger["stock_code"],
                        "timestamp": datetime.now(),
                        "action": "FORCE_SELL_SIGNAL",
                        "confidence": 1.0,
                        "position_size": 0.0,
                        "reasons": ["触发强制止损阈值"],
                        "metadata": trigger,
                    }
                )
            for snapshot in updated_snapshots:
                mongo.save_position_snapshot(snapshot)
            for trade in executed_trades:
                mongo.save_trade(trade)
            mongo.close()
            return {
                "status": "ok",
                "signals": len(triggers),
                "snapshots": len(updated_snapshots),
                "trades": len(executed_trades),
            }
        except Exception as exc:
            logger.warning("Persisting stop-loss signals skipped: %s", exc)
            return {"status": "skipped", "reason": str(exc)}


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {value!r}, expected HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid time value: {value!r}")
    return hour, minute


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _blocked_stop_loss_reason(position: dict[str, Any], trade_date: str) -> str:
    if str(position.get("last_buy_date", "")) == trade_date:
        return "blocked_t1_same_day_buy"
    return "blocked_no_sellable_shares"


def _auto_investment_message(competition: dict[str, Any], stop_loss: dict[str, Any]) -> str:
    rankings = competition.get("rankings") if isinstance(competition.get("rankings"), list) else []
    leader = rankings[0] if rankings and isinstance(rankings[0], dict) else {}
    skipped = sum(1 for item in rankings if isinstance(item, dict) and item.get("skipped_execution"))
    stop_payload = stop_loss.get("payload") if isinstance(stop_loss.get("payload"), dict) else {}
    trigger_count = int(_to_float(stop_payload.get("trigger_count")))
    execution_count = int(_to_float(stop_payload.get("execution_count")))
    return (
        f"auto investment run_date={competition.get('run_date', '-')} models={competition.get('model_count', 0)} "
        f"leader={leader.get('llm_model', '-')} skipped={skipped} stop_loss={trigger_count}/{execution_count}"
    )


def _auto_investment_notification_body(competition: dict[str, Any], stop_loss: dict[str, Any]) -> str:
    rankings = competition.get("rankings") if isinstance(competition.get("rankings"), list) else []
    leader = rankings[0] if rankings and isinstance(rankings[0], dict) else {}
    stop_payload = stop_loss.get("payload") if isinstance(stop_loss.get("payload"), dict) else {}
    return "\n".join(
        [
            f"日期：{competition.get('run_date', '-')}",
            f"模型账户数：{competition.get('model_count', 0)}",
            f"当前第一名：{leader.get('llm_model', '-')}",
            f"第一名权益：{leader.get('equity', '-')}",
            f"止损触发/执行：{stop_payload.get('trigger_count', 0)}/{stop_payload.get('execution_count', 0)}",
        ]
    )


def _stop_loss_snapshot(
    agent_id: str,
    previous_snapshot: dict[str, Any],
    account_payload: dict[str, Any],
    latest_prices: dict[str, float],
    trade_date: str,
    triggers: list[dict[str, Any]],
) -> dict[str, Any]:
    initial_capital = _to_float(account_payload.get("initial_capital"))
    equity = _to_float(account_payload.get("equity"))
    previous_equity = _to_float(previous_snapshot.get("equity"), initial_capital)
    execution_count = sum(1 for trigger in triggers if trigger.get("execution_status") == "executed")
    return {
        "agent_id": agent_id,
        "date": trade_date,
        "initial_capital": initial_capital,
        "equity": round(equity, 4),
        "cash": round(_to_float(account_payload.get("cash")), 4),
        "positions": _positions_as_rows(account_payload.get("positions", {}), latest_prices),
        "daily_pnl": round(equity - previous_equity, 4),
        "total_pnl": round(equity - initial_capital, 4),
        "previous_equity": round(previous_equity, 4),
        "previous_snapshot_date": str(previous_snapshot.get("date", "")),
        "stop_loss_trigger_count": len(triggers),
        "stop_loss_execution_count": execution_count,
        "stop_loss_triggers": triggers,
    }


def _positions_as_rows(positions: Any, latest_prices: dict[str, float]) -> list[dict[str, Any]]:
    if not isinstance(positions, dict):
        return []
    rows: list[dict[str, Any]] = []
    for stock_code, item in positions.items():
        if not isinstance(item, dict):
            continue
        shares = int(_to_float(item.get("shares")))
        cost_basis = _to_float(item.get("cost_basis"))
        price = latest_prices.get(str(stock_code), cost_basis)
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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
