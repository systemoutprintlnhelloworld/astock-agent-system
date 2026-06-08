from __future__ import annotations

import json

from astock_agent_system.config import load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.data.data_agent import build_provider_catalog, normalize_provider_name, provider_supports
from astock_agent_system.data.providers.alpha_vantage_provider import AlphaVantageProvider
from astock_agent_system.models import StockBar


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


def test_provider_catalog_normalizes_aliases_and_redacts_credentials(monkeypatch):
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "Tushare,alpha-vantage,同花顺")
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-tushare-token")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "secret-alpha-key")
    monkeypatch.setenv("JQDATA_USERNAME", "secret-user")
    monkeypatch.setenv("JQDATA_PASSWORD", "secret-password")
    settings = load_settings()

    catalog = build_provider_catalog(settings)
    serialized = json.dumps(catalog, ensure_ascii=False)

    assert normalize_provider_name("alpha-vantage") == "alpha_vantage"
    assert normalize_provider_name("同花顺") == "ths_skill"
    assert provider_supports("akshare", "financial") is True
    assert provider_supports("baostock", "financial") is False
    assert "secret-tushare-token" not in serialized
    assert "secret-alpha-key" not in serialized
    assert "secret-password" not in serialized
    assert any(item["source"] == "alpha_vantage" and item["has_credentials"] is True for item in catalog)
    assert any(item["source"] == "ths_skill" and item["adapter_available"] is False for item in catalog)


def test_alpha_vantage_symbol_normalizes_common_a_share_suffixes():
    provider = AlphaVantageProvider(api_key="demo")

    assert provider._to_alpha_symbol("600000.SH") == "600000.SHH"
    assert provider._to_alpha_symbol("600000.SSE") == "600000.SHH"
    assert provider._to_alpha_symbol("000001.SZ") == "000001.SHZ"
    assert provider._to_alpha_symbol("000001.SZSE") == "000001.SHZ"
    assert provider._to_alpha_symbol("AAPL") == "AAPL"


def test_provider_chain_uses_online_fallback_before_offline(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "tushare,baostock,akshare")
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("LLM_API_KEY", "")

    class _FakeBaostockProvider:
        def get_history(self, stock_code: str, days: int = 30, **_: object) -> list[StockBar]:
            return [
                StockBar(
                    stock_code=stock_code,
                    date="2026-06-01",
                    open=10.0,
                    high=11.0,
                    low=9.5,
                    close=10.5,
                    volume=1000.0,
                    amount=10500.0,
                )
            ]

    import astock_agent_system.data.providers as providers

    monkeypatch.setattr(providers, "BaostockProvider", _FakeBaostockProvider)
    data_agent = DataAgent(settings=load_settings())

    bars = data_agent.get_history("600519", days=5)
    diagnostics = data_agent.provider_diagnostics()

    assert len(bars) == 1
    assert bars[0].close == 10.5
    assert diagnostics["provider_chain"] == ["tushare", "baostock", "akshare"]
    assert any(item["source"] == "tushare" and item["status"] == "skipped" for item in diagnostics["attempts"])
    assert any(item["source"] == "baostock" and item["operation"] == "history" and item["status"] == "ok" for item in diagnostics["attempts"])


def test_online_provider_chain_falls_back_to_offline_samples(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "tushare")
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    data_agent = DataAgent(settings=load_settings())

    bars = data_agent.get_history("600519", days=3)
    diagnostics = data_agent.provider_diagnostics()

    assert len(bars) == 3
    assert any(item["source"] == "offline" and item["operation"] == "history" for item in diagnostics["attempts"])
