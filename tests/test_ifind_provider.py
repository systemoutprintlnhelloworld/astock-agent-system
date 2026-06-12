from __future__ import annotations

from astock_agent_system.data.providers.ifind_provider import (
    _bars_from_history_payload,
    _candidate_ifind_codes,
    _history_request_variants,
    _rows_from_payload,
    _to_ifind_code,
)


def test_ifind_code_normalizes_common_a_share_formats() -> None:
    assert _to_ifind_code("600519") == "600519.SH"
    assert _to_ifind_code("SH600519") == "600519.SH"
    assert _to_ifind_code("600519.SS") == "600519.SH"
    assert _to_ifind_code("000001") == "000001.SZ"
    assert _to_ifind_code("SZ000001") == "000001.SZ"
    assert _to_ifind_code("000001.XSHE") == "000001.SZ"
    assert _to_ifind_code("430047") == "430047.BJ"


def test_ifind_history_variants_try_raw_and_minimal_indicators() -> None:
    codes = _candidate_ifind_codes("600519")
    variants = _history_request_variants("600519")

    assert codes[:2] == ["600519.SH", "600519"]
    assert "SH600519" in codes
    assert ("600519.SH", "open,high,low,close,volume,amount") in variants
    assert ("600519.SH", "open,high,low,close") in variants
    assert ("600519", "open,high,low,close") in variants


def test_ifind_history_parser_attaches_table_times() -> None:
    payload = {
        "errorcode": 0,
        "tables": [
            {
                "thscode": "600519.SH",
                "time": ["2026-06-01", "2026-06-02"],
                "table": {
                    "open": [100.0, 101.0],
                    "high": [102.0, 103.0],
                    "low": [99.0, 100.0],
                    "close": [101.0, 102.0],
                    "volume": [10.0, 11.0],
                    "amount": [1000.0, 1100.0],
                },
            }
        ],
    }

    rows = _rows_from_payload(payload)
    bars = _bars_from_history_payload(payload, stock_code="600519")

    assert rows[0]["time"] == "2026-06-01"
    assert rows[1]["time"] == "2026-06-02"
    assert rows[0]["thscode"] == "600519.SH"
    assert [bar.date for bar in bars] == ["2026-06-01", "2026-06-02"]
    assert bars[1].close == 102.0
