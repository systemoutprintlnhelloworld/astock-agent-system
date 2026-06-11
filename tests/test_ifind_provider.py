from __future__ import annotations

from astock_agent_system.data.providers.ifind_provider import _to_ifind_code


def test_ifind_code_normalizes_common_a_share_formats() -> None:
    assert _to_ifind_code("600519") == "600519.SH"
    assert _to_ifind_code("SH600519") == "600519.SH"
    assert _to_ifind_code("600519.SS") == "600519.SH"
    assert _to_ifind_code("000001") == "000001.SZ"
    assert _to_ifind_code("SZ000001") == "000001.SZ"
    assert _to_ifind_code("000001.XSHE") == "000001.SZ"
    assert _to_ifind_code("430047") == "430047.BJ"
