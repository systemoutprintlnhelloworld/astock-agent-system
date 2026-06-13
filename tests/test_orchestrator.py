from __future__ import annotations

import json

from astock_agent_system.cli import build_parser
from astock_agent_system.cli_enhanced import RunLogRecorder
from astock_agent_system.agents.master_agent import MasterAgent
from astock_agent_system.config import load_settings
from astock_agent_system.events import AgentEventEmitter
from astock_agent_system.orchestrator import MultiAgentOrchestrator


def _offline_settings(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    return load_settings()


def test_competition_runs_independent_accounts_without_persistence(monkeypatch):
    settings = _offline_settings(monkeypatch)
    payload = MultiAgentOrchestrator(settings=settings).run_competition(
        models=["rule-baseline", "demo-model"],
        max_count=2,
        history_days=12,
        initial_capital=100000,
        trade_date="2026-01-05",
        persist=False,
        continue_from_storage=False,
    )

    assert payload["status"] == "ok"
    assert payload["run_id"]
    assert payload["run_date"] == "2026-01-05"
    assert payload["account_mode"] == "fresh_start"
    assert payload["fresh_start"] is True
    assert payload["continue_from_storage"] is False
    assert payload["snapshot_restore"]["status"] == "fresh_start"
    assert payload["snapshot_restore"]["loaded_count"] == 0
    assert payload["restored_account_count"] == 0
    assert payload["skipped_agent_count"] == 0
    assert payload["model_count"] == 2
    assert "persisted" not in payload
    assert len(payload["rankings"]) == 2
    assert len(payload["agents"]) == 2

    agent_ids = {agent["agent_id"] for agent in payload["agents"]}
    assert agent_ids == {"agent-rule-baseline", "agent-demo-model"}
    for agent in payload["agents"]:
        assert agent["initial_capital"] == 100000
        assert "equity" in agent
        assert "cash" in agent
        assert isinstance(agent["decisions"], list)
        assert isinstance(agent["positions"], list)
        assert isinstance(agent["trades"], list)
        if agent["llm_model"] == "demo-model":
            assert all(decision["llm_review"]["source"] == "rule_fallback" for decision in agent["decisions"])

    returns = [row["total_return"] for row in payload["rankings"]]
    assert returns == sorted(returns, reverse=True)


def test_offline_competition_skips_llm_review_even_with_default_model(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "gpt-5.5")
    settings = load_settings()

    payload = MultiAgentOrchestrator(settings=settings).run_competition(
        models=None,
        max_count=1,
        history_days=5,
        trade_date="2026-01-05",
        persist=False,
        continue_from_storage=False,
        collect_learning=False,
    )

    agent = payload["agents"][0]
    assert agent["llm_model"] == "gpt-5.5"
    assert agent["decisions"]
    assert all(
        decision["llm_review"] == {"source": "rule_fallback", "reason": "offline_mode"}
        for decision in agent["decisions"]
    )


def test_competition_can_continue_from_previous_snapshot(monkeypatch):
    settings = _offline_settings(monkeypatch)
    orchestrator = MultiAgentOrchestrator(settings=settings)
    previous_snapshot = {
        "agent_id": "agent-rule-baseline",
        "date": "2026-01-04",
        "initial_capital": 100000,
        "cash": 95000,
        "equity": 99350,
        "positions": [
            {
                "stock_code": "600036",
                "shares": 100,
                "cost_basis": 43.5,
                "last_buy_date": "2026-01-04",
            }
        ],
    }
    monkeypatch.setattr(orchestrator, "_load_account_snapshots", lambda models: {"agent-rule-baseline": previous_snapshot})

    payload = orchestrator.run_competition(
        models=["rule-baseline"],
        max_count=1,
        history_days=12,
        trade_date="2026-01-05",
        persist=False,
    )

    agent = payload["agents"][0]
    assert agent["restored_from_snapshot"] is True
    assert agent["previous_snapshot_date"] == "2026-01-04"
    assert agent["previous_equity"] == 99350
    assert agent["initial_capital"] == 100000
    assert round(agent["equity"] - 99350, 4) == agent["daily_pnl"]
    assert payload["account_mode"] == "continue_from_storage"
    assert payload["fresh_start"] is False
    assert payload["continue_from_storage"] is True
    assert payload["restored_account_count"] == 1
    assert payload["snapshot_restore"]["loaded_count"] == 1
    assert payload["snapshot_restore"]["missing_agent_ids"] == []
    assert payload["rankings"][0]["restored_from_snapshot"] is True
    assert payload["rankings"][0]["previous_snapshot_date"] == "2026-01-04"


def test_competition_is_idempotent_for_existing_trade_date_snapshot(monkeypatch):
    settings = _offline_settings(monkeypatch)
    orchestrator = MultiAgentOrchestrator(settings=settings)
    previous_snapshot = {
        "agent_id": "agent-rule-baseline",
        "date": "2026-01-05",
        "initial_capital": 100000,
        "cash": 95000,
        "equity": 99350,
        "positions": [
            {
                "stock_code": "600036",
                "shares": 100,
                "cost_basis": 43.5,
                "last_buy_date": "2026-01-05",
                "current_price": 43.5,
            }
        ],
    }
    monkeypatch.setattr(orchestrator, "_load_account_snapshots", lambda models: {"agent-rule-baseline": previous_snapshot})

    payload = orchestrator.run_competition(
        models=["rule-baseline"],
        max_count=1,
        history_days=12,
        trade_date="2026-01-05",
        persist=False,
    )

    agent = payload["agents"][0]
    assert agent["restored_from_snapshot"] is True
    assert agent["skipped_execution"] is True
    assert agent["skip_reason"] == "already_ran_for_trade_date"
    assert agent["previous_snapshot_date"] == "2026-01-05"
    assert agent["equity"] == 99350
    assert agent["cash"] == 95000
    assert agent["daily_pnl"] == 0
    assert agent["decisions"] == []
    assert agent["trades"] == []
    assert agent["total_trades"] == 0
    assert agent["buy_count"] == 0
    assert agent["sell_count"] == 0
    assert agent["positions"][0]["shares"] == 100
    assert payload["restored_account_count"] == 1
    assert payload["skipped_agent_count"] == 1
    assert payload["snapshot_restore"]["skipped_agent_ids"] == ["agent-rule-baseline"]
    assert payload["rankings"][0]["skipped_execution"] is True
    assert payload["rankings"][0]["skip_reason"] == "already_ran_for_trade_date"


def test_compete_cli_parser_wires_command_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "compete",
            "--offline",
            "--models",
            "rule-baseline,demo-model",
            "--max-count",
            "2",
            "--days",
            "12",
            "--initial-capital",
            "100000",
            "--fresh-start",
            "--no-persist",
        ]
    )

    assert args.func.__name__ == "_cmd_compete"
    assert args.offline is True
    assert args.models == "rule-baseline,demo-model"
    assert args.max_count == 2
    assert args.days == 12
    assert args.initial_capital == 100000
    assert args.fresh_start is True
    assert args.no_persist is True


def test_datasource_active_scan_cli_parser_wires_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "datasource",
            "active-scan",
            "--limit",
            "20",
            "--sector",
            "银行",
            "--sector",
            "半导体,券商",
            "--min-amount",
            "100000000",
            "--top-per-sector",
            "3",
            "--format",
            "json",
        ]
    )

    assert args.func.__name__ == "cmd_datasource_active_scan"
    assert args.limit == 20
    assert args.sector == ["银行", "半导体,券商"]
    assert args.min_amount == 100000000
    assert args.top_per_sector == 3
    assert args.format == "json"


def test_run_log_summary_records_run_and_account_metadata(monkeypatch, tmp_path):
    settings = _offline_settings(monkeypatch)
    import astock_agent_system.cli_enhanced as cli_enhanced

    monkeypatch.setattr(cli_enhanced, "PROJECT_ROOT", tmp_path)
    recorder = RunLogRecorder(settings, models=["rule-baseline"])
    payload = {
        "status": "ok",
        "run_id": "run-1234",
        "run_date": "2026-01-05",
        "account_mode": "fresh_start",
        "fresh_start": True,
        "continue_from_storage": False,
        "restored_account_count": 0,
        "skipped_agent_count": 0,
        "snapshot_restore": {"status": "fresh_start", "loaded_count": 0},
        "model_count": 1,
        "rankings": [],
    }

    recorder.write_summary(payload)
    summary = json.loads(recorder.summary_path.read_text(encoding="utf-8"))

    assert summary["run_id"] == "run-1234"
    assert summary["fresh_start"] is True
    assert summary["continue_from_storage"] is False
    assert summary["snapshot_restore"]["status"] == "fresh_start"
    assert summary["log_path"].endswith(".jsonl")
    assert summary["summary_path"].endswith(".summary.json")


def test_master_agent_emits_fine_grained_observability_events(monkeypatch):
    settings = _offline_settings(monkeypatch)
    emitter = AgentEventEmitter()
    events = []
    emitter.subscribe(events.append)

    report = MasterAgent(settings=settings, event_emitter=emitter).analyze_stock("600036", history_days=5)

    event_types = [event.type for event in events]
    assert report.decision is not None
    assert report.decision.explanation_data.get("objective_data", {}).get("bars")
    assert "data_fetch_start" in event_types
    assert "data_fetch_complete" in event_types
    assert "technical_analysis_start" in event_types
    assert "technical_analysis_complete" in event_types
    assert "fundamental_analysis_start" in event_types
    assert "fundamental_analysis_complete" in event_types
    assert "sentiment_analysis_start" in event_types
    assert "sentiment_analysis_complete" in event_types
    assert "debate_start" in event_types
    assert "debate_complete" in event_types
    assert "risk_analysis_start" in event_types
    assert "risk_analysis_complete" in event_types
    assert "portfolio_decision_start" in event_types
    assert "portfolio_decision_complete" in event_types

    data_event = next(event for event in events if event.type == "data_fetch_complete")
    assert data_event.payload["history_count"] == 5
    assert isinstance(data_event.payload.get("data_sources"), list)

    decision_event = next(event for event in events if event.type == "portfolio_decision_complete")
    assert decision_event.payload["agent_scores"]["technical"] == round(report.technical.score, 4)
    assert "objective_data" in decision_event.payload["explanation_data"]
