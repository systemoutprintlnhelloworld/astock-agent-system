from __future__ import annotations

from astock_agent_system.ui.streamlit_app import _watch_opportunity_rows, _watch_position_rows, _watch_ranking_rows


def test_watch_ranking_rows_show_idempotent_skip_status():
    rows = _watch_ranking_rows(
        [
            {
                "rank": 1,
                "llm_model": "gpt-5.4-mini",
                "total_return": 0.0123,
                "equity": 101230,
                "cash": 90000,
                "daily_pnl": 0,
                "skipped_execution": True,
                "skip_reason": "already_ran_for_trade_date",
            }
        ]
    )

    assert rows == [
        {
            "排名": 1,
            "模型": "gpt-5.4-mini",
            "总收益": "1.23%",
            "账户权益": "¥101,230",
            "现金": "¥90,000",
            "当日盈亏": "¥0",
            "执行状态": "已跳过",
            "说明": "同一交易日已运行过，已自动防止重复交易",
        }
    ]


def test_watch_position_rows_include_hidden_raw_pnl_for_metrics():
    rows = _watch_position_rows(
        [
            {
                "llm_model": "codex-auto-review",
                "positions": [
                    {
                        "stock_code": "600036",
                        "shares": 200,
                        "cost_basis": 43.5435,
                        "current_price": 43.5,
                        "market_value": 8700,
                        "unrealized_pnl": -8.7,
                        "unrealized_return": -0.000999,
                        "last_buy_date": "2026-06-03",
                    }
                ],
            }
        ]
    )

    assert rows[0]["模型"] == "codex-auto-review"
    assert rows[0]["股票"] == "600036"
    assert rows[0]["浮动盈亏"] == "¥-9"
    assert rows[0]["浮动收益"] == "-0.10%"
    assert rows[0]["floating_pnl_raw"] == -8.7


def test_watch_opportunity_rows_surface_sentiment_and_risk():
    rows = _watch_opportunity_rows(
        [
            {
                "stock": {"stock_code": "600036", "stock_name": "招商银行", "sector": "银行"},
                "quote": {"price": 43.5, "change_pct": 0.015},
                "decision": {
                    "action": "BUY",
                    "confidence": 0.8,
                    "position_size": 0.06,
                    "reasons": ["多维评分达到买入阈值", "估值相对不高"],
                    "risk_notes": ["舆情偏中性"],
                },
                "sentiment": {"score": 0.5},
                "risk": {"score": 0.83},
            }
        ]
    )

    assert rows[0]["股票"] == "招商银行（600036）｜银行"
    assert rows[0]["动作"] == "模拟买入"
    assert rows[0]["系统把握"] == "80.00%"
    assert rows[0]["舆情评分"] == "50.00%"
    assert rows[0]["风控评分"] == "83.00%"
    assert rows[0]["主要理由"] == "多维评分达到买入阈值; 估值相对不高"
    assert rows[0]["主要风险"] == "舆情偏中性"
