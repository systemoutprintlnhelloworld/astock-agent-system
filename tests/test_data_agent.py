from __future__ import annotations

from astock_agent_system.config import load_settings
from astock_agent_system.data import DataAgent


def _offline_data_agent(monkeypatch) -> DataAgent:
    monkeypatch.setenv("DATA_MODE", "offline")
    monkeypatch.setenv("SMART_SEARCH_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    return DataAgent(settings=load_settings())


def test_data_agent_returns_offline_universe_and_history(monkeypatch):
    data_agent = _offline_data_agent(monkeypatch)
    universe = data_agent.get_universe()

    assert len(universe) >= 3
    for stock in universe[:3]:
        bars = data_agent.get_history(stock.stock_code)
        quote = data_agent.get_quote(stock.stock_code)
        financial = data_agent.get_financial(stock.stock_code)

        assert len(bars) >= 20
        assert quote.price > 0
        assert quote.amount > 0
        assert financial.market_cap > 0


def test_history_days_limit(monkeypatch):
    data_agent = _offline_data_agent(monkeypatch)
    bars = data_agent.get_history("600519", days=5)

    assert len(bars) == 5
    assert bars == sorted(bars, key=lambda item: item.date)
