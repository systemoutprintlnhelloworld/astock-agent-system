"""Enhanced CLI commands for streaming Agent runs and learning visibility."""

from __future__ import annotations

import copy
import getpass
import json
import queue
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
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
from astock_agent_system.config import PROJECT_ROOT, load_settings, save_runtime_overrides
from astock_agent_system.data import DataAgent
from astock_agent_system.data.data_agent import PROVIDER_CATALOG, normalize_provider_name, provider_supports
from astock_agent_system.data.local_store import DEFAULT_LOCAL_MARKET_DB, LocalMarketStore
from astock_agent_system.events import AgentEvent, AgentEventEmitter
from astock_agent_system.orchestrator import MultiAgentOrchestrator


_SECRET_FIELD_HINTS = (
    "api_key",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "authorization",
    "webhook",
    "smtp",
)


def _redact_string_for_run_log(value: str) -> str:
    """Avoid persisting obvious bearer/key-like values in user-shareable run logs."""

    text = value
    for marker in ("Bearer ", "Token ", "access_token=", "refresh_token=", "api_key=", "password="):
        if marker in text:
            head, _, tail = text.partition(marker)
            token, sep, rest = tail.partition(" ")
            text = f"{head}{marker}***REDACTED***{sep}{rest}" if token else text
    return text


def _redact_for_run_log(value: Any) -> Any:
    """Recursively redact secrets before writing persistent run logs."""

    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(hint in key_text for hint in _SECRET_FIELD_HINTS):
                redacted[key] = "***REDACTED***" if item else ""
            else:
                redacted[key] = _redact_for_run_log(item)
        return redacted
    if isinstance(value, list):
        return [_redact_for_run_log(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_for_run_log(item) for item in value]
    if isinstance(value, str):
        return _redact_string_for_run_log(value)
    return value


def _compact_error(message: Any, *, retry: str | int | None = None) -> dict[str, Any]:
    """Classify noisy exceptions into a short Chinese reason plus stable error code."""

    text = _redact_string_for_run_log(str(message or "").strip())
    lower = text.lower()
    code = "E-RUN-ERROR"
    reason = text[:160] if text else "未知错误"
    if "mongo" in lower or "serverselectiontimeout" in lower:
        code = "E-MONGO-CONNECT"
        reason = "MongoDB 未连接或不可达；可用 --no-persist/菜单调试选项先跑通工作流"
    elif "timeout" in lower or "timed out" in lower or "exceeded" in lower or "超时" in text:
        code = "E-TIMEOUT"
        reason = "运行或外部请求超时；请缩小候选数/延长超时后重试"
    elif "429" in lower or "rate limit" in lower or "too many" in lower or "频率" in text or "限流" in text:
        code = "E-RATE-LIMIT"
        reason = "外部服务限流；请降低并发/等待冷却后重试"
    elif "401" in lower or "403" in lower or "unauthorized" in lower or "forbidden" in lower:
        code = "E-AUTH"
        reason = "鉴权失败或权限不足；请重新做凭证自检"
    elif "ifind" in lower or "同花顺" in text:
        code = "E-IFIND"
        reason = "iFinD/同花顺数据源请求失败；请查看矩阵诊断中的格式/权限/空返回"
    elif "jqdata" in lower or "joinquant" in lower or "聚宽" in text:
        code = "E-JQDATA"
        reason = "JQData/聚宽数据源请求失败；请重新做凭证自检"
    elif "tushare" in lower:
        code = "E-TUSHARE"
        reason = "Tushare 数据源请求失败；请检查 token、积分权限和接口频率"
    elif "llm" in lower or "openai" in lower or "model" in lower or "gateway" in lower:
        code = "E-LLM"
        reason = "LLM 网关或模型请求失败；请在 LLM 配置与诊断页面执行自检"
    return {"code": code, "reason": reason, "retry": str(retry if retry is not None else "0/0"), "raw": text[:500]}


def _cell_text(value: Any, *, width: int = 36) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) > width:
        return text[: max(0, width - 1)] + "…"
    return text


def _format_table(headers: list[str], rows: list[list[Any]], *, max_width: int = 36) -> str:
    """Render small human-facing terminal tables without depending on terminal state."""

    if not rows:
        return "(无数据)"
    string_rows = [[_cell_text(item, width=max_width) for item in row] for row in rows]
    cols = len(headers)
    widths = []
    for idx in range(cols):
        values = [headers[idx]] + [row[idx] if idx < len(row) else "" for row in string_rows]
        widths.append(min(max(len(str(item)) for item in values), max_width))

    def line(items: list[Any]) -> str:
        parts = []
        for idx in range(cols):
            item = _cell_text(items[idx] if idx < len(items) else "", width=widths[idx])
            parts.append(item.ljust(widths[idx]))
        return " | ".join(parts).rstrip()

    sep = "-+-".join("-" * width for width in widths)
    return "\n".join([line(headers), sep, *[line(row) for row in string_rows]])


class RunLogRecorder:
    """Write compact, redacted run events for later debugging/handoff."""

    def __init__(self, settings: Any, *, models: list[str]) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_part = "-".join(models or [getattr(settings.llm, "default_model", "default") or "default"])
        safe_model = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in model_part)[:80]
        self.root = PROJECT_ROOT / "data" / "runtime" / "runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f"{stamp}_{safe_model}.jsonl"
        self.summary_path = self.root / f"{stamp}_{safe_model}.summary.json"
        self.event_count = 0
        self.errors: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self._closed = False

    def __call__(self, event: AgentEvent) -> None:
        if self._closed:
            return
        payload = _redact_for_run_log(event.to_dict())
        self.event_count += 1
        if event.type == "run_error":
            self.errors.append(_compact_error(event.payload.get("message", "")))
        if event.type == "trade_executed":
            self.trades.append(_redact_for_run_log(event.payload))
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def write_summary(self, payload: dict[str, Any] | None = None) -> None:
        summary = {
            "status": (payload or {}).get("status", "unknown"),
            "run_date": (payload or {}).get("run_date", ""),
            "model_count": (payload or {}).get("model_count", 0),
            "event_count": self.event_count,
            "error_count": len(self.errors),
            "trade_count": len(self.trades),
            "log_path": str(self.path),
            "errors": self.errors[-20:],
            "rankings": (payload or {}).get("rankings", []),
        }
        self.summary_path.write_text(json.dumps(_redact_for_run_log(summary), ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def close(self) -> None:
        self._closed = True


def cmd_agent_start(args: Any) -> int:
    """Run one or more model-driven agents with streaming event output."""
    settings = load_settings(args.config)
    if getattr(args, "offline", False):
        settings.data.mode = "offline"
    models = _parse_models(getattr(args, "models", "") or getattr(args, "model", ""))
    emitter = AgentEventEmitter()
    renderer = RichEventRenderer(verbose=bool(getattr(args, "verbose", False)), debug=bool(getattr(args, "debug", False)))
    emitter.subscribe(renderer)
    run_log = RunLogRecorder(settings, models=models)
    emitter.subscribe(run_log)

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
            _sleep_with_countdown(renderer, interval_seconds)
    except KeyboardInterrupt:
        emitter.emit("run_error", message="收到 Ctrl+C，当前前台运行已停止")
        run_log.write_summary(last_payload)
        renderer.print_info("运行日志", f"完整事件日志: {run_log.path}\n摘要: {run_log.summary_path}")
        run_log.close()
        return 130
    except TimeoutError as exc:
        emitter.emit("run_error", message=str(exc))
        run_log.write_summary(last_payload)
        renderer.print_info("运行日志", f"完整事件日志: {run_log.path}\n摘要: {run_log.summary_path}")
        run_log.close()
        return 124
    except Exception as exc:
        emitter.emit("run_error", message=f"运行失败: {exc}")
        run_log.write_summary(last_payload)
        renderer.print_info("运行日志", f"完整事件日志: {run_log.path}\n摘要: {run_log.summary_path}")
        run_log.close()
        return 1

    run_log.write_summary(last_payload)
    renderer.print_info("运行日志", f"完整事件日志: {run_log.path}\n摘要: {run_log.summary_path}")
    run_log.close()
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


def cmd_datasource_local_status(args: Any) -> int:
    """Show SQLite local market database status and recent sync history."""
    settings = load_settings(args.config)
    db_path = str(getattr(args, "db_path", "") or "")
    store = LocalMarketStore(path=db_path or DEFAULT_LOCAL_MARKET_DB)
    stats = store.stats()
    payload: dict[str, Any] = {
        "status": "ok",
        "db_path": str(store.path),
        "local_stats": stats,
        "recent_sync_runs": store.recent_sync_runs(10),
        "provider_chain": list(settings.data.provider_chain or []),
    }
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_local_market_status(payload)
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
    items = []
    for source in sources:
        item = _test_one_datasource(
            settings,
            source=source,
            stock_code=getattr(args, "stock_code", "600519"),
            days=int(getattr(args, "days", 5)),
            checks=checks,
            include_universe=bool(getattr(args, "include_universe", False)),
            timeout_seconds=timeout_seconds,
        )
        if source == "ifind" and item.get("status") != "skipped":
            matrix = _test_ifind_matrix(
                settings,
                stock_code=getattr(args, "stock_code", "600519"),
                days=int(getattr(args, "days", 5)),
                checks=checks,
                timeout_seconds=max(3.0, min(timeout_seconds, 8.0)),
            )
            item["matrix"] = matrix
            if not _ifind_matrix_has_success(matrix):
                item["diagnosis"] = _ifind_failure_diagnosis(item, matrix)
        items.append(item)
    payload = {
        "status": "ok",
        "stock_code": getattr(args, "stock_code", "600519"),
        "days": int(getattr(args, "days", 5)),
        "checks": checks,
        "items": items,
    }
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_datasource_tests(payload)
    return 0 if any(item.get("status") == "ok" for item in payload["items"]) else 1


def cmd_datasource_sync_local(args: Any) -> int:
    """Build or update the local A-share SQLite market database."""
    settings = load_settings(args.config)
    sources = _parse_models(str(getattr(args, "sources", "") or ""))
    if sources:
        settings.data.provider_chain = [normalize_provider_name(item) for item in sources]
    sync_mode = str(getattr(args, "sync_mode", "incremental") or "incremental").strip().lower()
    if sync_mode not in {"quick", "full", "incremental", "specified"}:
        sync_mode = "incremental"
    provider_strategy = str(getattr(args, "provider_strategy", "fill-gaps") or "fill-gaps").strip().lower()
    if provider_strategy not in {"fill-gaps", "all-providers"}:
        provider_strategy = "fill-gaps"
    max_stocks = max(0, int(getattr(args, "max_stocks", 0) or 0))
    if sync_mode == "quick" and max_stocks == 0:
        max_stocks = 20
    settings.data.dynamic_universe_limit = max_stocks if max_stocks > 0 else None
    checks = _parse_models(str(getattr(args, "checks", "universe,history,quote,financial") or ""))
    if not checks:
        checks = ["universe", "history", "quote", "financial"]
    db_path = str(getattr(args, "db_path", "") or "")
    store = LocalMarketStore(path=db_path or DEFAULT_LOCAL_MARKET_DB)
    store.initialize()
    agent = DataAgent(settings=settings, use_local_store=False, local_store_path=store.path)
    days = int(getattr(args, "days", 120) or 120)
    requested_codes = _parse_models(str(getattr(args, "stock_codes", "") or ""))
    payload: dict[str, Any] = {
        "status": "ok",
        "db_path": str(store.path),
        "provider_chain": list(settings.data.provider_chain),
        "checks": checks,
        "days": days,
        "sync_mode": sync_mode,
        "provider_strategy": provider_strategy,
        "max_stocks": max_stocks,
        "universe_total": 0,
        "selected_count": 0,
        "items": [],
    }

    stocks = []
    if "universe" in checks or not requested_codes:
        try:
            before = _provider_attempt_count(agent)
            universe = agent.get_universe()
            source = _latest_success_source(agent, operation="universe", attempts_before=before)
            payload["universe_total"] = len(universe)
            if source:
                universe_to_store = universe[:max_stocks] if max_stocks > 0 else universe
                stored = store.upsert_universe(universe_to_store)
                store.record_sync(source=source, operation="universe", status="ok", detail=f"{stored} stocks")
                payload["items"].append({"operation": "universe", "status": "ok", "source": source, "stored": stored})
            else:
                payload["items"].append({"operation": "universe", "status": "skipped", "detail": "no online provider success"})
            stocks = universe
        except Exception as exc:
            detail = _redact_string_for_run_log(str(exc))
            store.record_sync(source="provider_chain", operation="universe", status="error", detail=detail)
            payload["items"].append({"operation": "universe", "status": "error", "detail": detail[:300]})

    if requested_codes:
        sync_mode = "specified"
        stock_codes = requested_codes[:max_stocks] if max_stocks > 0 else requested_codes
    else:
        all_codes = [stock.stock_code for stock in stocks]
        stock_codes = all_codes[:max_stocks] if max_stocks > 0 else all_codes
    payload["sync_mode"] = sync_mode
    payload["selected_count"] = len(stock_codes)
    if not stock_codes:
        payload["status"] = "error"
        payload["message"] = "no stock codes to sync; provide --stock-codes or enable universe-capable provider"
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 1

    operation_counts = {"history": 0, "quote": 0, "financial": 0}
    for stock_code in stock_codes:
        if "history" in checks:
            _sync_one_operation_with_strategy(settings, agent, store, payload, operation="history", stock_code=stock_code, days=days, counts=operation_counts, provider_strategy=provider_strategy)
        if "quote" in checks:
            _sync_one_operation_with_strategy(settings, agent, store, payload, operation="quote", stock_code=stock_code, days=days, counts=operation_counts, provider_strategy=provider_strategy)
        if "financial" in checks:
            _sync_one_operation_with_strategy(settings, agent, store, payload, operation="financial", stock_code=stock_code, days=days, counts=operation_counts, provider_strategy=provider_strategy)

    payload["stored"] = {"stocks": len(stock_codes), **operation_counts}
    payload["local_stats"] = store.stats()
    payload["provider_participation"] = _provider_participation(payload["items"])
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        RichEventRenderer().render_sync_local(payload)
    return 0 if any(value > 0 for value in operation_counts.values()) or any(item.get("operation") == "universe" and item.get("status") == "ok" for item in payload["items"]) else 1


def cmd_datasource_configure_jqdata(args: Any) -> int:
    """Persist JQData credentials after a real provider preflight."""
    username = str(getattr(args, "username", "") or "").strip()
    if not username:
        username = input("JQData username: ").strip()
    password = getpass.getpass("JQData password: ").strip()
    if not username or not password:
        print(json.dumps({"status": "error", "message": "username and password are required"}, ensure_ascii=False, indent=2))
        return 1
    provider_chain = _parse_models(str(getattr(args, "provider_chain", "") or ""))
    settings = load_settings(getattr(args, "config", None))
    if not provider_chain:
        provider_chain = list(getattr(settings.data, "provider_chain", []) or [])
    scoped = copy.deepcopy(settings)
    scoped.data.jqdata_username = username
    scoped.data.jqdata_password = password
    scoped.data.provider_chain = ["jqdata"]
    preflight = _test_one_datasource(scoped, source="jqdata", stock_code="600519", days=5, checks=["history", "quote"], timeout_seconds=12.0)
    if preflight.get("status") != "ok":
        payload = {
            "status": "error",
            "message": "JQData 自检失败，已拒绝写入本地配置",
            "provider": "jqdata",
            "checks": preflight.get("checks", []),
            "error": _compact_error(preflight.get("message", "JQData preflight failed")),
        }
        print(json.dumps(_redact_for_run_log(payload), ensure_ascii=False, indent=2, default=str))
        return 1
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
        "preflight": {"status": preflight.get("status"), "checks": preflight.get("checks", [])},
    }
    print(json.dumps(_redact_for_run_log(payload), ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_datasource_configure_ifind(args: Any) -> int:
    """Persist iFinD tokens after a real QuantAPI preflight."""
    access_token = getpass.getpass("iFinD access token: ").strip()
    refresh_token = getpass.getpass("iFinD refresh token (optional): ").strip()
    if not access_token:
        print(json.dumps({"status": "error", "message": "access token is required"}, ensure_ascii=False, indent=2))
        return 1
    provider_chain = _parse_models(str(getattr(args, "provider_chain", "") or ""))
    settings = load_settings(getattr(args, "config", None))
    if not provider_chain:
        provider_chain = list(getattr(settings.data, "provider_chain", []) or [])
    scoped = copy.deepcopy(settings)
    scoped.data.ifind_access_token = access_token
    scoped.data.ifind_refresh_token = refresh_token
    scoped.data.provider_chain = ["ifind"]
    preflight = _test_one_datasource(scoped, source="ifind", stock_code="600519", days=5, checks=["history", "quote"], timeout_seconds=12.0)
    matrix = _test_ifind_matrix(scoped, stock_code="600519", days=5, checks=["history", "quote"], timeout_seconds=6.0)
    matrix_ok = _ifind_matrix_has_success(matrix)
    if preflight.get("status") != "ok" and not matrix_ok:
        payload = {
            "status": "error",
            "message": "iFinD 自检失败，已拒绝写入本地配置",
            "provider": "ifind",
            "checks": preflight.get("checks", []),
            "matrix": matrix,
            "diagnosis": _ifind_failure_diagnosis(preflight, matrix),
            "error": _compact_error(preflight.get("message", "iFinD preflight failed")),
        }
        print(json.dumps(_redact_for_run_log(payload), ensure_ascii=False, indent=2, default=str))
        return 1
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
        "preflight": {"status": preflight.get("status"), "checks": preflight.get("checks", []), "matrix": matrix, "matrix_ok": matrix_ok},
    }
    print(json.dumps(_redact_for_run_log(payload), ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_datasource_configure_tushare(args: Any) -> int:
    """Persist Tushare token only after a real preflight succeeds."""
    token = getpass.getpass("Tushare token: ").strip()
    if not token:
        print(json.dumps({"status": "error", "message": "token is required"}, ensure_ascii=False, indent=2))
        return 1
    provider_chain = _parse_models(str(getattr(args, "provider_chain", "") or ""))
    settings = load_settings(getattr(args, "config", None))
    if not provider_chain:
        provider_chain = list(getattr(settings.data, "provider_chain", []) or [])
    scoped = copy.deepcopy(settings)
    scoped.data.tushare_token = token
    scoped.data.provider_chain = ["tushare"]
    preflight = _test_one_datasource(scoped, source="tushare", stock_code="600519", days=5, checks=["history", "quote", "financial"], timeout_seconds=12.0)
    if preflight.get("status") != "ok":
        payload = {
            "status": "error",
            "message": "Tushare 自检失败，已拒绝写入本地配置",
            "provider": "tushare",
            "checks": preflight.get("checks", []),
            "error": _compact_error(preflight.get("message", "Tushare preflight failed")),
        }
        print(json.dumps(_redact_for_run_log(payload), ensure_ascii=False, indent=2, default=str))
        return 1
    normalized_chain = []
    for item in provider_chain + ["tushare"]:
        source = normalize_provider_name(item)
        if source and source not in normalized_chain:
            normalized_chain.append(source)
    path = save_runtime_overrides({"data": {"tushare_token": token, "provider_chain": normalized_chain}})
    payload = {
        "status": "ok",
        "message": "Tushare token saved to ignored runtime config",
        "runtime_config_path": str(path),
        "provider_chain": normalized_chain,
        "has_tushare_token": True,
        "preflight": {"status": preflight.get("status"), "checks": preflight.get("checks", [])},
    }
    print(json.dumps(_redact_for_run_log(payload), ensure_ascii=False, indent=2, default=str))
    return 0


class RichEventRenderer:
    """Rich-backed event renderer with a plain-text fallback."""

    def __init__(self, verbose: bool = False, debug: bool = False) -> None:
        self.verbose = verbose
        self.debug = debug
        self._rendered_structured_steps: set[tuple[str, str]] = set()
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
            "technical_analysis_start": self._render_agent_phase_start,
            "technical_analysis_complete": self._render_agent_phase_complete,
            "fundamental_analysis_start": self._render_agent_phase_start,
            "fundamental_analysis_complete": self._render_agent_phase_complete,
            "sentiment_analysis_start": self._render_agent_phase_start,
            "sentiment_analysis_complete": self._render_agent_phase_complete,
            "debate_start": self._render_agent_phase_start,
            "debate_complete": self._render_agent_phase_complete,
            "risk_analysis_start": self._render_agent_phase_start,
            "risk_analysis_complete": self._render_agent_phase_complete,
            "portfolio_decision_start": self._render_agent_phase_start,
            "portfolio_decision_complete": self._render_portfolio_decision_complete,
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
            _format_table(
                ["指标", "值"],
                [
                    ["累计经验", payload.get("total_experiences", 0)],
                    ["进度", f"{payload.get('progress', 0)}/{payload.get('threshold', 30)}"],
                    ["是否可分析", "是" if payload.get("ready") else "否"],
                    ["成功率", _percent(payload.get("success_rate", 0.0))],
                    ["平均收益", f"{_float_text(payload.get('average_return_pct', 0.0))}%"],
                ],
            )
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
        rows = []
        for index, item in enumerate(suggestions, 1):
            rows.append(
                [
                    index,
                    item.get("agent_id", ""),
                    item.get("section", ""),
                    item.get("metric", ""),
                    item.get("current_value", ""),
                    item.get("suggested_value", ""),
                    _percent(item.get("confidence", 0.0)),
                    item.get("reason", ""),
                ]
            )
        lines = [f"分析时间: {payload.get('analyzed_at', '')}", f"建议数: {len(suggestions)}", ""]
        lines.append(_format_table(["#", "Agent", "段落", "指标", "当前", "建议", "置信度", "原因"], rows, max_width=24))
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
            rows = []
            for item in providers:
                if isinstance(item, dict):
                    rows.append(
                        [
                            item.get("name", ""),
                            item.get("configured", ""),
                            item.get("available", ""),
                            item.get("reason", ""),
                        ]
                    )
            lines.append(_format_table(["Provider", "已配置", "可用", "原因"], rows, max_width=32))
        self.print_info("数据源状态", "\n".join(lines))

    def render_datasource_tests(self, payload: dict[str, Any]) -> None:
        items = payload.get("items", []) if isinstance(payload, dict) else []
        lines = [f"测试股票: {payload.get('stock_code', '')}", f"历史窗口: {payload.get('days', '')} 天", ""]
        provider_rows = []
        check_rows = []
        matrix_rows = []
        diagnosis_lines = []
        for item in items:
            if not isinstance(item, dict):
                continue
            compact = _compact_error(item.get("message", "")) if item.get("status") == "error" else {}
            provider_rows.append(
                [
                    item.get("source", ""),
                    item.get("status", ""),
                    compact.get("code", ""),
                    compact.get("reason", item.get("message", "")),
                ]
            )
            for check in item.get("checks", []) if isinstance(item.get("checks"), list) else []:
                if isinstance(check, dict):
                    compact_check = _compact_error(check.get("detail", "")) if check.get("status") == "error" else {}
                    check_rows.append(
                        [
                            item.get("source", ""),
                            check.get("operation", ""),
                            check.get("status", ""),
                            compact_check.get("code", ""),
                            compact_check.get("reason", check.get("detail", "")),
                        ]
                    )
            for matrix_item in item.get("matrix", []) if isinstance(item.get("matrix"), list) else []:
                if isinstance(matrix_item, dict):
                    matrix_rows.append(
                        [
                            matrix_item.get("stock_code", ""),
                            matrix_item.get("symbol", ""),
                            matrix_item.get("operation", ""),
                            matrix_item.get("status", ""),
                            matrix_item.get("detail", matrix_item.get("message", "")),
                        ]
                    )
            diagnosis = item.get("diagnosis", [])
            if isinstance(diagnosis, list):
                diagnosis_lines.extend(str(entry) for entry in diagnosis if str(entry).strip())
        lines.append("Provider 总览")
        lines.append(_format_table(["数据源", "状态", "错误码", "中文原因/结果"], provider_rows, max_width=30))
        if check_rows:
            lines.extend(["", "检查项明细", _format_table(["数据源", "检查项", "状态", "错误码", "结果"], check_rows, max_width=28)])
        if matrix_rows:
            lines.extend(["", "iFinD 多格式矩阵", _format_table(["股票", "格式", "检查项", "状态", "结果"], matrix_rows, max_width=26)])
        if diagnosis_lines:
            lines.extend(["", "iFinD 诊断结论", *[f"- {entry}" for entry in diagnosis_lines[:4]]])
        self.print_info("数据源 smoke 测试", "\n".join(lines).strip())

    def render_sync_local(self, payload: dict[str, Any]) -> None:
        items = payload.get("items", []) if isinstance(payload, dict) else []
        lines = [
            f"状态: {payload.get('status', '')}",
            f"本地库: {payload.get('db_path', '')}",
            f"同步模式: {payload.get('sync_mode', '')}    策略: {payload.get('provider_strategy', '')}",
            f"目标股票数: {payload.get('selected_count', payload.get('max_stocks', ''))} / 股票池: {payload.get('universe_total', '')}",
            f"历史窗口: {payload.get('days', '')} 天",
            "",
        ]
        stored = payload.get("stored", {}) if isinstance(payload.get("stored"), dict) else {}
        stats = payload.get("local_stats", {}) if isinstance(payload.get("local_stats"), dict) else {}
        lines.append("写入汇总")
        lines.append(
            _format_table(
                ["项目", "本轮写入", "本地总量"],
                [
                    ["股票", stored.get("stocks", 0), stats.get("stocks", 0)],
                    ["K线", stored.get("history", 0), stats.get("bars", 0)],
                    ["行情", stored.get("quote", 0), stats.get("quotes", 0)],
                    ["财务", stored.get("financial", 0), stats.get("financials", 0)],
                ],
            )
        )
        participation = payload.get("provider_participation", [])
        if isinstance(participation, list) and participation:
            lines.extend(["", "Provider 参与表"])
            lines.append(
                _format_table(
                    ["Provider", "操作", "状态", "次数", "写入"],
                    [
                        [
                            item.get("source", ""),
                            item.get("operation", ""),
                            item.get("status", ""),
                            item.get("count", 0),
                            item.get("stored", 0),
                        ]
                        for item in participation
                        if isinstance(item, dict)
                    ],
                )
            )
        errors = [item for item in items if isinstance(item, dict) and item.get("status") == "error"]
        if errors:
            lines.extend(["", "压缩错误（最多 8 条）"])
            lines.append(
                _format_table(
                    ["股票", "操作", "错误码", "中文原因"],
                    [
                        [
                            item.get("stock_code", ""),
                            item.get("operation", ""),
                            _compact_error(item.get("detail", item.get("message", ""))).get("code", ""),
                            _compact_error(item.get("detail", item.get("message", ""))).get("reason", ""),
                        ]
                        for item in errors[:8]
                    ],
                    max_width=30,
                )
            )
        self.print_info("本地市场数据同步", "\n".join(lines).strip())

    def render_local_market_status(self, payload: dict[str, Any]) -> None:
        stats = payload.get("local_stats", {}) if isinstance(payload.get("local_stats"), dict) else {}
        recent = payload.get("recent_sync_runs", []) if isinstance(payload.get("recent_sync_runs"), list) else []
        lines = [
            f"本地库: {payload.get('db_path', stats.get('path', ''))}",
            f"是否存在: {'是' if stats.get('exists') else '否'}",
            f"最近同步: {stats.get('latest_sync_at', '') or '(暂无同步记录)'}",
            f"Provider 链: {', '.join(payload.get('provider_chain', []) or [])}",
            "",
            "库存统计",
            _format_table(
                ["项目", "数量"],
                [
                    ["股票", stats.get("stocks", 0)],
                    ["K线", stats.get("bars", 0)],
                    ["行情", stats.get("quotes", 0)],
                    ["财务", stats.get("financials", 0)],
                    ["同步记录", stats.get("sync_runs", 0)],
                ],
            ),
        ]
        if recent:
            lines.extend(["", "最近同步记录（最多 10 条）"])
            lines.append(
                _format_table(
                    ["时间", "Provider", "操作", "股票", "状态", "说明"],
                    [
                        [
                            item.get("created_at", ""),
                            item.get("source", ""),
                            item.get("operation", ""),
                            item.get("stock_code", ""),
                            item.get("status", ""),
                            _compact_error(item.get("detail", "")).get("reason", item.get("detail", "")) if item.get("status") == "error" else item.get("detail", ""),
                        ]
                        for item in recent
                        if isinstance(item, dict)
                    ],
                    max_width=24,
                )
            )
        else:
            lines.append("\n最近同步记录: 暂无；请先执行本页面的同步功能。")
        self.print_info("本地市场数据状态", "\n".join(lines).strip())

    def render_result_summary(self, payload: dict[str, Any]) -> None:
        agents = payload.get("agents", []) if isinstance(payload.get("agents"), list) else []
        rankings = payload.get("rankings", []) if isinstance(payload.get("rankings"), list) else []
        lines = [f"运行日期: {payload.get('run_date', '')}", f"模型数: {len(agents)}"]
        if rankings:
            lines.append("")
            lines.append("收益排行:")
            rows = []
            for item in rankings:
                if isinstance(item, dict):
                    model = item.get("llm_model", item.get("model", ""))
                    ret = item.get("total_return", item.get("return", 0.0))
                    rows.append([item.get("rank", ""), model, _percent(ret), _float_text(item.get("cash", "")), _float_text(item.get("equity", ""))])
            lines.append(_format_table(["排名", "模型", "收益", "现金", "权益"], rows, max_width=28))
        if agents:
            account_rows = []
            position_rows = []
            trade_rows = []
            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                model = agent.get("llm_model", agent.get("model", ""))
                positions = agent.get("positions", []) if isinstance(agent.get("positions"), list) else []
                trades = agent.get("trades", []) if isinstance(agent.get("trades"), list) else []
                account_rows.append(
                    [
                        model,
                        _float_text(agent.get("equity", "")),
                        _float_text(agent.get("cash", "")),
                        _percent(agent.get("total_return", 0.0)),
                        _float_text(agent.get("daily_pnl", 0.0)),
                        len(positions),
                        f"{agent.get('buy_count', 0)}/{agent.get('sell_count', 0)}",
                        agent.get("total_trades", len(trades)),
                    ]
                )
                for position in positions[:8]:
                    if not isinstance(position, dict):
                        continue
                    position_rows.append(
                        [
                            model,
                            position.get("stock_code", ""),
                            position.get("shares", ""),
                            _float_text(position.get("current_price", "")),
                            _float_text(position.get("market_value", "")),
                            _percent(position.get("unrealized_return", 0.0)),
                        ]
                    )
                for trade in trades[-8:]:
                    if not isinstance(trade, dict):
                        continue
                    trade_rows.append(
                        [
                            model,
                            trade.get("date", ""),
                            trade.get("stock_code", ""),
                            trade.get("side", ""),
                            _float_text(trade.get("price", "")),
                            trade.get("shares", ""),
                            _float_text(trade.get("realized_pnl", 0.0)),
                        ]
                    )
            lines.extend(["", "账户看板:"])
            lines.append(_format_table(["模型", "权益", "现金", "收益", "本轮PnL", "持仓", "买/卖", "成交"], account_rows, max_width=24))
            lines.extend(["", "当前持仓:"])
            if position_rows:
                lines.append(_format_table(["模型", "股票", "股数", "现价", "市值", "浮盈%"], position_rows, max_width=22))
            else:
                lines.append("空仓：本轮没有可展示持仓。")
            lines.extend(["", "最近交易:"])
            if trade_rows:
                lines.append(_format_table(["模型", "日期", "股票", "方向", "价格", "股数", "已实现PnL"], trade_rows, max_width=20))
            else:
                lines.append("无成交：本轮没有买入/卖出记录。")
        insights = _benchmark_insights(payload)
        if insights:
            lines.append("")
            lines.extend(insights)
        learning = payload.get("learning")
        if isinstance(learning, dict):
            lines.append("")
            lines.append("学习结果:")
            lines.append(
                _format_table(
                    ["指标", "值"],
                    [
                        ["状态", learning.get("status", "")],
                        ["本轮经验", learning.get("experiences_recorded", learning.get("experience_count", ""))],
                        ["建议数", len(learning.get("suggestions", []) or []) if isinstance(learning.get("suggestions", []), list) else ""],
                        ["原因", learning.get("reason", learning.get("message", ""))],
                    ],
                    max_width=34,
                )
            )
        self.print_info("运行完成", "\n".join(lines))

    def _render_run_start(self, event: AgentEvent) -> None:
        self.print_info("启动运行", event.payload.get("message", "开始运行"))

    def _render_run_complete(self, event: AgentEvent) -> None:
        self.print_info("运行事件", event.payload.get("message", "运行完成"))

    def _render_error(self, event: AgentEvent) -> None:
        compact = _compact_error(event.payload.get("message", ""), retry=event.payload.get("retry", "0/0"))
        self._print(f"[red]{compact.get('code')}[/red] {compact.get('reason')} retry={compact.get('retry')}")

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

    def _render_agent_phase_start(self, event: AgentEvent) -> None:
        title = _phase_title(event)
        self._print(f"[blue]{title}[/blue] {event.payload.get('message', '')}")

    def _render_agent_phase_complete(self, event: AgentEvent) -> None:
        title = _phase_title(event)
        stock_code = str(event.payload.get("stock_code", ""))
        result = _as_dict(event.payload.get("result"))
        if result:
            self._print(f"[cyan]{title}[/cyan] {stock_code} {result.get('label', '')} score={_percent(result.get('score', 0.0))}")
        else:
            self._print(f"[cyan]{title}[/cyan] {event.payload.get('message', '')}")
        details = _render_phase_details(title, result, event.payload.get("objective_data", {}))
        if details:
            self.print_info(f"{title} 明细", details)
        self._rendered_structured_steps.add(_event_step_key(event))

    def _render_portfolio_decision_complete(self, event: AgentEvent) -> None:
        title = _phase_title(event)
        decision = _as_dict(event.payload.get("decision"))
        stock_code = str(event.payload.get("stock_code", decision.get("stock_code", "")))
        self._print(
            f"[yellow]{title}[/yellow] {stock_code} {decision.get('action', '')} "
            f"置信度={_percent(decision.get('confidence', 0.0))} 仓位={_percent(decision.get('position_size', 0.0))}"
        )
        body = _render_decision_evidence(decision)
        if body:
            self.print_info(f"决策客观依据 {stock_code}", body)
        self._rendered_structured_steps.add(_event_step_key(event))

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
        data_sources = event.payload.get("data_sources", []) if isinstance(event.payload.get("data_sources"), list) else []
        if data_sources:
            lines.extend(["", "数据源调用链:"])
            for item in data_sources[-8:]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('operation', '')}: {item.get('source', '')} "
                        f"{item.get('status', '')} {item.get('detail', item.get('reason', ''))}"
                    )
        if bars:
            lines.extend(["", render_kline_ascii(bars), "", render_technical_indicators(bars)])
        if financial:
            lines.extend(["", render_financial_table(financial)])
        self.print_info("客观数据快照", "\n".join(item for item in lines if item))

    def _render_agent_chain_step(self, event: AgentEvent) -> None:
        step = str(event.payload.get("chain_step", ""))
        title = _chain_step_title(step)
        if _event_step_key(event) in self._rendered_structured_steps and not self.verbose:
            return
        result = _as_dict(event.payload.get("result"))
        if result:
            self._print(
                f"[cyan]{title}[/cyan] {event.payload.get('stock_code', '')} "
                f"{result.get('label', '')} score={_percent(result.get('score', 0.0))}"
            )
        else:
            self._print(f"[cyan]{title}[/cyan] {event.payload.get('message', '')}")
        if result:
            details = _render_phase_details(title, result, event.payload.get("objective_data", {}), include_kline=self.verbose)
            if details:
                self.print_info(f"{title} 明细", details)

    def _render_analysis_complete(self, event: AgentEvent) -> None:
        report = event.payload.get("report", {}) if isinstance(event.payload.get("report"), dict) else {}
        decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
        suffix = ""
        if decision:
            suffix = f" action={decision.get('action', '')} confidence={_percent(decision.get('confidence', 0.0))}"
        self._print(f"[green]分析完成[/green] {event.payload.get('message', '')}{suffix}")
        objective = event.payload.get("objective_data", {}) if isinstance(event.payload.get("objective_data"), dict) else {}
        agent_chain = event.payload.get("agent_chain", {}) if isinstance(event.payload.get("agent_chain"), dict) else {}
        overview = _render_analysis_overview(report, objective, agent_chain)
        if overview:
            self.print_info(f"分析总览 {event.payload.get('stock_code', '')}", overview)

    def _render_decision(self, event: AgentEvent) -> None:
        decision = _as_dict(event.payload.get("decision")) or _as_dict(event.payload)
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


_EVENT_STEP_MAP = {
    "technical_analysis_start": "technical_analyst",
    "technical_analysis_complete": "technical_analyst",
    "fundamental_analysis_start": "fundamental_analyst",
    "fundamental_analysis_complete": "fundamental_analyst",
    "sentiment_analysis_start": "sentiment_analyst",
    "sentiment_analysis_complete": "sentiment_analyst",
    "debate_start": "debate_room",
    "debate_complete": "debate_room",
    "risk_analysis_start": "risk_manager",
    "risk_analysis_complete": "risk_manager",
    "portfolio_decision_start": "portfolio_manager",
    "portfolio_decision_complete": "portfolio_manager",
}


def _phase_title(event: AgentEvent) -> str:
    return _chain_step_title(_EVENT_STEP_MAP.get(event.type, event.stage or str(event.payload.get("chain_step", ""))))


def _chain_step_title(step: str) -> str:
    titles = {
        "technical": "技术分析 (TechnicalAnalyst)",
        "technical_analyst": "技术分析 (TechnicalAnalyst)",
        "fundamental": "基本面分析 (FundamentalAnalyst)",
        "fundamental_analyst": "基本面分析 (FundamentalAnalyst)",
        "sentiment": "舆情分析 (SentimentAnalyst)",
        "sentiment_analyst": "舆情分析 (SentimentAnalyst)",
        "debate": "多Agent辩论 (DebateRoom)",
        "debate_room": "多Agent辩论 (DebateRoom)",
        "risk": "风控评估 (RiskManager)",
        "risk_manager": "风控评估 (RiskManager)",
        "portfolio": "最终决策 (PortfolioManager)",
        "portfolio_manager": "最终决策 (PortfolioManager)",
    }
    return titles.get(step, step or "Agent 步骤")


def _event_step_key(event: AgentEvent) -> tuple[str, str]:
    stock_code = str(event.payload.get("stock_code", ""))
    step = str(event.payload.get("chain_step") or _EVENT_STEP_MAP.get(event.type, event.stage or ""))
    return stock_code, step


def _render_phase_details(title: str, result: dict[str, Any], objective_data: Any, *, include_kline: bool = False) -> str:
    objective = _as_dict(objective_data)
    details: list[str] = []
    if result:
        details.append(render_analysis_result(title, result))
    bars = objective.get("bars", []) if isinstance(objective.get("bars"), list) else []
    if bars:
        details.extend(["", render_technical_indicators(bars)])
        if include_kline:
            details.extend(["", render_kline_ascii(bars)])
    financial = _as_dict(objective.get("financial"))
    if financial:
        details.extend(["", render_financial_table(financial)])
    news = objective.get("news") if "news" in objective else None
    if news:
        details.extend(["", render_news_list(news)])
    return "\n".join(item for item in details if str(item).strip()).strip()


def _render_analysis_overview(report: dict[str, Any], objective: dict[str, Any], agent_chain: dict[str, Any]) -> str:
    """Render the full evidence board for one analyzed stock."""
    stock = _dict_or_empty(objective.get("stock")) or _dict_or_empty(report.get("stock"))
    quote = _dict_or_empty(objective.get("quote")) or _dict_or_empty(report.get("quote"))
    financial = _dict_or_empty(objective.get("financial")) or _dict_or_empty(report.get("financial"))
    bars = objective.get("bars", []) if isinstance(objective.get("bars"), list) else []
    news = objective.get("news") if "news" in objective else None
    if news is None:
        sentiment = _dict_or_empty(report.get("sentiment"))
        metadata = _dict_or_empty(sentiment.get("metadata"))
        news = metadata.get("news") or metadata.get("news_items") or metadata.get("articles") or sentiment.get("reasons")

    sections: list[str] = []
    if stock or quote or financial:
        sections.extend(["【公司与行情】", render_company_info(stock, quote, financial)])
    if bars:
        sections.extend(["", "【时间序列 / K线】", render_kline_ascii(bars), "", "【技术指标】", render_technical_indicators(bars)])
    if financial:
        sections.extend(["", "【财务与估值】", render_financial_table(financial)])
    if news:
        sections.extend(["", "【舆情 / 新闻】", render_news_list(news)])

    chain_lines = _render_agent_chain_summary(report, agent_chain)
    if chain_lines:
        sections.extend(["", "【Agent 协作链】", *chain_lines])

    decision = _dict_or_empty(report.get("decision"))
    if decision:
        reasons = decision.get("reasons") if isinstance(decision.get("reasons"), list) else []
        reason_text = decision.get("rationale") or decision.get("reason") or "；".join(str(item) for item in reasons[:3])
        sections.extend(
            [
                "",
                "【最终决策】",
                f"动作: {decision.get('action', '')}  置信度: {_percent(decision.get('confidence', 0.0))}  仓位: {_percent(decision.get('position_size', 0.0))}",
                f"理由: {reason_text}",
            ]
        )
    return "\n".join(str(item) for item in sections if str(item).strip())


def _render_decision_evidence(decision: dict[str, Any]) -> str:
    """Render the evidence blocks requested by PortfolioManager."""
    explanation = _as_dict(decision.get("explanation_data"))
    objective = _as_dict(explanation.get("objective_data"))
    requested_sections = set(explanation.get("sections", [])) if isinstance(explanation.get("sections"), list) else set()
    lines: list[str] = []
    highlights = explanation.get("highlights", []) if isinstance(explanation.get("highlights"), list) else []
    if highlights:
        lines.append("【Agent建议展示的数据】")
        lines.extend(f"- {item}" for item in highlights[:5])
    reasons = decision.get("reasons", []) if isinstance(decision.get("reasons"), list) else []
    if reasons:
        lines.extend(["", "【决策理由】"])
        lines.extend(f"- {item}" for item in reasons[:5])
    risk_notes = decision.get("risk_notes", []) if isinstance(decision.get("risk_notes"), list) else []
    if risk_notes:
        lines.extend(["", "【风险提示】"])
        lines.extend(f"- {item}" for item in risk_notes[:4])

    stock = _as_dict(objective.get("stock"))
    quote = _as_dict(objective.get("quote"))
    financial = _as_dict(objective.get("financial"))
    bars = objective.get("bars", []) if isinstance(objective.get("bars"), list) else []
    news = objective.get("news") if "news" in objective else None

    if ("company" in requested_sections or "quote" in requested_sections) and (stock or quote or financial):
        lines.extend(["", "【公司与行情】", render_company_info(stock, quote, financial)])
    if "kline" in requested_sections and bars:
        lines.extend(["", "【K线】", render_kline_ascii(bars)])
    if "technical_indicators" in requested_sections and bars:
        lines.extend(["", "【技术指标】", render_technical_indicators(bars)])
    if "financial" in requested_sections and financial:
        lines.extend(["", "【财务与估值】", render_financial_table(financial)])
    if "sentiment" in requested_sections and news:
        lines.extend(["", "【舆情 / 新闻】", render_news_list(news)])

    agent_scores = explanation.get("agent_scores", {}) if isinstance(explanation.get("agent_scores"), dict) else {}
    if agent_scores:
        lines.extend(["", "【Agent 分数】"])
        for key, score in agent_scores.items():
            lines.append(f"- {key}: {_percent(score)}")
    agent_chain = explanation.get("agent_chain", {}) if isinstance(explanation.get("agent_chain"), dict) else {}
    if "agent_chain" in requested_sections and agent_chain:
        chain_lines = _render_agent_chain_summary({}, agent_chain)
        if chain_lines:
            lines.extend(["", "【Agent 协作链】", *chain_lines])
    return "\n".join(str(item) for item in lines if str(item).strip()).strip()


def _render_agent_chain_summary(report: dict[str, Any], agent_chain: dict[str, Any]) -> list[str]:
    """Render concise per-agent scores and reasons from the current report."""
    chain = agent_chain if isinstance(agent_chain, dict) else {}
    fallback_map = {
        "technical": report.get("technical"),
        "fundamental": report.get("fundamental"),
        "sentiment": report.get("sentiment"),
        "debate": report.get("debate"),
        "risk": report.get("risk"),
    }
    labels = [
        ("technical", "技术分析"),
        ("fundamental", "基本面分析"),
        ("sentiment", "舆情分析"),
        ("debate", "多Agent辩论"),
        ("risk", "风控评估"),
    ]
    lines: list[str] = []
    for key, title in labels:
        result = _dict_or_empty(chain.get(key)) or _dict_or_empty(fallback_map.get(key))
        if not result:
            continue
        score = result.get("score", result.get("risk_score", 0.0))
        label = result.get("label", result.get("recommendation", ""))
        lines.append(f"- {title}: {label}  评分={_percent(score)}")
        reasons = result.get("reasons") or []
        if isinstance(reasons, list):
            for reason in reasons[:2]:
                lines.append(f"  + {reason}")
        risks = result.get("risks") or []
        if isinstance(risks, list):
            for risk in risks[:1]:
                lines.append(f"  - {risk}")
    return lines


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    if is_dataclass(value):
        return asdict(value)
    return {}


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


def _ifind_symbol_candidates(stock_code: str) -> list[str]:
    raw = str(stock_code or "").strip().upper()
    if not raw:
        raw = "600519"
    code = raw
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix) and len(code) > 2:
            code = code[2:]
    if "." in code:
        code = code.split(".", 1)[0]
    market = "SH" if code.startswith("6") else "SZ" if code.startswith(("0", "3")) else "BJ" if code.startswith(("4", "8")) else ""
    candidates = [raw, code]
    if market:
        candidates.extend([f"{code}.{market}", f"{market}{code}"])
        if market == "SH":
            candidates.append(f"{code}.SS")
        elif market == "SZ":
            candidates.extend([f"{code}.SZ", f"{code}.XSHE"])
    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique[:5]


def _test_ifind_matrix(
    settings: Any,
    *,
    stock_code: str,
    days: int,
    checks: list[str] | None = None,
    timeout_seconds: float = 8.0,
) -> list[dict[str, Any]]:
    operations = [item for item in checks or ["history", "quote"] if item in {"history", "quote"}]
    if not operations:
        operations = ["history", "quote"]
    stock_codes = []
    for item in [stock_code, "600519", "000001", "600036"]:
        code = str(item or "").strip()
        if code and code not in stock_codes:
            stock_codes.append(code)
    rows: list[dict[str, Any]] = []
    for code in stock_codes[:3]:
        for symbol in _ifind_symbol_candidates(code)[:4]:
            for operation in operations:
                result = _test_one_datasource(
                    settings,
                    source="ifind",
                    stock_code=symbol,
                    days=days,
                    checks=[operation],
                    include_universe=False,
                    timeout_seconds=timeout_seconds,
                )
                checks_result = result.get("checks", []) if isinstance(result.get("checks"), list) else []
                first = checks_result[0] if checks_result and isinstance(checks_result[0], dict) else {}
                rows.append(
                    {
                        "stock_code": code,
                        "symbol": symbol,
                        "operation": operation,
                        "status": first.get("status", result.get("status", "error")),
                        "detail": first.get("detail", result.get("message", "")),
                    }
                )
    return rows


def _ifind_matrix_has_success(matrix: list[dict[str, Any]]) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "ok" for item in matrix)


def _ifind_failure_diagnosis(preflight: dict[str, Any], matrix: list[dict[str, Any]]) -> list[str]:
    """Summarize iFinD matrix failures without exposing token values."""
    details = " ".join(str(item.get("detail", "")) for item in matrix if isinstance(item, dict)).lower()
    details = f"{details} {preflight.get('message', '')}".lower()
    if "401" in details or "403" in details or "unauthorized" in details or "forbidden" in details or "权限" in details or "鉴权" in details:
        return ["多股票/多格式均失败，且错误指向鉴权或权限；请核对 access_token、账号 QuantAPI 权限和接口额度。"]
    if "timeout" in details or "timed out" in details or "超时" in details:
        return ["多股票/多格式请求超时；请检查 iFinD QuantAPI 网络可达性或调大 timeout 后重试。"]
    empty_count = sum(1 for item in matrix if isinstance(item, dict) and item.get("status") == "empty")
    error_count = sum(1 for item in matrix if isinstance(item, dict) and item.get("status") == "error")
    if empty_count and empty_count >= max(1, len(matrix) // 2):
        return ["矩阵多数为空返回；更像是指标权限/接口口径问题，不像单只股票代码格式问题。"]
    if error_count:
        return ["矩阵已覆盖 600519/000001/600036 与 SH/SZ 前后缀格式；若全部报错，优先排查 base URL、token 权限或账号服务开通状态。"]
    return ["iFinD 自检未通过；请查看 matrix 每行的 symbol/status/detail 区分格式、空返回和权限问题。"]


def _sync_one_operation_with_strategy(
    settings: Any,
    agent: DataAgent,
    store: LocalMarketStore,
    payload: dict[str, Any],
    *,
    operation: str,
    stock_code: str,
    days: int,
    counts: dict[str, int],
    provider_strategy: str,
) -> None:
    if provider_strategy != "all-providers":
        _sync_one_operation(agent, store, payload, operation=operation, stock_code=stock_code, days=days, counts=counts)
        return
    for source in getattr(settings.data, "provider_chain", []) or []:
        source = normalize_provider_name(source)
        if not provider_supports(source, operation):
            payload["items"].append(
                {"operation": operation, "stock_code": stock_code, "status": "skipped", "source": source, "detail": "capability not supported"}
            )
            continue
        scoped = copy.deepcopy(settings)
        scoped.data.mode = "online"
        scoped.data.provider_chain = [source]
        scoped_agent = DataAgent(settings=scoped, use_local_store=False, local_store_path=store.path)
        _sync_one_operation(scoped_agent, store, payload, operation=operation, stock_code=stock_code, days=days, counts=counts)


def _provider_participation(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "provider_chain")
        operation = str(item.get("operation") or "")
        status = str(item.get("status") or "")
        key = (source, operation, status)
        row = grouped.setdefault(key, {"source": source, "operation": operation, "status": status, "count": 0, "stored": 0})
        row["count"] += 1
        try:
            row["stored"] += int(item.get("stored", 0) or 0)
        except (TypeError, ValueError):
            pass
    return sorted(grouped.values(), key=lambda row: (row.get("source", ""), row.get("operation", ""), row.get("status", "")))


def _sync_one_operation(
    agent: DataAgent,
    store: LocalMarketStore,
    payload: dict[str, Any],
    *,
    operation: str,
    stock_code: str,
    days: int,
    counts: dict[str, int],
) -> None:
    before = _provider_attempt_count(agent)
    try:
        if operation == "history":
            bars = agent.get_history(stock_code, days=days)
            source = _latest_success_source(agent, operation="history", attempts_before=before)
            if bars and source:
                stored = store.upsert_history(stock_code, bars, source=source)
                counts["history"] += stored
                store.record_sync(source=source, operation="history", stock_code=stock_code, status="ok", detail=f"{stored} bars")
                payload["items"].append({"operation": "history", "stock_code": stock_code, "status": "ok", "source": source, "stored": stored})
            else:
                payload["items"].append({"operation": "history", "stock_code": stock_code, "status": "skipped", "detail": "no online provider success"})
            return
        if operation == "quote":
            quote = agent.get_quote(stock_code)
            source = _latest_success_source(agent, operation="quote", attempts_before=before)
            if quote.price > 0 and source:
                stored = store.upsert_quote(quote, source=source)
                counts["quote"] += stored
                store.record_sync(source=source, operation="quote", stock_code=stock_code, status="ok", detail=f"price={quote.price}")
                payload["items"].append({"operation": "quote", "stock_code": stock_code, "status": "ok", "source": source, "stored": stored})
            else:
                payload["items"].append({"operation": "quote", "stock_code": stock_code, "status": "skipped", "detail": "no online provider success"})
            return
        if operation == "financial":
            snapshot = agent.get_financial(stock_code)
            source = _latest_success_source(agent, operation="financial", attempts_before=before)
            if snapshot.stock_code and source:
                stored = store.upsert_financial(snapshot, source=source)
                counts["financial"] += stored
                store.record_sync(source=source, operation="financial", stock_code=stock_code, status="ok", detail=f"pe={snapshot.pe_ttm}")
                payload["items"].append({"operation": "financial", "stock_code": stock_code, "status": "ok", "source": source, "stored": stored})
            else:
                payload["items"].append({"operation": "financial", "stock_code": stock_code, "status": "skipped", "detail": "no online provider success"})
            return
    except Exception as exc:
        store.record_sync(source="provider_chain", operation=operation, stock_code=stock_code, status="error", detail=str(exc))
        payload["items"].append({"operation": operation, "stock_code": stock_code, "status": "error", "detail": str(exc)[:300]})


def _latest_success_source(agent: DataAgent, *, operation: str, attempts_before: int) -> str:
    attempts = agent.provider_diagnostics().get("attempts", [])
    if not isinstance(attempts, list):
        return ""
    ignored_sources = {"offline", "cache", "file_cache", "local_market"}
    for item in reversed([entry for entry in attempts[attempts_before:] if isinstance(entry, dict)]):
        if item.get("operation") == operation and item.get("status") == "ok":
            source = str(item.get("source", ""))
            if source and source not in ignored_sources:
                return source
    return ""


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


def _sleep_with_countdown(renderer: RichEventRenderer, interval_seconds: float) -> None:
    """Sleep between continuous rounds while keeping a visible countdown."""
    remaining = max(0, int(interval_seconds))
    if remaining <= 0:
        return
    next_notice = remaining
    while remaining > 0:
        if remaining == next_notice or remaining <= 10:
            renderer.print_info("连续运行倒计时", f"距离下一轮还有 {remaining} 秒；按 Ctrl+C 可停止。")
            next_notice = max(10, remaining // 2)
        sleep_for = min(10, remaining)
        time.sleep(sleep_for)
        remaining -= sleep_for


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
