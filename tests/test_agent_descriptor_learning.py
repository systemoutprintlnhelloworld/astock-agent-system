from __future__ import annotations

import json
from datetime import datetime
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
    load_learning_suggestions,
    trigger_learning_if_ready,
)
from astock_agent_system.agents import TechnicalAnalyst
from astock_agent_system.models import StockBar
from apps.tui.backend_client import BackendClientError
from apps.tui.commands import handle_agent_command, handle_slash_command
from apps.tui.config_wizard import build_config_patch, redact_config_patch, render_wizard_summary
from apps.tui.prompt import SlashCommandCompleter
from apps.tui.session import TuiSessionState, extract_file_paths
from apps.tui.widgets import render_agent_management_panel, render_learning_progress, render_provider_diagnostics, render_status_bar
from prompt_toolkit.document import Document


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
    assert load_learning_suggestions(suggestions_path)["suggestions"]
    assert "学习分析" in evolution_path.read_text(encoding="utf-8")


def test_append_experience_serializes_datetime_values(tmp_path: Path) -> None:
    log_path = tmp_path / "experience.jsonl"

    append_experience(
        {
            "date": "2026-06-09",
            "stock_code": "600519",
            "agent_outputs": {"decision": {"timestamp": datetime(2026, 6, 9, 10, 30)}} ,
            "outcome": {"return_pct": 0.0},
        },
        path=log_path,
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["agent_outputs"]["decision"]["timestamp"].startswith("2026-06-09 10:30")


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


class _FakeTuiBackend:
    def __init__(self) -> None:
        self.started: dict[str, object] = {}

    def health(self) -> dict[str, object]:
        return {"status": "ok", "app": "fake"}

    def config(self) -> dict[str, object]:
        return {"status": "ok", "config": {"data": {"mode": "offline"}}}

    def save_config(self, config: dict[str, object]) -> dict[str, object]:
        return {"status": "ok", "config": config}

    def test_llm(self, config: dict[str, object] | None = None, *, run_bench: bool = False) -> dict[str, object]:
        return {"configured": False, "run_bench": run_bench}

    def list_models(self) -> dict[str, object]:
        return {"status": "ok", "models": ["rule-baseline", "gpt-demo"]}

    def start_auto_investment(
        self,
        *,
        models: list[str] | None = None,
        offline: bool = False,
        max_count: int | None = None,
        days: int | None = None,
        background: bool = True,
    ) -> dict[str, object]:
        self.started = {
            "models": models,
            "offline": offline,
            "max_count": max_count,
            "days": days,
            "background": background,
        }
        return {"status": "accepted", "run_id": "run-1"}

    def run_status(self) -> dict[str, object]:
        return {"status": "idle", "run": None}

    def decisions(self) -> dict[str, object]:
        return {"items": []}

    def stock_board(self) -> dict[str, object]:
        return {"holdings": [], "candidates": [], "trades": []}

    def rankings(self) -> dict[str, object]:
        return {"rankings": [{"rank": 1, "llm_model": "rule-baseline", "total_return": 0.01, "equity": 101000, "total_trades": 1}]}

    def data_providers(self) -> dict[str, object]:
        return {
            "diagnostics": {
                "mode": "offline",
                "provider_chain": ["tushare", "baostock", "akshare"],
                "catalog": [
                    {
                        "source": "akshare",
                        "configured": True,
                        "adapter_available": True,
                        "has_credentials": True,
                        "missing_credentials": [],
                        "capabilities": ["history", "quote"],
                        "suitability": "免费综合兜底源。",
                    }
                ],
                "attempts": [],
            }
        }

    def agent_flow(self) -> dict[str, object]:
        return {"nodes": [], "edges": []}

    def learning_status(self) -> dict[str, object]:
        return {"learning": {"threshold": 30, "progress": 1, "total_experiences": 1}}


def test_tui_slash_commands_update_state_and_call_backend() -> None:
    state = TuiSessionState()
    client = _FakeTuiBackend()

    model_result = handle_slash_command("/models set rule-baseline,gpt-demo", state=state, client=client)
    workflow_result = handle_slash_command("/workflow offline", state=state, client=client)
    start_result = handle_slash_command("/start --max-count 2 --days 12", state=state, client=client)
    providers_result = handle_slash_command("/providers", state=state, client=client)
    run_result = handle_slash_command("/run", state=state, client=client)
    dashboard_result = handle_slash_command("/dashboard", state=state, client=client)

    assert model_result.ok is True
    assert workflow_result.ok is True
    assert start_result.ok is True
    assert providers_result.ok is True
    assert run_result.ok is True
    assert dashboard_result.ok is True
    assert state.selected_models == ["rule-baseline", "gpt-demo"]
    assert client.started == {
        "models": ["rule-baseline", "gpt-demo"],
        "offline": True,
        "max_count": 2,
        "days": 12,
        "background": True,
    }
    assert state.last_run_id == "run-1"
    assert state.active_tab == "trading"
    assert "运行观测" in start_result.body
    assert "run_id: run-1" in start_result.body
    assert "运行观测" in run_result.body
    assert dashboard_result.title == "交易看板"
    assert "akshare" in providers_result.body


def test_tui_models_list_updates_available_models_for_completion() -> None:
    state = TuiSessionState()
    client = _FakeTuiBackend()

    result = handle_slash_command("/models list", state=state, client=client)
    completions = list(SlashCommandCompleter(state.available_models).get_completions(Document("/models set g"), None))

    assert result.ok is True
    assert state.available_models == ["rule-baseline", "gpt-demo"]
    assert "当前比赛模型" in result.body
    assert any(completion.text == "gpt-demo" and "后端模型列表" in str(completion.display_meta) for completion in completions)


def test_tui_slash_command_palette_shows_descriptions() -> None:
    completions = list(SlashCommandCompleter(["gpt-demo"]).get_completions(Document("/"), None))
    subcommands = list(SlashCommandCompleter(["gpt-demo"]).get_completions(Document("/dashboard "), None))

    assert any(completion.text == "/dashboard" and "交易看板" in str(completion.display_meta) for completion in completions)
    assert any(completion.text == "trading" and "默认" in str(completion.display_meta) for completion in subcommands)


class _FailingTuiBackend(_FakeTuiBackend):
    def config(self) -> dict[str, object]:
        raise BackendClientError("config unavailable")

    def start_auto_investment(
        self,
        *,
        models: list[str] | None = None,
        offline: bool = False,
        max_count: int | None = None,
        days: int | None = None,
        background: bool = True,
    ) -> dict[str, object]:
        raise BackendClientError("start unavailable")

    def data_providers(self) -> dict[str, object]:
        raise BackendClientError("providers unavailable")


def test_tui_slash_commands_keep_todo_state_consistent_on_backend_failure() -> None:
    state = TuiSessionState()
    client = _FailingTuiBackend()

    config_result = handle_slash_command("/config show", state=state, client=client)
    providers_result = handle_slash_command("/providers", state=state, client=client)
    start_result = handle_slash_command("/start --offline", state=state, client=client)

    assert config_result.ok is False
    assert providers_result.ok is False
    assert start_result.ok is False
    assert state.todo_status.get("配置") != "completed"
    assert state.todo_status.get("数据源") != "completed"
    assert state.todo_status["运行"] == "failed"


def test_tui_config_wizard_redacts_secret_values() -> None:
    patch = build_config_patch(
        {
            "data_mode": "online",
            "provider_chain": "tushare,baostock,akshare,yfinance,alpha-vantage,jqdata",
            "tushare_token": "local-secret-token",
            "llm_api_key": "local-llm-key",
            "scheduler_models": "rule-baseline,gpt-demo",
        }
    )
    redacted = redact_config_patch(patch)
    render_wizard_summary(patch)

    assert patch["data"]["provider_chain"][-1] == "jqdata"
    assert redacted["data"]["tushare_token"] == "[已设置]"
    assert redacted["llm"]["api_key"] == "[已设置]"
    assert "local-secret-token" not in str(redacted)
    assert "local-llm-key" not in str(redacted)


def test_tui_config_wizard_accepts_selected_provider_list_without_scheduler_models() -> None:
    patch = build_config_patch(
        {
            "data_mode": "online",
            "provider_chain": ["tushare", "baostock", "akshare", "adata"],
            "llm_default_model": "gpt-5.5",
            "scheduler_models": ["rule-baseline", "gpt-5.5"],
        }
    )

    assert patch["data"]["provider_chain"] == ["tushare", "baostock", "akshare", "adata"]
    assert patch["llm"]["default_model"] == "gpt-5.5"
    assert "models" not in patch.get("scheduler", {})


def test_agent_learning_short_alias_matches_command_palette() -> None:
    result = handle_agent_command("/agent stats")

    assert result.ok is True
    assert result.title == "Agent 学习状态"
    assert "学习进度" in result.body


def test_tui_context_meter_and_file_path_extraction(tmp_path: Path) -> None:
    attachment = tmp_path / "note.txt"
    attachment.write_text("hello", encoding="utf-8")
    state = TuiSessionState(context_limit_tokens=20, auto_compact_threshold=0.5)

    paths = state.add_user_input(f"请读取 {attachment}")
    for index in range(12):
        state.add_message("assistant", f"message {index} " * 8)

    assert str(attachment.resolve()) in paths
    assert extract_file_paths(f'"{attachment}"') == [str(attachment.resolve())]
    assert state.compacted_count > 0
    assert "上下文" in render_status_bar(state, {"status": "idle"})


def test_tui_provider_diagnostics_renderer() -> None:
    text = render_provider_diagnostics(_FakeTuiBackend().data_providers())

    assert "数据源诊断" in text
    assert "tushare, baostock, akshare" in text
    assert "akshare" in text
