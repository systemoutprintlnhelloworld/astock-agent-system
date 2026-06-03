from __future__ import annotations

from astock_agent_system.backtest import BacktestEngine, VirtualAccount
from astock_agent_system.config import load_settings


def _offline_settings(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    return load_settings()


def test_virtual_account_buy_sell_and_t1(monkeypatch):
    settings = _offline_settings(monkeypatch)
    account = VirtualAccount(settings, initial_capital=100000)

    assert account.buy("000333", price=70, target_value=10000, date="2026-01-02") is True
    assert account.sell("000333", price=71, shares=None, date="2026-01-02") is False
    assert account.sell("000333", price=72, shares=None, date="2026-01-03") is True
    assert account.cash > 0
    assert len(account.trades) == 2


def test_virtual_account_restores_from_snapshot_and_keeps_t1(monkeypatch):
    settings = _offline_settings(monkeypatch)
    snapshot = {
        "initial_capital": 100000,
        "cash": 90000,
        "positions": [
            {
                "stock_code": "000333",
                "shares": 100,
                "cost_basis": 70,
                "last_buy_date": "2026-01-02",
            }
        ],
    }

    account = VirtualAccount.from_snapshot(snapshot, settings=settings)

    assert account.initial_capital == 100000
    assert account.cash == 90000
    assert account.positions["000333"].shares == 100
    assert account.positions["000333"].last_buy_date == "2026-01-02"
    assert account.sell("000333", price=71, shares=None, date="2026-01-02") is False
    assert account.sell("000333", price=72, shares=None, date="2026-01-03") is True


def test_backtest_engine_outputs_core_metrics(monkeypatch):
    settings = _offline_settings(monkeypatch)
    result = BacktestEngine(settings=settings).run(max_count=2, initial_capital=100000)
    payload = result.to_dict()

    assert payload["status"] == "ok"
    assert payload["initial_capital"] == 100000
    assert "total_return" in payload
    assert "max_drawdown" in payload
    assert "win_rate" in payload
    assert isinstance(payload["equity_curve"], list)
    assert len(payload["equity_curve"]) >= 6
