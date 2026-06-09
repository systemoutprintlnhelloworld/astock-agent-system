from __future__ import annotations

import json
from types import SimpleNamespace

from astock_agent_system.cli_enhanced import cmd_datasource_test
from astock_agent_system.config import load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.data.data_agent import build_provider_catalog, normalize_provider_name, provider_supports
from astock_agent_system.data.providers.alpha_vantage_provider import AlphaVantageProvider
from astock_agent_system.data.providers.tushare_provider import TushareProvider
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


def test_online_unknown_stock_falls_back_to_empty_placeholder(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "tushare")
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    data_agent = DataAgent(settings=load_settings())

    bars = data_agent.get_history("000002", days=3)
    financial = data_agent.get_financial("000002")
    quote = data_agent.get_quote("000002")
    diagnostics = data_agent.provider_diagnostics()

    assert bars == []
    assert financial.stock_code == "000002"
    assert financial.market_cap == 0.0
    assert quote.stock_code == "000002"
    assert quote.price == 0.0
    assert any(item["source"] == "offline" and item["operation"] == "fallback" for item in diagnostics["attempts"])


def test_tushare_financial_handles_series_like_rows_without_truth_check():
    class _FakeRow:
        def __init__(self, data: dict[str, object]) -> None:
            self.data = data

        def __getitem__(self, key: str) -> object:
            return self.data[key]

        def get(self, key: str, default: object = None) -> object:
            return self.data.get(key, default)

        def to_dict(self) -> dict[str, object]:
            return dict(self.data)

        def __bool__(self) -> bool:
            raise AssertionError("row truthiness must not be evaluated")

    class _FakeIloc:
        def __init__(self, rows: list[_FakeRow]) -> None:
            self.rows = rows

        def __getitem__(self, index: int) -> _FakeRow:
            return self.rows[index]

    class _FakeFrame:
        def __init__(self, rows: list[_FakeRow]) -> None:
            self.empty = not rows
            self.iloc = _FakeIloc(rows)

    calls: dict[str, dict[str, object]] = {}

    def _daily_basic(**kwargs: object) -> _FakeFrame:
        calls["daily_basic"] = dict(kwargs)
        return _FakeFrame(
            [
                _FakeRow(
                    {
                        "trade_date": "20260601",
                        "pe_ttm": "12.3",
                        "pb": "1.4",
                        "total_mv": "1000",
                    }
                )
            ]
        )

    def _fina_indicator(**kwargs: object) -> _FakeFrame:
        calls["fina_indicator"] = dict(kwargs)
        return _FakeFrame(
            [
                _FakeRow(
                    {
                        "roe": "9.5",
                        "debt_to_assets": "42.0",
                        "q_profit_yoy": "6.0",
                        "q_sales_yoy": "7.0",
                    }
                )
            ]
        )

    provider = TushareProvider(token="dummy-token")
    provider._api = SimpleNamespace(daily_basic=_daily_basic, fina_indicator=_fina_indicator)

    snapshot = provider.get_financial("000001")

    assert calls["daily_basic"]["start_date"]
    assert calls["daily_basic"]["end_date"]
    assert snapshot.stock_code == "000001"
    assert snapshot.pe_ttm == 12.3
    assert snapshot.roe == 9.5
    assert snapshot.market_cap == 10000000.0


def test_datasource_smoke_command_classifies_skipped_sources(monkeypatch, capsys):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "tushare,ths_skill")
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("LLM_API_KEY", "")

    exit_code = cmd_datasource_test(
        SimpleNamespace(config=None, sources="tushare,ths_skill", all=False, stock_code="600519", days=5, format="json")
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert any(item["source"] == "tushare" and item["status"] == "skipped" for item in payload["items"])
    assert any(item["source"] == "ths_skill" and item["status"] == "skipped" for item in payload["items"])


def test_datasource_smoke_does_not_count_offline_fallback_as_source_success(monkeypatch, capsys):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "baostock")
    monkeypatch.setenv("LLM_API_KEY", "")

    class _FailingBaostockProvider:
        def get_history(self, stock_code: str, days: int = 30, **_: object) -> list[StockBar]:
            raise RuntimeError(f"simulated provider outage for {stock_code}, days={days}")

    import astock_agent_system.data.providers as providers

    monkeypatch.setattr(providers, "BaostockProvider", _FailingBaostockProvider)

    exit_code = cmd_datasource_test(
        SimpleNamespace(
            config=None,
            sources="baostock",
            all=False,
            stock_code="600519",
            days=5,
            checks="history",
            include_universe=False,
            format="json",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    item = payload["items"][0]

    assert exit_code == 1
    assert item["source"] == "baostock"
    assert item["status"] == "error"
    assert item["checks"][0]["status"] == "error"
    assert "simulated provider outage" in item["checks"][0]["detail"]
