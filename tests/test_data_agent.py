from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace

from astock_agent_system.cli_enhanced import cmd_datasource_sync_local, cmd_datasource_test
from astock_agent_system.config import load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.data.data_agent import build_provider_catalog, normalize_provider_name, provider_supports
from astock_agent_system.data.local_store import LocalMarketStore
from astock_agent_system.data.providers.alpha_vantage_provider import AlphaVantageProvider
from astock_agent_system.data.providers.baostock_provider import BaostockProvider, _is_supported_a_share_stock_code
from astock_agent_system.data.providers.tushare_provider import TushareProvider
from astock_agent_system.models import FinancialSnapshot, StockBar, StockIdentity, StockQuote


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


def test_local_market_store_roundtrip(tmp_path):
    store = LocalMarketStore(path=tmp_path / "market.sqlite")
    stocks = [
        StockIdentity(stock_code="000001", stock_name="平安银行", sector="银行"),
        StockIdentity(stock_code="600519", stock_name="贵州茅台", sector="白酒"),
    ]
    bars = [
        StockBar(stock_code="000001", date="2026-06-01", open=10.0, high=10.5, low=9.8, close=10.2, volume=100.0, amount=1020.0),
        StockBar(stock_code="000001", date="2026-06-02", open=10.2, high=10.8, low=10.1, close=10.6, volume=120.0, amount=1272.0),
        StockBar(stock_code="000001", date="2026-06-03", open=10.6, high=11.0, low=10.4, close=10.9, volume=130.0, amount=1417.0),
    ]
    quote = StockQuote(
        stock_code="000001",
        stock_name="平安银行",
        date="2026-06-03",
        price=10.9,
        change_pct=0.0283,
        volume=130.0,
        amount=1417.0,
        sector="银行",
    )
    financial = FinancialSnapshot(
        stock_code="000001",
        stock_name="平安银行",
        report_date="2026-03-31",
        pe_ttm=5.2,
        pb=0.62,
        roe=0.11,
        debt_ratio=0.9,
        revenue_growth=0.04,
        profit_growth=0.06,
        market_cap=2000.0,
        sector="银行",
    )

    assert store.upsert_universe(stocks) == 2
    assert store.upsert_history("000001", bars, source="unit") == 3
    assert store.upsert_quote(quote, source="unit") == 1
    assert store.upsert_financial(financial, source="unit") == 1
    store.record_sync(source="unit", operation="history", stock_code="000001", status="ok", detail="3 bars")

    assert [stock.stock_code for stock in store.get_universe(limit=1)] == ["000001"]
    assert [bar.date for bar in store.get_history("000001", days=2)] == ["2026-06-02", "2026-06-03"]
    assert store.get_quote("000001").price == 10.9
    assert store.get_financial("000001").pe_ttm == 5.2
    stats = store.stats()
    assert stats["stocks"] == 2
    assert stats["bars"] == 3
    assert stats["quotes"] == 1
    assert stats["financials"] == 1
    assert stats["sync_runs"] == 1
    coverage = store.coverage_summary(stock_limit=5, date_limit=5)
    assert coverage["stock_count"] == 2
    assert coverage["bars_stock_count"] == 1
    assert coverage["bar_count"] == 3
    assert coverage["first_date"] == "2026-06-01"
    assert coverage["last_date"] == "2026-06-03"
    assert coverage["recent_dates"][-1]["date"] == "2026-06-03"
    assert coverage["top_stocks"][0]["stock_code"] == "000001"
    assert coverage["sector_coverage"]


def test_data_agent_reads_local_market_store_first(monkeypatch, tmp_path):
    db_path = tmp_path / "market.sqlite"
    store = LocalMarketStore(path=db_path)
    store.upsert_universe([StockIdentity(stock_code="000001", stock_name="平安银行", sector="银行")])
    store.upsert_history(
        "000001",
        [
            StockBar(stock_code="000001", date="2026-06-01", open=10.0, high=10.5, low=9.8, close=10.2, volume=100.0, amount=1020.0),
            StockBar(stock_code="000001", date="2026-06-02", open=10.2, high=10.8, low=10.1, close=10.6, volume=120.0, amount=1272.0),
        ],
        source="unit",
    )
    store.upsert_quote(
        StockQuote(
            stock_code="000001",
            stock_name="平安银行",
            date="2026-06-02",
            price=10.6,
            change_pct=0.0392,
            volume=120.0,
            amount=1272.0,
            sector="银行",
        ),
        source="unit",
    )
    store.upsert_financial(
        FinancialSnapshot(
            stock_code="000001",
            stock_name="平安银行",
            report_date="2026-03-31",
            pe_ttm=5.2,
            pb=0.62,
            roe=0.11,
            debt_ratio=0.9,
            revenue_growth=0.04,
            profit_growth=0.06,
            market_cap=2000.0,
            sector="银行",
        ),
        source="unit",
    )
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "baostock")
    monkeypatch.setenv("ASTOCK_MARKET_LOCAL_DB", str(db_path))
    monkeypatch.setenv("LLM_API_KEY", "")

    data_agent = DataAgent(settings=load_settings(), local_store_path=db_path)

    assert data_agent.get_universe()[0].stock_code == "000001"
    assert data_agent.get_history("000001", days=1)[0].close == 10.6
    assert data_agent.get_quote("000001").price == 10.6
    assert data_agent.get_financial("000001").market_cap == 2000.0
    diagnostics = data_agent.provider_diagnostics()
    assert diagnostics["local_market"]["exists"] is True
    assert any(item["source"] == "local_market" and item["operation"] == "history" for item in diagnostics["attempts"])


def test_datasource_sync_local_writes_provider_results(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "baostock")
    monkeypatch.setenv("LLM_API_KEY", "")

    class _FakeBaostockProvider:
        def get_universe(self, limit: int | None = None) -> list[StockIdentity]:
            stocks = [StockIdentity(stock_code="000001", stock_name="平安银行", sector="银行")]
            return stocks[:limit] if limit else stocks

        def get_history(self, stock_code: str, days: int = 30, **_: object) -> list[StockBar]:
            return [
                StockBar(stock_code=stock_code, date="2026-06-01", open=10.0, high=10.5, low=9.8, close=10.2, volume=100.0, amount=1020.0),
                StockBar(stock_code=stock_code, date="2026-06-02", open=10.2, high=10.8, low=10.1, close=10.6, volume=120.0, amount=1272.0),
            ][-days:]

        def get_quote(self, stock_code: str) -> StockQuote:
            return StockQuote(
                stock_code=stock_code,
                stock_name="平安银行",
                date="2026-06-02",
                price=10.6,
                change_pct=0.0392,
                volume=120.0,
                amount=1272.0,
                sector="银行",
            )

        def get_financial(self, stock_code: str) -> FinancialSnapshot:
            return FinancialSnapshot(
                stock_code=stock_code,
                stock_name="平安银行",
                report_date="2026-03-31",
                pe_ttm=5.2,
                pb=0.62,
                roe=0.11,
                debt_ratio=0.9,
                revenue_growth=0.04,
                profit_growth=0.06,
                market_cap=2000.0,
                sector="银行",
            )

    import astock_agent_system.data.providers as providers

    monkeypatch.setattr(providers, "BaostockProvider", _FakeBaostockProvider)
    db_path = tmp_path / "market.sqlite"

    exit_code = cmd_datasource_sync_local(
        SimpleNamespace(
            config=None,
            sources="baostock",
            stock_codes="",
            max_stocks=1,
            days=2,
            checks="universe,history,quote,financial",
            db_path=str(db_path),
            format="json",
        )
    )
    payload = json.loads(capsys.readouterr().out)
    store = LocalMarketStore(path=db_path)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["provider_chain"] == ["baostock"]
    assert any(item["operation"] == "universe" and item["source"] == "baostock" for item in payload["items"])
    assert [stock.stock_code for stock in store.get_universe()] == ["000001"]
    assert len(store.get_history("000001", days=5)) == 2
    assert store.get_quote("000001").price == 10.6
    assert store.get_financial("000001").market_cap == 2000.0


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
    assert provider_supports("baostock", "financial") is True
    assert provider_supports("jqdata", "financial") is True
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


def test_baostock_login_stdout_is_suppressed(monkeypatch, capsys):
    def _login() -> SimpleNamespace:
        print("login success!")
        return SimpleNamespace(error_code="0", error_msg="")

    monkeypatch.setitem(sys.modules, "baostock", SimpleNamespace(login=_login))

    provider = BaostockProvider()
    provider._get_bs()

    assert capsys.readouterr().out == ""


def test_baostock_universe_filters_indexes_and_inactive_rows(monkeypatch):
    class _FakeResult:
        error_code = "0"
        error_msg = ""

        def __init__(self, rows: list[list[str]]) -> None:
            self.rows = rows
            self.index = -1

        def next(self) -> bool:
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self) -> list[str]:
            return self.rows[self.index]

    def _login() -> SimpleNamespace:
        return SimpleNamespace(error_code="0", error_msg="")

    def _query_stock_basic() -> _FakeResult:
        return _FakeResult(
            [
                ["sh.000003", "上证指数样例", "", "", "2", "1"],
                ["sz.000004", "退市样例", "", "", "1", "0"],
                ["sz.000001", "平安银行", "", "", "1", "1"],
                ["sh.600519", "贵州茅台", "", "", "1", "1"],
            ]
        )

    monkeypatch.setitem(sys.modules, "baostock", SimpleNamespace(login=_login, query_stock_basic=_query_stock_basic))

    provider = BaostockProvider()
    stocks = provider.get_universe(limit=10)

    assert [stock.stock_code for stock in stocks] == ["000001", "600519"]
    assert _is_supported_a_share_stock_code("000003", "sh.000003") is False
    assert _is_supported_a_share_stock_code("600519", "sh.600519") is True


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


def test_provider_error_cooldown_skips_repeated_failed_operation(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "akshare")
    monkeypatch.setenv("LLM_API_KEY", "")

    class _FailingAkshareProvider:
        calls = 0

        def get_financial(self, stock_code: str):
            type(self).calls += 1
            raise RuntimeError(f"Connection aborted for {stock_code}")

    import astock_agent_system.data.providers as providers

    monkeypatch.setattr(providers, "AkShareProvider", _FailingAkshareProvider)
    data_agent = DataAgent(settings=load_settings())

    first = data_agent.get_financial("600519")
    second = data_agent.get_financial("000333")
    diagnostics = data_agent.provider_diagnostics()

    assert first.stock_code == "600519"
    assert second.stock_code == "000333"
    assert _FailingAkshareProvider.calls == 1
    assert any(
        item["source"] == "akshare" and item["operation"] == "financial" and item["status"] == "skipped"
        for item in diagnostics["attempts"]
    )


def test_provider_rate_limit_sets_sourcewide_cooldown(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "tushare")
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    monkeypatch.setenv("LLM_API_KEY", "")

    class _RateLimitedTushareProvider:
        history_calls = 0
        quote_calls = 0

        def __init__(self, token: str | None = None) -> None:
            self.token = token

        def get_history(self, stock_code: str, days: int = 30, **_: object) -> list[StockBar]:
            type(self).history_calls += 1
            raise RuntimeError("抱歉，您访问接口(daily_basic)频率超限(1次/小时)")

        def get_quote(self, stock_code: str):
            type(self).quote_calls += 1
            raise RuntimeError("quote should be skipped after rate limit")

    import astock_agent_system.data.providers as providers

    monkeypatch.setattr(providers, "TushareProvider", _RateLimitedTushareProvider)
    data_agent = DataAgent(settings=load_settings())

    bars = data_agent.get_history("600519", days=3)
    quote = data_agent.get_quote("600519")
    diagnostics = data_agent.provider_diagnostics()

    assert len(bars) == 3
    assert quote.price > 0
    assert _RateLimitedTushareProvider.history_calls == 1
    assert _RateLimitedTushareProvider.quote_calls == 0
    assert any(item["source"] == "tushare" for item in diagnostics["global_cooldowns"])
    assert any(
        item["source"] == "tushare" and item["operation"] == "quote" and item["status"] == "skipped"
        for item in diagnostics["attempts"]
    )


def test_provider_call_timeout_falls_back_without_hanging(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "online")
    monkeypatch.setenv("DATA_PROVIDER_CHAIN", "akshare")
    monkeypatch.setenv("DATA_PROVIDER_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("LLM_API_KEY", "")

    class _HungAkshareProvider:
        calls = 0

        def get_history(self, stock_code: str, days: int = 30, **_: object) -> list[StockBar]:
            type(self).calls += 1
            time.sleep(5)
            return []

    import astock_agent_system.data.providers as providers

    monkeypatch.setattr(providers, "AkShareProvider", _HungAkshareProvider)
    data_agent = DataAgent(settings=load_settings())

    started = time.perf_counter()
    bars = data_agent.get_history("600519", days=3)
    elapsed = time.perf_counter() - started
    diagnostics = data_agent.provider_diagnostics()

    assert len(bars) == 3
    assert elapsed < 1.0
    assert _HungAkshareProvider.calls == 1
    assert any(
        item["source"] == "akshare" and item["operation"] == "history" and item["status"] == "error"
        and "exceeded" in item["detail"]
        for item in diagnostics["attempts"]
    )
