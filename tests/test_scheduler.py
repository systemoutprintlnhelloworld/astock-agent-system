from __future__ import annotations

from datetime import datetime
from typing import Any

from astock_agent_system.cli import build_parser
from astock_agent_system.config import load_settings
from astock_agent_system.models import StockQuote
from astock_agent_system.scheduler import ScheduledTaskResult, TradingTaskScheduler


class _QuoteDataAgent:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices

    def get_quote(self, stock_code: str) -> StockQuote:
        price = self.prices[stock_code]
        return StockQuote(
            stock_code=stock_code,
            stock_name=stock_code,
            date=datetime.now().strftime("%Y-%m-%d"),
            price=price,
            change_pct=0.0,
            volume=1000,
            amount=price * 1000,
        )


def _offline_settings(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    return load_settings()


def test_stop_loss_check_executes_forced_paper_sell(monkeypatch):
    settings = _offline_settings(monkeypatch)
    scheduler = TradingTaskScheduler(settings=settings, data_agent=_QuoteDataAgent({"600000": 90.0}))  # type: ignore[arg-type]
    snapshot = {
        "agent_id": "agent-demo",
        "date": "2026-01-02",
        "initial_capital": 100000,
        "cash": 90000,
        "equity": 100000,
        "positions": [
            {
                "stock_code": "600000",
                "shares": 100,
                "cost_basis": 100.0,
                "last_buy_date": "2026-01-01",
            }
        ],
    }
    monkeypatch.setattr(scheduler, "_load_latest_position_snapshots", lambda: [snapshot])
    persisted: dict[str, Any] = {}

    def _capture_persist(triggers, updated_snapshots, executed_trades):
        persisted["triggers"] = triggers
        persisted["updated_snapshots"] = updated_snapshots
        persisted["executed_trades"] = executed_trades
        return {"status": "ok"}

    monkeypatch.setattr(scheduler, "_persist_stop_loss_results", _capture_persist)

    result = scheduler.check_stop_loss()

    assert result.status == "alert"
    assert result.payload["trigger_count"] == 1
    assert result.payload["execution_count"] == 1
    trigger = result.payload["triggers"][0]
    assert trigger["action"] == "FORCE_SELL_EXECUTED"
    assert trigger["execution_status"] == "executed"
    assert persisted["updated_snapshots"][0]["positions"] == []
    assert persisted["executed_trades"][0]["reason"] == "forced_stop_loss"


def test_stop_loss_check_respects_t1_same_day_buy(monkeypatch):
    settings = _offline_settings(monkeypatch)
    scheduler = TradingTaskScheduler(settings=settings, data_agent=_QuoteDataAgent({"600000": 90.0}))  # type: ignore[arg-type]
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot = {
        "agent_id": "agent-demo",
        "date": today,
        "initial_capital": 100000,
        "cash": 90000,
        "equity": 99000,
        "positions": [
            {
                "stock_code": "600000",
                "shares": 100,
                "cost_basis": 100.0,
                "last_buy_date": today,
            }
        ],
    }
    monkeypatch.setattr(scheduler, "_load_latest_position_snapshots", lambda: [snapshot])
    monkeypatch.setattr(
        scheduler,
        "_persist_stop_loss_results",
        lambda triggers, updated_snapshots, executed_trades: {"status": "ok"},
    )

    result = scheduler.check_stop_loss()

    assert result.status == "alert"
    assert result.payload["trigger_count"] == 1
    assert result.payload["execution_count"] == 0
    trigger = result.payload["triggers"][0]
    assert trigger["action"] == "FORCE_SELL_SIGNAL"
    assert trigger["execution_status"] == "blocked_t1_same_day_buy"
    assert result.payload["updated_snapshots"][0]["positions"][0]["shares"] == 100


def test_auto_investment_runs_competition_then_stop_loss(monkeypatch):
    settings = _offline_settings(monkeypatch)
    settings.scheduler.max_count = 2
    settings.scheduler.history_days = 12
    settings.portfolio.initial_capital = 123456
    captured: dict[str, Any] = {}

    class _FakeOrchestrator:
        def __init__(self, settings, data_agent) -> None:  # noqa: ANN001 - mirrors production constructor
            captured["settings"] = settings
            captured["data_agent"] = data_agent

        def run_competition(self, **kwargs):  # noqa: ANN001 - simple test double
            captured["competition_kwargs"] = kwargs
            return {
                "status": "ok",
                "run_date": "2026-01-05",
                "model_count": 1,
                "rankings": [{"llm_model": "demo-model", "equity": 123000, "skipped_execution": False}],
            }

    monkeypatch.setattr("astock_agent_system.scheduler.task_scheduler.MultiAgentOrchestrator", _FakeOrchestrator)
    scheduler = TradingTaskScheduler(settings=settings, data_agent=_QuoteDataAgent({}))  # type: ignore[arg-type]
    monkeypatch.setattr(
        scheduler,
        "check_stop_loss",
        lambda: ScheduledTaskResult(
            task_name="stop_loss_check",
            status="ok",
            started_at="2026-01-05T15:10:00",
            finished_at="2026-01-05T15:10:01",
            payload={"trigger_count": 0, "execution_count": 0},
        ),
    )

    result = scheduler.run_auto_investment(models=["demo-model"])

    assert result.status == "ok"
    assert result.task_name == "auto_investment"
    assert "auto investment" in result.message
    assert result.payload["competition"]["model_count"] == 1
    assert result.payload["stop_loss"]["status"] == "ok"
    assert captured["competition_kwargs"] == {
        "models": ["demo-model"],
        "max_count": 2,
        "history_days": 12,
        "initial_capital": 123456,
        "persist": True,
        "continue_from_storage": True,
    }


def test_auto_investment_uses_configured_scheduler_models(monkeypatch):
    settings = _offline_settings(monkeypatch)
    settings.scheduler.models = ["rule-baseline", "demo-model"]
    captured: dict[str, Any] = {}

    class _FakeOrchestrator:
        def __init__(self, settings, data_agent) -> None:  # noqa: ANN001 - mirrors production constructor
            captured["settings"] = settings
            captured["data_agent"] = data_agent

        def run_competition(self, **kwargs):  # noqa: ANN001 - simple test double
            captured["competition_kwargs"] = kwargs
            return {
                "status": "ok",
                "run_date": "2026-01-05",
                "model_count": 2,
                "rankings": [{"llm_model": "rule-baseline", "equity": 100000, "skipped_execution": False}],
            }

    monkeypatch.setattr("astock_agent_system.scheduler.task_scheduler.MultiAgentOrchestrator", _FakeOrchestrator)
    scheduler = TradingTaskScheduler(settings=settings, data_agent=_QuoteDataAgent({}))  # type: ignore[arg-type]
    monkeypatch.setattr(
        scheduler,
        "check_stop_loss",
        lambda: ScheduledTaskResult(
            task_name="stop_loss_check",
            status="ok",
            started_at="2026-01-05T15:10:00",
            finished_at="2026-01-05T15:10:01",
            payload={"trigger_count": 0, "execution_count": 0},
        ),
    )

    result = scheduler.run_auto_investment()

    assert result.status == "ok"
    assert captured["competition_kwargs"]["models"] == ["rule-baseline", "demo-model"]


def test_scheduler_auto_investment_cli_parser_wires_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scheduler",
            "run-auto-investment",
            "--offline",
            "--models",
            "gpt-5.4-mini,codex-auto-review",
            "--max-count",
            "2",
            "--days",
            "12",
        ]
    )

    assert args.func.__name__ == "_cmd_scheduler_run_auto_investment"
    assert args.offline is True
    assert args.models == "gpt-5.4-mini,codex-auto-review"
    assert args.max_count == 2
    assert args.days == 12
