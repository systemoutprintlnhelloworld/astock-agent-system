from __future__ import annotations

from astock_agent_system.cli_enhanced import RichEventRenderer
from astock_agent_system.data.providers.iwencai_skillhub import IwencaiSkillHub
from astock_agent_system.events import AgentEvent
from astock_agent_system.models import AnalysisResult


def _plain_renderer() -> RichEventRenderer:
    renderer = RichEventRenderer()
    renderer.rich = False
    renderer.console = None
    return renderer


def _sample_bars() -> list[dict[str, float | str]]:
    return [
        {"stock_code": "600036", "date": "2026-06-01", "open": 42.0, "high": 43.0, "low": 41.8, "close": 42.5, "volume": 100.0, "amount": 4250.0, "turnover": 0.1},
        {"stock_code": "600036", "date": "2026-06-02", "open": 42.5, "high": 43.5, "low": 42.2, "close": 43.1, "volume": 120.0, "amount": 5172.0, "turnover": 0.1},
        {"stock_code": "600036", "date": "2026-06-03", "open": 43.1, "high": 44.0, "low": 42.9, "close": 43.8, "volume": 130.0, "amount": 5694.0, "turnover": 0.1},
        {"stock_code": "600036", "date": "2026-06-04", "open": 43.8, "high": 44.1, "low": 43.0, "close": 43.4, "volume": 110.0, "amount": 4774.0, "turnover": 0.1},
        {"stock_code": "600036", "date": "2026-06-05", "open": 43.4, "high": 44.5, "low": 43.2, "close": 44.2, "volume": 140.0, "amount": 6188.0, "turnover": 0.1},
    ]


def _sample_financial() -> dict[str, float | str]:
    return {
        "stock_code": "600036",
        "stock_name": "招商银行",
        "report_date": "2026-03-31",
        "pe_ttm": 5.2,
        "pb": 0.8,
        "roe": 0.12,
        "debt_ratio": 0.9,
        "revenue_growth": 0.04,
        "profit_growth": 0.06,
        "market_cap": 10970.0,
        "sector": "金融",
    }


def test_renderer_shows_fine_grained_analysis_event(capsys) -> None:  # noqa: ANN001
    event = AgentEvent(
        type="technical_analysis_complete",
        timestamp="2026-06-11T00:00:00+00:00",
        stage="technical_analyst",
        payload={
            "stock_code": "600036",
            "result": AnalysisResult(
                agent_name="TechnicalAnalyst",
                stock_code="600036",
                score=0.72,
                label="偏强",
                reasons=["收盘价站上短期均线"],
            ),
            "objective_data": {"bars": _sample_bars()},
        },
    )

    _plain_renderer()(event)

    output = capsys.readouterr().out
    assert "技术分析" in output
    assert "score=72.00%" in output
    assert "MA5" in output


def test_renderer_shows_decision_requested_evidence_blocks(capsys) -> None:  # noqa: ANN001
    decision = {
        "stock_code": "600036",
        "action": "BUY",
        "confidence": 0.71,
        "position_size": 0.05,
        "reasons": ["估值低", "技术面偏强"],
        "risk_notes": ["控制单股仓位"],
        "explanation_data": {
            "sections": ["company", "quote", "kline", "technical_indicators", "financial", "sentiment", "agent_chain"],
            "highlights": ["Agent建议展示K线和财务表支撑BUY决策。"],
            "objective_data": {
                "stock": {"stock_code": "600036", "stock_name": "招商银行", "sector": "金融"},
                "quote": {
                    "stock_code": "600036",
                    "stock_name": "招商银行",
                    "date": "2026-06-05",
                    "price": 44.2,
                    "change_pct": 0.018,
                    "volume": 140.0,
                    "amount": 6188.0,
                    "sector": "金融",
                },
                "financial": _sample_financial(),
                "bars": _sample_bars(),
                "news": ["无重大负面新闻"],
            },
            "agent_scores": {"technical": 0.72, "fundamental": 0.8},
            "agent_chain": {
                "technical": {"score": 0.72, "label": "偏强", "reasons": ["收盘价站上短期均线"]},
                "fundamental": {"score": 0.8, "label": "优秀", "reasons": ["PE较低"]},
            },
        },
    }
    event = AgentEvent(
        type="portfolio_decision_complete",
        timestamp="2026-06-11T00:00:00+00:00",
        stage="portfolio_manager",
        payload={"stock_code": "600036", "decision": decision},
    )

    _plain_renderer()(event)

    output = capsys.readouterr().out
    assert "最终决策" in output
    assert "决策客观依据" in output
    assert "公司与行情" in output
    assert "财务与估值" in output
    assert "Agent 分数" in output


def test_renderer_result_summary_shows_account_positions_and_trades(capsys) -> None:  # noqa: ANN001
    payload = {
        "status": "ok",
        "run_date": "2026-06-11",
        "rankings": [{"rank": 1, "llm_model": "gpt-demo", "total_return": 0.0123, "cash": 90000, "equity": 101230}],
        "agents": [
            {
                "llm_model": "gpt-demo",
                "equity": 101230,
                "cash": 90000,
                "total_return": 0.0123,
                "daily_pnl": 1230,
                "buy_count": 1,
                "sell_count": 0,
                "total_trades": 1,
                "positions": [
                    {"stock_code": "600036", "shares": 200, "current_price": 44.2, "market_value": 8840, "unrealized_return": 0.03}
                ],
                "trades": [
                    {"date": "2026-06-11", "stock_code": "600036", "side": "BUY", "price": 44.2, "shares": 200, "realized_pnl": 0}
                ],
            }
        ],
    }

    _plain_renderer().render_result_summary(payload)

    output = capsys.readouterr().out
    assert "账户看板" in output
    assert "当前持仓" in output
    assert "最近交易" in output
    assert "600036" in output


def test_renderer_local_market_status_shows_inventory(capsys) -> None:  # noqa: ANN001
    payload = {
        "db_path": "data/market_local/market.sqlite",
        "provider_chain": ["tushare", "baostock"],
        "local_stats": {"exists": True, "stocks": 3, "bars": 120, "quotes": 3, "financials": 2, "sync_runs": 4, "latest_sync_at": "2026-06-11 10:00:00"},
        "recent_sync_runs": [
            {"created_at": "2026-06-11 10:00:00", "source": "tushare", "operation": "history", "stock_code": "600036", "status": "ok", "detail": "120 bars"}
        ],
    }

    _plain_renderer().render_local_market_status(payload)

    output = capsys.readouterr().out
    assert "本地市场数据状态" in output
    assert "库存统计" in output
    assert "最近同步记录" in output
    assert "tushare" in output


def test_iwencai_skillhub_reports_missing_cli_and_key(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("shutil.which", lambda _: None)

    hub = IwencaiSkillHub(base_url="https://openapi.iwencai.com", api_key="", cli="skillhub")
    status = hub.status()
    result = hub.search_announcements(stock_code="600519", query="公告")

    assert status["status"] == "needs_config"
    assert status["skillhub_found"] is False
    assert status["has_api_key"] is False
    assert result.status == "skipped"
    assert "IWENCAI_API_KEY" in result.reason
    assert result.next_steps
    assert "iwencai-skillhub-cli" in status["install_command"]
    assert any("iwencai-skillhub-cli" in step for step in result.next_steps)
