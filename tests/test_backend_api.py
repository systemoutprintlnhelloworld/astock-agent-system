from __future__ import annotations

import importlib
import json
from typing import Any

from fastapi.testclient import TestClient

from apps.backend.app import app, make_event, settings_to_public_dict
from astock_agent_system.config import load_settings
from astock_agent_system.scheduler import ScheduledTaskResult


backend_app_module = importlib.import_module("apps.backend.app")


def test_health_endpoint_exposes_backend_metadata() -> None:
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "AStock Agent Modern Backend"
    assert "run_started" in payload["event_types"]


def test_config_endpoint_redacts_local_secrets(monkeypatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "x")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("SMTP_USERNAME", "x")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://webhook.example/hook")
    monkeypatch.setenv("MONGO_URI", "mongodb://user:pass@localhost:27017")
    monkeypatch.setenv("REDIS_URL", "redis://user:pass@localhost:6379/0")

    client = TestClient(app)
    response = client.get("/api/config")

    assert response.status_code == 200
    config = response.json()["config"]
    serialized = json.dumps(config, ensure_ascii=False)
    assert "user:pass" not in serialized
    assert "https://webhook.example/hook" not in serialized
    assert config["data"]["has_tushare_token"] is True
    assert config["llm"]["has_api_key"] is True
    assert config["storage"]["mongo_uri"] == "mongodb://[REDACTED]@localhost:27017"
    assert config["storage"]["redis_url"] == "redis://[REDACTED]@localhost:6379/0"


def test_public_settings_helper_never_returns_api_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("TUSHARE_TOKEN", "x")

    public_config = settings_to_public_dict(load_settings())

    assert public_config["llm"]["has_api_key"] is True
    assert "api_key" not in public_config["llm"]
    assert "tushare_token" not in public_config["data"]


def test_bench_endpoint_skips_without_llm_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "")
    client = TestClient(app)

    response = client.post("/api/bench", json={"models": ["demo-model"], "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "skipped"
    assert payload["results"] == []


def test_auto_investment_endpoint_reuses_scheduler(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeScheduler:
        def __init__(self, settings) -> None:  # noqa: ANN001 - mirrors production constructor
            captured["data_mode"] = settings.data.mode
            captured["max_count"] = settings.scheduler.max_count
            captured["history_days"] = settings.scheduler.history_days

        def run_auto_investment(self, models):  # noqa: ANN001 - mirrors production method
            captured["models"] = models
            return ScheduledTaskResult(
                task_name="auto_investment",
                status="ok",
                started_at="2026-06-03T10:00:00",
                finished_at="2026-06-03T10:00:01",
                message="auto investment smoke ok",
                payload={
                    "competition": {
                        "status": "ok",
                        "run_date": "2026-06-03",
                        "rankings": [
                            {
                                "rank": 1,
                                "agent_id": "agent-rule",
                                "llm_model": "rule-baseline",
                                "total_return": 0.01,
                                "max_drawdown": 0.0,
                                "win_rate": 1.0,
                                "total_trades": 1,
                                "equity": 101000,
                                "cash": 90000,
                                "daily_pnl": 1000,
                            }
                        ],
                        "agents": [
                            {
                                "agent_id": "agent-rule",
                                "llm_model": "rule-baseline",
                                "decisions": [
                                    {
                                        "stock_code": "600000",
                                        "stock_name": "浦发银行",
                                        "action": "BUY",
                                        "confidence": 0.8,
                                        "position_size": 0.1,
                                        "reasons": ["趋势改善"],
                                        "risk_notes": ["模拟盘验证"],
                                        "technical_score": 0.7,
                                        "fundamental_score": 0.6,
                                        "sentiment_score": 0.5,
                                        "risk_score": 0.9,
                                        "llm_review": {"source": "rule_fallback", "reason": "llm_not_configured"},
                                    }
                                ],
                                "positions": [
                                    {
                                        "stock_code": "600000",
                                        "shares": 100,
                                        "cost_basis": 10.0,
                                        "current_price": 10.5,
                                        "market_value": 1050,
                                        "unrealized_return": 0.05,
                                    }
                                ],
                                "trades": [
                                    {
                                        "date": "2026-06-03",
                                        "stock_code": "600000",
                                        "side": "BUY",
                                        "price": 10.0,
                                        "shares": 100,
                                        "reason": "agent_buy",
                                    }
                                ],
                            }
                        ],
                    },
                    "stop_loss": {"status": "ok"},
                },
            )

    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setattr(backend_app_module, "TradingTaskScheduler", _FakeScheduler)
    client = TestClient(app)

    response = client.post(
        "/api/auto-investment",
        json={"models": ["rule-baseline"], "offline": True, "max_count": 2, "days": 12},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["run_id"]
    assert payload["result"]["task_name"] == "auto_investment"
    assert captured == {"data_mode": "offline", "max_count": 2, "history_days": 12, "models": ["rule-baseline"]}

    decisions = client.get("/api/decisions").json()
    assert decisions["schema_version"] == "2026-06-03"
    assert decisions["items"][0]["stock_code"] == "600000"
    assert decisions["items"][0]["steps"][0]["title"] == "多 Agent 评分"

    board = client.get("/api/stocks/board").json()
    assert board["holdings"][0]["market_value"] == 1050
    assert board["candidates"][0]["stock_name"] == "浦发银行"
    assert board["trades"][0]["side"] == "BUY"

    equity = client.get("/api/metrics/equity").json()
    assert equity["series"][0]["equity"] == 101000

    rankings = client.get("/api/metrics/rankings").json()
    assert rankings["rankings"][0]["llm_model"] == "rule-baseline"

    run = client.get("/api/runs/current").json()
    assert run["status"] == "idle"
    assert run["run"]["status"] == "ok"


def test_agent_flow_endpoint_returns_animated_react_flow_edges() -> None:
    client = TestClient(app)

    response = client.get("/api/agents/flow")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert any(node["id"] == "risk_manager" for node in payload["nodes"])
    assert payload["edges"]
    assert all(edge["animated"] is True for edge in payload["edges"])


def test_websocket_events_support_ping_pong() -> None:
    client = TestClient(app)

    with client.websocket_connect("/ws/events") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connection_established"

        websocket.send_json({"type": "ping", "payload": {"from": "test"}})
        pong = websocket.receive_json()

        assert pong["type"] == "pong"
        assert pong["payload"]["echo"] == {"from": "test"}


def test_make_event_falls_back_to_error_type_for_unknown_events() -> None:
    event = make_event("unknown_event", payload={"reason": "bad type"})

    assert event["type"] == "error"
    assert event["payload"] == {"reason": "bad type"}
