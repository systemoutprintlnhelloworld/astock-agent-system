"""Offline smoke test for the A-share Agent MVP.

This script intentionally avoids external providers and can run without pytest.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

os.environ["DATA_MODE"] = "offline"
os.environ["SMART_SEARCH_ENABLED"] = "false"
os.environ["LLM_API_KEY"] = ""

from astock_agent_system.agents import MasterAgent, StockScreener  # noqa: E402
from astock_agent_system.backtest import BacktestEngine  # noqa: E402
from astock_agent_system.config import load_settings  # noqa: E402
from astock_agent_system.data import DataAgent  # noqa: E402
from astock_agent_system.llm import ModelBench  # noqa: E402
from astock_agent_system.notification import build_notifier  # noqa: E402


def main() -> int:
    settings = load_settings()
    data_agent = DataAgent(settings=settings)
    universe = data_agent.get_universe()
    assert len(universe) >= 3, "offline universe should include at least 3 stocks"
    assert len(data_agent.get_history(universe[0].stock_code)) >= 20, "sample history is too short"

    screened = StockScreener(data_agent=data_agent).screen(max_count=3)
    assert len(screened) == 3, "screening should return 3 candidates"

    report = MasterAgent(settings=settings, data_agent=data_agent).analyze_stock(universe[0].stock_code)
    assert report.decision is not None, "single-stock analysis should produce a decision"

    backtest = BacktestEngine(settings=settings, data_agent=data_agent).run(max_count=2, initial_capital=100000)
    assert backtest.status == "ok", "backtest should complete in offline mode"
    assert backtest.equity_curve, "backtest should produce an equity curve"

    bench = ModelBench().run(models=["offline-skip"], limit=1)
    assert bench["status"] == "skipped", "LLM bench should skip without API key"

    notification = build_notifier(settings).send("smoke", "test")
    assert notification[0].status == "skipped", "notification should skip when unconfigured"

    print(
        json.dumps(
            {
                "status": "ok",
                "universe_count": len(universe),
                "screened_count": len(screened),
                "decision": report.decision.to_dict(),
                "backtest_total_return": backtest.total_return,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
