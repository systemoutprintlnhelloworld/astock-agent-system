from __future__ import annotations

import json
from pathlib import Path

from astock_agent_system.agent_descriptor import (
    backup_agent_descriptor,
    load_agent_descriptor,
    load_user_profile,
    rollback_agent_descriptor,
)
from astock_agent_system.agent_learning import (
    append_experience,
    get_learning_status,
    trigger_learning_if_ready,
)
from astock_agent_system.agents import TechnicalAnalyst
from astock_agent_system.models import StockBar
from apps.tui.commands import handle_agent_command
from apps.tui.widgets import render_agent_management_panel, render_learning_progress


def test_agent_descriptor_renders_prompt_with_user_profile() -> None:
    descriptor = load_agent_descriptor("sentiment")

    rendered = descriptor.render_prompt(
        {
            "stock_code": "600000",
            "text": "公司订单增长",
            "learning_context": "近期高杠杆股票表现较差。",
        }
    )

    assert descriptor.agent_id == "sentiment_analyst"
    assert "600000" in rendered
    assert "moderate" in rendered
    assert "近期高杠杆股票表现较差" in rendered


def test_user_profile_loads_non_secret_preferences() -> None:
    profile = load_user_profile()

    assert profile.risk_preference in {"conservative", "moderate", "aggressive"}
    assert "technical_momentum" in profile.focus_areas


def test_technical_analyst_uses_descriptor_version_metadata() -> None:
    bars = [
        StockBar("600000", f"2026-01-{day:02d}", 10, 11, 9, 10 + day * 0.1, 1000, 100000)
        for day in range(1, 25)
    ]

    result = TechnicalAnalyst().analyze("600000", bars)

    assert result.score > 0
    assert result.metadata["agent_descriptor_version"] == "v1.0.0"


def test_agent_descriptor_backup_and_rollback_use_local_directory(tmp_path: Path) -> None:
    source = Path("config/agents/technical_analyst.md")
    work_dir = tmp_path / "agents"
    work_dir.mkdir()
    target = work_dir / "technical_analyst.md"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    backup = backup_agent_descriptor("technical", directory=work_dir)
    target.write_text(target.read_text(encoding="utf-8") + "\n<!-- changed -->\n", encoding="utf-8")

    restored = rollback_agent_descriptor("technical", backup.name, directory=work_dir)

    assert restored == target
    assert "<!-- changed -->" not in target.read_text(encoding="utf-8")


def test_learning_status_and_trigger_use_temp_files(tmp_path: Path) -> None:
    log_path = tmp_path / "experience.jsonl"
    state_path = tmp_path / "state.json"
    suggestions_path = tmp_path / "suggestions.json"
    evolution_path = tmp_path / "evolution.md"

    for index in range(3):
        append_experience(
            {
                "date": "2026-06-07",
                "stock_code": f"60000{index}",
                "agent_outputs": {"decision": {"reasons": ["MA5 高于 MA20", "RSI14 健康"]}},
                "outcome": {"return_pct": 1.2 if index % 2 == 0 else -0.5},
            },
            path=log_path,
        )

    status = get_learning_status(path=log_path, state_path=state_path, threshold=3)
    assert status["ready"] is True
    assert status["progress"] == 3

    triggered = trigger_learning_if_ready(
        path=log_path,
        state_path=state_path,
        suggestions_path=suggestions_path,
        evolution_path=evolution_path,
        threshold=3,
    )

    assert triggered["suggestions"]
    assert json.loads(suggestions_path.read_text(encoding="utf-8"))["analyzed_count"] == 3
    assert "学习分析" in evolution_path.read_text(encoding="utf-8")


def test_tui_agent_command_and_panel_render() -> None:
    listed = handle_agent_command("/agent list")
    viewed = handle_agent_command("/agent view technical")
    panel = render_agent_management_panel()
    progress = render_learning_progress({"threshold": 30, "progress": 6, "total_experiences": 6, "success_rate": 0.5, "average_return_pct": 1.2})

    assert listed.ok is True
    assert "technical_analyst" in listed.body
    assert viewed.ok is True
    assert "TechnicalAnalyst" in viewed.body
    assert "Agent 管理" in panel
    assert "学习进度" in progress
