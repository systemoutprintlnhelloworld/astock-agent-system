from __future__ import annotations

from astock_agent_system.agents import MasterAgent, StockScreener
from astock_agent_system.config import load_settings
from astock_agent_system.notification import build_notifier


def _offline_settings(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "")
    monkeypatch.setenv("SMTP_HOST", "")
    return load_settings()


def test_dynamic_screener_returns_sorted_candidates(monkeypatch):
    settings = _offline_settings(monkeypatch)
    candidates = StockScreener().screen(max_count=3)

    assert settings.data.mode == "offline"
    assert len(candidates) == 3
    assert candidates == sorted(candidates, key=lambda item: item.score, reverse=True)
    assert candidates[0].technical.score >= 0
    assert candidates[0].fundamental.score >= 0


def test_master_agent_single_stock_decision_is_complete(monkeypatch):
    settings = _offline_settings(monkeypatch)
    report = MasterAgent(settings=settings).analyze_stock("600519")
    payload = report.to_dict()

    assert payload["stock"]["stock_code"] == "600519"
    assert payload["technical"]["score"] >= 0
    assert payload["fundamental"]["score"] >= 0
    assert payload["sentiment"]["metadata"]["source"] == "offline"
    assert payload["risk"]["metadata"]["approved"] in {True, False}
    assert payload["decision"]["action"] in {"BUY", "SELL", "HOLD", "REJECT"}


def test_notifier_safely_skips_when_unconfigured(monkeypatch):
    settings = _offline_settings(monkeypatch)
    results = build_notifier(settings).send("test", "body")

    assert results[0].status == "skipped"
