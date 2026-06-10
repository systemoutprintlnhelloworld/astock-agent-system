"""Enhanced CLI commands for streaming Agent runs and learning visibility."""

from __future__ import annotations

import copy
import getpass
import json
import queue
import threading
import time
from importlib.util import find_spec
from typing import Any

from astock_agent_system.agent_learning import (
    get_learning_status,
    load_experiences,
    load_learning_suggestions,
    trigger_learning_if_ready,
)
from astock_agent_system.agent_memory import AgentMemoryStore
from astock_agent_system.cli_data_viz import (
    render_analysis_result,
    render_company_info,
    render_financial_table,
    render_kline_ascii,
    render_news_list,
    render_technical_indicators,
)
from astock_agent_system.config import load_settings, save_runtime_overrides
from astock_agent_system.data import DataAgent
from astock_agent_system.data.data_agent import PROVIDER_CATALOG, normalize_provider_name, provider_supports
from astock_agent_system.events import AgentEvent, AgentEventEmitter
from astock_agent_system.orchestrator import MultiAgentOrchestrator


def cmd_agent_start(args: Any) -> int:
    """Run one or more model-driven agents with streaming event output."""
    settings = load_settings(args.config)
    if getattr(args, "offline", False):
        settings.data.mode = "offline"
    models = _parse_models(getattr(args, "models", "") or getattr(args, "model", ""))
    emitter = AgentEventEmitter()
    renderer = RichEventRenderer(verbose=bool(getattr(args, "verbose", False)), debug=bool(getattr(args, "debug", False)))
    emitter.subscribe(renderer)

    _render_run_header(renderer, settings, models=models, offline=bool(getattr(args, "offline", False)))
    _emit_datasource_snapshot(emitter, settings)
    timeout_seconds = float(getattr(args, "timeout_seconds", 900.0) or 900.0)
    interval_seconds = max(0.0, float(getattr(args, "interval_minutes", 60.0) or 60.0) * 60.0)
    continuous = bool(getattr(args, "continuous", False))
    max_rounds = int(getattr(args, "max_rounds", 0) or 0)
    round_index = 0
    last_payload: dict[str, Any] | None = None
    try:
        while True:
            round_index += 1
            if continuous:
                renderer.print_info("连续运行", f"第 {round_index} 轮开始；按 Ctrl+C 可安全停止。")
            orchestrator = MultiAgentOrchestrator(settings=settings, event_emitter=emitter)
            payload = _run_with_timeout(
                lambda: orchestrator.run_competition(
                    models=models or None,
                    max_count=int(getattr(args, "max_count", 3)),
                    history_days=int(getattr(args, "days", 24)),
                    initial_capital=getattr(args, "initial_capital", None),
                    persist=not bool(getattr(args, "no_persist", False)),
                    continue_from_storage=not bool(getattr(args, "fresh_start", False)) or round_index > 1,
                    collect_learning=not bool(getattr(args, "no_learning", False)),
                ),
                timeout_seconds=timeout_seconds,
                label="agent run",
            )
            last_payload = payload
            _emit_post_run_visibility(emitter, settings, payload)
            renderer.render_result_summary(payload)
            if not continuous or payload.get("status") != "ok":
                break
            if max_rounds > 0 and round_index >= max_rounds:
                renderer.print_info("连续运行", f"已完成 --max-rounds={max_rounds}，自动停止。")
                break
            renderer.print_info("连续运行", f"第 {round_index} 轮完成，等待 {interval_seconds / 60:.1f} 分钟后进入下一轮。")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        emitter.emit("run_error", message="收到 Ctrl+C，当前前台运行已停止")
        return 130
    except TimeoutError as exc:
        emitter.emit("run_error", message=str(exc))
        return 124
    except Exception as exc:
        emitter.emit("run_error", message=f"运行失败: {exc}")
        return 1

    return 0 if (last_payload or {}).get("status") == "ok" else 1


def cmd_agent_benchmark(args: Any) -> int:
    """Run benchmark with the same streaming renderer and an enhanced comparison."""
    exit_code = cmd_agent_start(args)
    return exit_code


def cmd_agent_status(args: Any) -> int:
    settings = load_settings(args.config)
    payload = {
        "status": "ok",
        "model": getattr(args, "model", "") or settings.llm.default_model,
        "learning": get_learning_status(),
        "suggestions": load_learning_suggestions(),
        "memory": _memory_summary(settings, agent_id=getattr(args, "agent_id", ""), limit=int(getattr(args, "limit", 20))),
        "datasource": _provider_diagnostics(settings),
    }
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_status(payload)
    return 0


def cmd_agent_history(args: Any) -> int:
    entries = load_experiences(limit=int(getattr(args, "limit", 20)))
    model = getattr(args, "model", "")
    if model:
        entries = [item for item in entries if str(item.get("llm_model", "")) == model]
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"experiences": entries}, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_history(entries)
    return 0


def cmd_agent_stop(args: Any) -> int:
    message = "CLI agent runs are foreground processes; use Ctrl+C in the running terminal to stop safely."
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"status": "ok", "message": message}, ensure_ascii=False, indent=2))
    else:
        RichEventRenderer().print_info("停止说明", message)
    return 0


def cmd_agent_learning_status(args: Any) -> int:
    payload = get_learning_status()
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_learning_status(payload)
    return 0


def cmd_agent_learning_suggestions(args: Any) -> int:
    payload = load_learning_suggestions()
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_learning_suggestions(payload)
    return 0


def cmd_agent_learning_trigger(args: Any) -> int:
    payload = trigger_learning_if_ready(force=bool(getattr(args, "force", False)))
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_learning_status(payload, title="学习分析结果")
    return 0


def cmd_agent_memory(args: Any) -> int:
    settings = load_settings(args.config)
    agent_id = getattr(args, "agent_id", "") or "agent-rule-baseline"
    cases = AgentMemoryStore(settings).list_cases(
        agent_id=agent_id,
        limit=int(getattr(args, "limit", 20)),
        stock_code=getattr(args, "similar_to", ""),
        outcome=getattr(args, "outcome", ""),
    )
    payload = {"agent_id": agent_id, "count": len(cases), "cases": cases}
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_memory(payload)
    return 0


def cmd_datasource_status(args: Any) -> int:
    settings = load_settings(args.config)
    payload = _provider_diagnostics(settings)
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_datasource(payload)
    return 0


def cmd_datasource_test(args: Any) -> int:
    """Smoke-test configured data providers without exposing credentials."""
    settings = load_settings(args.config)
    base_agent = DataAgent(settings=settings)
    diagnostics = base_agent.provider_diagnostics()
    requested = _parse_models(getattr(args, "sources", ""))
    if not requested:
        requested = list(PROVIDER_CATALOG) if getattr(args, "all", False) else list(diagnostics.get("provider_chain", []))
    sources = [normalize_provider_name(item) for item in requested]
    checks = _parse_models(getattr(args, "checks", "history")) or ["history"]
    timeout_seconds = float(getattr(args, "timeout_seconds", 15.0) or 15.0)
    payload = {
        "status": "ok",
        "stock_code": getattr(args, "stock_code", "600519"),
        "days": int(getattr(args, "days", 5)),
        "checks": checks,
        "items": [
            _test_one_datasource(
                settings,
                source=source,
                stock_code=getattr(args, "stock_code", "600519"),
                days=int(getattr(args, "days", 5)),
                checks=checks,
                include_universe=bool(getattr(args, "include_universe", False)),
                timeout_seconds=timeout_seconds,
            )
            for source in sources
        ],
    }
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_datasource_tests(payload)
    return 0 if any(item.get("status") == "ok" for item in payload["items"]) else 1


def cmd_datasource_configure_jqdata(args: Any) -> int:
    """Persist JQData credentials through hidden prompts in the ignored runtime config."""
    username = str(getattr(args, "username", "") or "").strip()
    if not username:
        username = input("JQData username: ").strip()
    password = getpass.getpass("JQData password: ").strip()
    if not username or not password:
        print(json.dumps({"status": "error", "message": "username and password are required"}, ensure_ascii=False, indent=2))
        return 1
    provider_chain = _parse_models(str(getattr(args, "provider_chain", "") or ""))
    if not provider_chain:
        settings = load_settings(getattr(args, "config", None))
        provider_chain = list(getattr(settings.data, "provider_chain", []) or [])
    normalized_chain = []
    for item in provider_chain + ["jqdata"]:
        source = normalize_provider_name(item)
        if source and source not in normalized_chain:
            normalized_chain.append(source)
    path = save_runtime_overrides(
        {
            "data": {
                "jqdata_username": username,
                "jqdata_password": password,
                "provider_chain": normalized_chain,
            }
        }
    )
    payload = {
        "status": "ok",
        "message": "JQData credentials saved to ignored runtime config",
        "runtime_config_path": str(path),
        "provider_chain": normalized_chain,
        "has_jqdata_username": True,
        "has_jqdata_password": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_datasource_configure_ifind(args: Any) -> int:
    """Persist iFinD tokens through hidden prompts in the ignored runtime config."""
    access_token = getpass.getpass("iFinD access token: ").strip()
    refresh_token = getpass.getpass("iFinD refresh token (optional): ").strip()
    if not access_token:
        print(json.dumps({"status": "error", "message": "access token is required"}, ensure_ascii=False, indent=2))
        return 1
    provider_chain = _parse_models(str(getattr(args, "provider_chain", "") or ""))
    if not provider_chain:
        settings = load_settings(getattr(args, "config", None))
        provider_chain = list(getattr(settings.data, "provider_chain", []) or [])
    normalized_chain = []
    for item in provider_chain + ["ifind"]:
        source = normalize_provider_name(item)
        if source and source not in normalized_chain:
            normalized_chain.append(source)
    path = save_runtime_overrides(
        {
            "data": {
                "ifind_access_token": access_token,
                "ifind_refresh_token": refresh_token,
                "provider_chain": normalized_chain,
            }
        }
    )
    payload = {
        "status": "ok",
        "message": "iFinD tokens saved to ignored runtime config",
        "runtime_config_path": str(path),
        "provider_chain": normalized_chain,
        "has_ifind_access_token": True,
        "has_ifind_refresh_token": bool(refresh_token),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


class RichEventRenderer:
    """Rich-backed event renderer with a plain-text fallback."""

    def __init__(self, verbose: bool = False, debug: bool = False) -> None:
        self.verbose = verbose
        self.debug = debug
        try:
            from rich.console import Console

            self.console = Console()
            self.rich = True
        except Exception:  # pragma: no cover - depends on optional dependency
            self.console = None
            self.rich = False

    def __call__(self, event: AgentEvent) -> None:
        if self.debug:
            self._print(json.dumps(event.to_dict(), ensure_ascii=False, indent=2, default=str))
            return
        handlers = {
            "run_start": self._render_run_start,
            "run_complete": self._render_run_complete,
            "run_error": self._render_error,
            "screening_start": self._render_workflow_event,
            "screening_complete": self._render_screening_complete,
            "analysis_start": self._render_workflow_event,
            "analysis_complete": self._render_analysis_complete,
            "data_fetch_start": self._render_workflow_event,
            "data_fetch_complete": self._render_data_fetch_complete,
            "agent_chain_step": self._render_agent_chain_step,
            "agent_start": self._render_agent_start,
            "agent_complete": self._render_agent_complete,
            "decision_made": self._render_decision,
            "trade_executed": self._render_trade,
            "data_source_switched": self._render_datasource_event,
            "learning_experience_recorded": self._render_learning_event,
            "learning_analysis_triggered": self._render_learning_event,
            "learning_suggestion_generated": self._render_learning_event,
            "memory_case_retrieved": self._render_memory_event,
        }
        handler = handlers.get(event.type, self._render_generic)
        handler(event)

    def print_info(self, title: str, body: str) -> None:
        if self.rich:
            from rich.panel import Panel

            self.console.print(Panel(body, title=title, border_style="cyan"))
        else:
            self._print(f"{title}\n{body}")

    def render_status(self, payload: dict[str, Any]) -> None:
        learning = payload.get("learning", {}) if isinstance(payload.get("learning"), dict) else {}
        memory = payload.get("memory", {}) if isinstance(payload.get("memory"), dict) else {}
        datasource = payload.get("datasource", {}) if isinstance(payload.get("datasource"), dict) else {}
        lines = [
            f"模型: {payload.get('model', '')}",
            "",
            "学习状态",
            f"  累计经验: {learning.get('total_experiences', 0)}",
            f"  进度: {learning.get('progress', 0)}/{learning.get('threshold', 30)}",
            f"  成功率: {_percent(learning.get('success_rate', 0.0))}",
            f"  平均收益: {_float_text(learning.get('average_return_pct', 0.0))}%",
            "",
            "记忆统计",
            f"  案例数: {memory.get('count', 0)}",
            "",
            "数据源状态",
            f"  模式: {datasource.get('mode', '')}",
            f"  降级链: {', '.join(datasource.get('provider_chain', []) or [])}",
        ]
        self.print_info("智能体状态", "\n".join(lines))

    def render_history(self, entries: list[dict[str, Any]]) -> None:
        if not entries:
            self.print_info("历史经验", "暂无经验记录。")
            return
        lines = []
        for item in entries:
            outcome = item.get("outcome", {}) if isinstance(item.get("outcome"), dict) else {}
            outputs = item.get("agent_outputs", {}) if isinstance(item.get("agent_outputs"), dict) else {}
            lines.append(
                f"{item.get('date', '')} {item.get('llm_model', '')} {item.get('stock_code', '')} "
                f"{outputs.get('final_decision', '')} return={outcome.get('return_pct', 0)}%"
            )
        self.print_info("历史经验", "\n".join(lines))

    def render_learning_status(self, payload: dict[str, Any], title: str = "学习状态") -> None:
        lines = [
            f"累计经验: {payload.get('total_experiences', 0)}",
            f"进度: {payload.get('progress', 0)}/{payload.get('threshold', 30)}",
            f"是否可分析: {'是' if payload.get('ready') else '否'}",
            f"成功率: {_percent(payload.get('success_rate', 0.0))}",
            f"平均收益: {_float_text(payload.get('average_return_pct', 0.0))}%",
        ]
        suggestions = payload.get("suggestions", [])
        if suggestions:
            lines.append("")
            lines.append(f"建议数: {len(suggestions)}")
        self.print_info(title, "\n".join(lines))

    def render_learning_suggestions(self, payload: dict[str, Any]) -> None:
        suggestions = payload.get("suggestions", []) if isinstance(payload, dict) else []
        if not suggestions:
            self.print_info("学习建议", "暂无建议。运行 agent learning trigger --force 可强制分析当前经验。")
            return
        lines = [f"分析时间: {payload.get('analyzed_at', '')}", f"建议数: {len(suggestions)}", ""]
        for index, item in enumerate(suggestions, 1):
            lines.extend(
                [
                    f"建议 #{index}: {item.get('agent_id', '')} / {item.get('section', '')}",
                    f"  指标: {item.get('metric', '')}",
                    f"  当前值: {item.get('current_value', '')}",
                    f"  建议值: {item.get('suggested_value', '')}",
                    f"  置信度: {_percent(item.get('confidence', 0.0))}",
                    f"  原因: {item.get('reason', '')}",
                    "",
                ]
            )
        self.print_info("学习建议", "\n".join(lines).strip())

    def render_memory(self, payload: dict[str, Any]) -> None:
        cases = payload.get("cases", []) if isinstance(payload, dict) else []
        if not cases:
            self.print_info("Agent 记忆", "暂无可用记忆案例。若未启动 MongoDB，这是正常的只读空态。")
            return
        lines = [f"Agent: {payload.get('agent_id', '')}", f"案例数: {len(cases)}", ""]
        for item in cases:
            lines.append(
                f"- {item.get('decision_date', '')} {item.get('stock_code', '')} "
                f"{item.get('action', '')} {item.get('outcome', '')} pnl={item.get('pnl_pct', 0)}%"
            )
            reason = item.get("reason", "")
            if reason:
                lines.append(f"  理由: {reason}")
        self.print_info("Agent 记忆", "\n".join(lines))

    def render_datasource(self, payload: dict[str, Any]) -> None:
        lines = [
            f"数据模式: {payload.get('mode', '')}",
            f"Provider chain: {', '.join(payload.get('provider_chain', []) or [])}",
        ]
        providers = payload.get("providers", [])
        if isinstance(providers, list) and providers:
            lines.append("")
            lines.append("Provider 详情:")
            for item in providers:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('name', '')}: configured={item.get('configured', '')}, "
                        f"available={item.get('available', '')}, reason={item.get('reason', '')}"
                    )
        self.print_info("数据源状态", "\n".join(lines))

    def render_datasource_tests(self, payload: dict[str, Any]) -> None:
        items = payload.get("items", []) if isinstance(payload, dict) else []
        lines = [f"测试股票: {payload.get('stock_code', '')}", f"历史窗口: {payload.get('days', '')} 天", ""]
        for item in items:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('source', '')}: {item.get('status', '')}")
            lines.append(f"  原因/结果: {item.get('message', '')}")
            for check in item.get("checks", []) if isinstance(item.get("checks"), list) else []:
                if isinstance(check, dict):
                    lines.append(f"  - {check.get('operation', '')}: {check.get('status', '')} {check.get('detail', '')}")
        self.print_info("数据源 smoke 测试", "\n".join(lines).strip())

    def render_result_summary(self, payload: dict[str, Any]) -> None:
        agents = payload.get("agents", []) if isinstance(payload.get("agents"), list) else []
        rankings = payload.get("rankings", []) if isinstance(payload.get("rankings"), list) else []
        lines = [f"运行日期: {payload.get('run_date', '')}", f"模型数: {len(agents)}"]
        if rankings:
            lines.append("")
            lines.append("收益排行:")
            for item in rankings:
                if isinstance(item, dict):
                    model = item.get("llm_model", item.get("model", ""))
                    ret = item.get("total_return", item.get("return", 0.0))
                    lines.append(f"- #{item.get('rank', '')} {model}: {_percent(ret)}")
        insights = _benchmark_insights(payload)
        if insights:
            lines.append("")
            lines.extend(insights)
        learning = payload.get("learning")
        if isinstance(learning, dict):
            lines.append("")
            lines.append("学习结果:")
            lines.append(json.dumps(learning, ensure_ascii=False, default=str)[:600])
        self.print_info("运行完成", "\n".join(lines))

    def _render_run_start(self, event: AgentEvent) -> None:
        self.print_info("启动运行", event.payload.get("message", "开始运行"))

    def _render_run_complete(self, event: AgentEvent) -> None:
        self.print_info("运行事件", event.payload.get("message", "运行完成"))

    def _render_error(self, event: AgentEvent) -> None:
        self._print(f"[red]错误: {event.payload.get('message', '')}[/red]")

    def _render_agent_start(self, event: AgentEvent) -> None:
        self._print(f"[cyan]启动智能体[/cyan] {event.model or event.agent_id}: {event.payload.get('message', '')}")

    def _render_agent_complete(self, event: AgentEvent) -> None:
        self._print(
            f"[green]智能体完成[/green] {event.model or event.agent_id}: "
            f"权益={event.payload.get('equity', '')}, 收益={_percent(event.payload.get('total_return', 0.0))}"
        )

    def _render_workflow_event(self, event: AgentEvent) -> None:
        label = {
            "screening_start": "筛选",
            "analysis_start": "分析",
            "data_fetch_start": "数据",
        }.get(event.type, "流程")
        self._print(f"[blue]{label}[/blue] {event.payload.get('message', '')}")

    def _render_screening_complete(self, event: AgentEvent) -> None:
        candidates = event.payload.get("candidates", []) if isinstance(event.payload.get("candidates"), list) else []
        scores = event.payload.get("candidate_scores", {}) if isinstance(event.payload.get("candidate_scores"), dict) else {}
        lines = [event.payload.get("message", "完成股票池筛选")]
        if candidates:
            lines.append("")
            lines.append("入选股票:")
            for item in candidates[:10]:
                if not isinstance(item, dict):
                    continue
                code = item.get("stock_code", "")
                score = scores.get(code, "")
                score_text = f" score={_float_text(score)}" if score != "" else ""
                lines.append(f"- {code} {item.get('stock_name', '')} {item.get('sector', '')}{score_text}".strip())
        self.print_info("股票池筛选", "\n".join(lines))

    def _render_data_fetch_complete(self, event: AgentEvent) -> None:
        objective = event.payload.get("objective_data", {}) if isinstance(event.payload.get("objective_data"), dict) else {}
        stock = objective.get("stock", {}) if isinstance(objective.get("stock"), dict) else {}
        quote = objective.get("quote", {}) if isinstance(objective.get("quote"), dict) else {}
        financial = objective.get("financial", {}) if isinstance(objective.get("financial"), dict) else {}
        bars = objective.get("bars", []) if isinstance(objective.get("bars"), list) else []
        if not objective:
            self._print(f"[blue]数据[/blue] {event.payload.get('message', '')}")
            return
        lines = [event.payload.get("message", "完成数据获取"), "", render_company_info(stock, quote, financial)]
        if bars:
            lines.extend(["", render_kline_ascii(bars), "", render_technical_indicators(bars)])
        if financial:
            lines.extend(["", render_financial_table(financial)])
        self.print_info("客观数据快照", "\n".join(item for item in lines if item))

    def _render_agent_chain_step(self, event: AgentEvent) -> None:
        step = str(event.payload.get("chain_step", ""))
        title = _chain_step_title(step)
        result = event.payload.get("result", {}) if isinstance(event.payload.get("result"), dict) else {}
        if result:
            self._print(
                f"[cyan]{title}[/cyan] {event.payload.get('stock_code', '')} "
                f"{result.get('label', '')} score={_percent(result.get('score', 0.0))}"
            )
        else:
            self._print(f"[cyan]{title}[/cyan] {event.payload.get('message', '')}")
        if result:
            objective = event.payload.get("objective_data", {}) if isinstance(event.payload.get("objective_data"), dict) else {}
            details = [render_analysis_result(title, result)]
            bars = objective.get("bars", []) if isinstance(objective.get("bars"), list) else []
            if bars:
                details.extend(["", render_technical_indicators(bars)])
                if self.verbose:
                    details.extend(["", render_kline_ascii(bars)])
            financial = objective.get("financial") if isinstance(objective.get("financial"), dict) else None
            if financial:
                details.extend(["", render_financial_table(financial)])
            news = objective.get("news") if "news" in objective else None
            if news:
                details.extend(["", render_news_list(news)])
            self.print_info(f"{title} 明细", "\n".join(details).strip())

    def _render_analysis_complete(self, event: AgentEvent) -> None:
        report = event.payload.get("report", {}) if isinstance(event.payload.get("report"), dict) else {}
        decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
        suffix = ""
        if decision:
            suffix = f" action={decision.get('action', '')} confidence={_percent(decision.get('confidence', 0.0))}"
        self._print(f"[green]分析完成[/green] {event.payload.get('message', '')}{suffix}")

    def _render_decision(self, event: AgentEvent) -> None:
        decision = event.payload.get("decision", {}) if isinstance(event.payload.get("decision"), dict) else event.payload
        self._print(
            f"[yellow]决策[/yellow] {decision.get('stock_code', '')} "
            f"{decision.get('action', '')} 置信度={_percent(decision.get('confidence', 0.0))}"
        )
        body = _render_decision_evidence(decision)
        if body:
            self.print_info(f"决策客观依据 {decision.get('stock_code', '')}", body)

    def _render_trade(self, event: AgentEvent) -> None:
        self._print(
            f"[green]交易[/green] {event.payload.get('side', '')} {event.payload.get('stock_code', '')} "
            f"仓位={_percent(event.payload.get('position_size', 0.0))}"
        )

    def _render_datasource_event(self, event: AgentEvent) -> None:
        self._print(f"[blue]数据源[/blue] {event.payload.get('message', '')}")

    def _render_learning_event(self, event: AgentEvent) -> None:
        self._print(f"[magenta]学习[/magenta] {event.payload.get('message', '')}")

    def _render_memory_event(self, event: AgentEvent) -> None:
        self._print(f"[magenta]记忆[/magenta] {event.payload.get('message', '')}")

    def _render_generic(self, event: AgentEvent) -> None:
        if self.verbose:
            self._print(f"[dim]{event.type}[/dim] {event.payload.get('message', '')}")

    def _print(self, message: str) -> None:
        if self.rich:
            self.console.print(message)
        else:
            print(message)


def _render_run_header(renderer: RichEventRenderer, settings: Any, *, models: list[str], offline: bool) -> None:
    learning = get_learning_status()
    provider_chain = getattr(settings.data, "provider_chain", []) or []
    lines = [
        f"模型: {', '.join(models) if models else getattr(settings.llm, 'default_model', '')}",
        f"模式: {'离线' if offline or getattr(settings.data, 'mode', '') == 'offline' else '在线'}",
        f"数据源链: {', '.join(provider_chain)}",
        f"学习进度: {learning.get('progress', 0)}/{learning.get('threshold', 30)}",
    ]
    renderer.print_info("CLI 流式智能体", "\n".join(lines))


def _emit_datasource_snapshot(emitter: AgentEventEmitter, settings: Any) -> None:
    diagnostics = _provider_diagnostics(settings)
    emitter.emit(
        "data_source_switched",
        stage="datasource",
        message=f"数据模式={diagnostics.get('mode', '')}，链路={', '.join(diagnostics.get('provider_chain', []) or [])}",
        diagnostics=diagnostics,
    )


def _emit_post_run_visibility(emitter: AgentEventEmitter, settings: Any, payload: dict[str, Any]) -> None:
    learning = payload.get("learning", {}) if isinstance(payload.get("learning"), dict) else {}
    if learning:
        record_result = learning.get("record_result", {}) if isinstance(learning.get("record_result"), dict) else {}
        status = learning.get("status", learning)
        suggestions = status.get("suggestions", []) if isinstance(status, dict) else []
        emitter.emit(
            "learning_experience_recorded",
            stage="learning",
            message=f"本次记录经验 {record_result.get('recorded', 0)} 条",
            learning=learning,
        )
        if suggestions:
            emitter.emit(
                "learning_suggestion_generated",
                stage="learning",
                message=f"生成 {len(suggestions)} 条学习建议，等待人工审查",
                suggestions=suggestions,
            )
    memory_store = AgentMemoryStore(settings)
    for agent in payload.get("agents", []) if isinstance(payload.get("agents"), list) else []:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("agent_id", ""))
        cases = memory_store.list_cases(agent_id=agent_id, limit=3)
        emitter.emit(
            "memory_case_retrieved",
            agent_id=agent_id,
            model=str(agent.get("llm_model", "")),
            stage="memory",
            message=f"{agent_id} 检索到 {len(cases)} 条历史案例",
            cases=cases,
        )


def _provider_diagnostics(settings: Any) -> dict[str, Any]:
    try:
        payload = DataAgent(settings=settings).provider_diagnostics()
    except Exception as exc:
        return {
            "mode": getattr(settings.data, "mode", ""),
            "provider_chain": getattr(settings.data, "provider_chain", []) or [],
            "providers": [],
            "error": str(exc),
        }
    return payload if isinstance(payload, dict) else {"providers": []}


def _test_one_datasource(
    settings: Any,
    *,
    source: str,
    stock_code: str,
    days: int,
    checks: list[str] | None = None,
    include_universe: bool = False,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    source = normalize_provider_name(source)
    spec = PROVIDER_CATALOG.get(source)
    if not spec:
        return {"source": source, "status": "skipped", "message": "unknown provider", "checks": []}
    if not spec.get("class_name"):
        return {
            "source": source,
            "status": "skipped",
            "message": "no adapter is registered; this source is documented as reference/manual workflow only",
            "checks": [],
        }
    dependency_module = str(spec.get("dependency_module", ""))
    if dependency_module and find_spec(dependency_module) is None:
        return {
            "source": source,
            "status": "skipped",
            "message": f"dependency not installed: {dependency_module}",
            "checks": [],
        }
    missing = [field for field in spec.get("credential_fields", []) if not str(getattr(settings.data, str(field), "") or "").strip()]
    if missing:
        return {"source": source, "status": "skipped", "message": f"missing credentials: {', '.join(missing)}", "checks": []}
    scoped = copy.deepcopy(settings)
    scoped.data.mode = "online"
    scoped.data.provider_chain = [source]
    agent = DataAgent(settings=scoped)
    # Provider smoke must test the selected source itself. Shared file-cache
    # hits would otherwise make a broken provider look healthy.
    agent._market_cache = _DatasourceSmokeNoopCache()  # noqa: SLF001
    check_results: list[dict[str, Any]] = []
    requested_operations = [item for item in checks or ["history"] if item]
    operations = [item for item in requested_operations if item in {"universe", "history", "financial", "quote"}]
    if include_universe:
        operations.insert(0, "universe")
    for operation in dict.fromkeys(operations):
        if operation != "universe" and not provider_supports(source, operation):
            check_results.append({"operation": operation, "status": "skipped", "detail": "capability not supported"})
            continue
        if operation == "universe" and not provider_supports(source, operation):
            check_results.append({"operation": operation, "status": "skipped", "detail": "capability not supported"})
            continue
        attempts_before = _provider_attempt_count(agent)
        try:
            result_status, result_detail = _run_with_timeout(
                lambda: _run_datasource_operation(agent, operation=operation, stock_code=stock_code, days=days),
                timeout_seconds=timeout_seconds,
                label="provider check",
            )
            check_results.append(
                _source_check_result(
                    agent,
                    source=source,
                    operation=operation,
                    attempts_before=attempts_before,
                    fallback_status=result_status,
                    fallback_detail=result_detail,
                )
            )
        except Exception as exc:
            check_results.append({"operation": operation, "status": "error", "detail": str(exc)[:300]})
    ok_count = sum(1 for check in check_results if check.get("status") == "ok")
    status = "ok" if ok_count else "error"
    return {
        "source": source,
        "status": status,
        "message": f"{ok_count} checks passed" if ok_count else "all executable checks failed",
        "checks": check_results,
        "attempts": agent.provider_diagnostics().get("attempts", []),
    }


def _run_datasource_operation(agent: DataAgent, *, operation: str, stock_code: str, days: int) -> tuple[str, str]:
    if operation == "universe":
        result = agent.get_universe()
        return ("ok" if result else "empty", f"{len(result)} stocks")
    if operation == "history":
        result = agent.get_history(stock_code, days=days)
        return ("ok" if result else "empty", f"{len(result)} bars")
    if operation == "financial":
        result = agent.get_financial(stock_code)
        ok = bool(result.stock_code)
        return ("ok" if ok else "empty", f"pe={result.pe_ttm}, roe={result.roe}")
    if operation == "quote":
        result = agent.get_quote(stock_code)
        return ("ok" if result.price > 0 else "empty", f"price={result.price}")
    return "skipped", "unknown operation"


class _DatasourceSmokeNoopCache:
    """Disable persistent market cache only for single-source smoke checks."""

    def get_history(self, stock_code: str, days: int) -> None:
        return None

    def set_history(self, stock_code: str, days: int, bars: Any) -> None:
        return None

    def get_quote(self, stock_code: str) -> None:
        return None

    def set_quote(self, stock_code: str, quote: Any) -> None:
        return None

    def get_financial(self, stock_code: str) -> None:
        return None

    def set_financial(self, stock_code: str, snapshot: Any) -> None:
        return None


def _run_with_timeout(func: Any, *, timeout_seconds: float, label: str = "operation") -> Any:
    """Run one provider smoke operation with a hard CLI timeout.

    Some free web data sources can hang inside third-party network calls. The
    smoke command is a diagnostic command, so it must return a clear timeout
    result instead of turning into a long-running listener.
    """
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put(("ok", func()))
        except Exception as exc:  # pragma: no cover - exercised through caller tests/network smoke
            result_queue.put(("error", exc))

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(max(0.1, float(timeout_seconds)))
    if worker.is_alive():
        raise TimeoutError(f"{label} exceeded {timeout_seconds:.1f}s")
    status, value = result_queue.get_nowait()
    if status == "error":
        raise value
    return value


def _provider_attempt_count(agent: DataAgent) -> int:
    attempts = agent.provider_diagnostics().get("attempts", [])
    return len(attempts) if isinstance(attempts, list) else 0


def _source_check_result(
    agent: DataAgent,
    *,
    source: str,
    operation: str,
    attempts_before: int,
    fallback_status: str,
    fallback_detail: str,
) -> dict[str, Any]:
    attempts = agent.provider_diagnostics().get("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
    new_attempts = [item for item in attempts[attempts_before:] if isinstance(item, dict)]
    operation_attempts = [
        item
        for item in new_attempts
        if item.get("source") == source and item.get("operation") == operation
    ]
    if operation_attempts:
        latest = operation_attempts[-1]
        status = str(latest.get("status", fallback_status))
        detail = str(latest.get("detail", fallback_detail) or fallback_detail)
        if status == "ok":
            detail = fallback_detail
        return {"operation": operation, "status": status, "detail": detail[:300]}

    init_attempts = [item for item in new_attempts if item.get("source") == source and item.get("operation") == "init"]
    if init_attempts:
        latest = init_attempts[-1]
        return {
            "operation": operation,
            "status": str(latest.get("status", "error")),
            "detail": f"provider init {latest.get('status', 'error')}: {latest.get('detail', '')}"[:300],
        }

    offline_attempts = [item for item in new_attempts if item.get("source") == "offline"]
    if offline_attempts:
        return {
            "operation": operation,
            "status": "error",
            "detail": "provider produced no result; offline fallback was ignored for this source smoke check",
        }
    return {"operation": operation, "status": fallback_status, "detail": fallback_detail[:300]}


def _memory_summary(settings: Any, *, agent_id: str = "", limit: int = 20) -> dict[str, Any]:
    target_agent = agent_id or "agent-rule-baseline"
    cases = AgentMemoryStore(settings).list_cases(agent_id=target_agent, limit=limit)
    return {"agent_id": target_agent, "count": len(cases), "cases": cases[:5]}


def _parse_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _benchmark_insights(payload: dict[str, Any]) -> list[str]:
    agents = payload.get("agents", []) if isinstance(payload.get("agents"), list) else []
    if not agents:
        return []
    experiences = load_experiences(limit=500)
    experience_counts: dict[str, int] = {}
    for item in experiences:
        model = str(item.get("llm_model", ""))
        if model:
            experience_counts[model] = experience_counts.get(model, 0) + 1
    lines = ["Benchmark 洞察:"]
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        model = str(agent.get("llm_model", ""))
        decisions = agent.get("decisions", []) if isinstance(agent.get("decisions"), list) else []
        positions = [float(item.get("position_size", 0.0) or 0.0) for item in decisions if isinstance(item, dict)]
        buy_count = int(agent.get("buy_count", 0) or 0)
        sell_count = int(agent.get("sell_count", 0) or 0)
        total_trades = int(agent.get("total_trades", 0) or 0)
        avg_position = sum(positions) / len(positions) if positions else 0.0
        aggressiveness = min(1.0, buy_count / max(1, len(decisions)) + avg_position)
        error_mode = _error_mode(agent, avg_position=avg_position)
        lines.append(
            f"- {model}: 激进度={_percent(aggressiveness)}, 交易={total_trades}笔 "
            f"(买{buy_count}/卖{sell_count}), 平均仓位={_percent(avg_position)}, "
            f"经验数={experience_counts.get(model, 0)}, 错误模式={error_mode}"
        )
    return lines


def _error_mode(agent: dict[str, Any], *, avg_position: float) -> str:
    total_return = float(agent.get("total_return", 0.0) or 0.0)
    buy_count = int(agent.get("buy_count", 0) or 0)
    total_trades = int(agent.get("total_trades", 0) or 0)
    if total_return < 0 and avg_position >= 0.15:
        return "可能高估信号并追高"
    if total_return < 0 and total_trades == 0:
        return "可能过度保守或无可执行信号"
    if buy_count > 0 and total_trades >= 3:
        return "需关注交易频率和手续费影响"
    return "暂无明显错误模式"


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def _float_text(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "0.0000"
