"""Command line interface for the A-share agent system MVP."""

from __future__ import annotations

import argparse
import json

from astock_agent_system.agents import (
    DebateRoom,
    FundamentalAnalyst,
    MasterAgent,
    PortfolioManager,
    RiskManager,
    SentimentAnalyst,
    StockScreener,
    TechnicalAnalyst,
)
from astock_agent_system.backtest import BacktestEngine
from astock_agent_system.cli_enhanced import (
    cmd_agent_benchmark,
    cmd_agent_history,
    cmd_agent_learning_status,
    cmd_agent_learning_suggestions,
    cmd_agent_learning_trigger,
    cmd_agent_memory,
    cmd_agent_start,
    cmd_agent_status,
    cmd_agent_stop,
    cmd_datasource_status,
    cmd_datasource_test,
)
from astock_agent_system.config import load_settings
from astock_agent_system.data import DataAgent
from astock_agent_system.llm import LLMClient, ModelBench
from astock_agent_system.notification import build_notifier
from astock_agent_system.orchestrator import MultiAgentOrchestrator
from astock_agent_system.reporting import save_daily_report, save_stock_report
from astock_agent_system.scheduler import TradingTaskScheduler


def _cmd_config(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    payload = {
        "data_mode": settings.data.mode,
        "offline_data_path": settings.data.offline_data_path,
        "data": {
            "mode": settings.data.mode,
            "offline_data_path": settings.data.offline_data_path,
            "dynamic_universe_limit": settings.data.dynamic_universe_limit,
            "provider_chain": settings.data.provider_chain,
            "has_tushare_token": bool(settings.data.tushare_token),
            "has_alpha_vantage_api_key": bool(settings.data.alpha_vantage_api_key),
            "has_jqdata_username": bool(settings.data.jqdata_username),
            "has_jqdata_password": bool(settings.data.jqdata_password),
        },
        "initial_capital": settings.portfolio.initial_capital,
        "risk": {
            "max_position_per_stock": settings.risk.max_position_per_stock,
            "max_total_position": settings.risk.max_total_position,
            "stop_loss_pct": settings.risk.stop_loss_pct,
        },
        "llm": {
            "base_url": settings.llm.base_url,
            "has_api_key": bool(settings.llm.api_key),
            "default_model": settings.llm.default_model,
            "request_profile": settings.llm.request_profile,
            "max_tokens": settings.llm.max_tokens,
            "timeout_seconds": settings.llm.timeout_seconds,
        },
        "storage": {
            "mongo_uri": settings.storage.mongo_uri,
            "mongo_db": settings.storage.mongo_db,
            "mongo_timeout_ms": settings.storage.mongo_timeout_ms,
            "redis_url": settings.storage.redis_url,
        },
        "scheduler": {
            "enabled": settings.scheduler.enabled,
            "timezone": settings.scheduler.timezone,
            "daily_run_time": settings.scheduler.daily_run_time,
            "stop_loss_interval_minutes": settings.scheduler.stop_loss_interval_minutes,
            "notify_after_daily_run": settings.scheduler.notify_after_daily_run,
            "max_count": settings.scheduler.max_count,
            "history_days": settings.scheduler.history_days,
            "output_dir": settings.scheduler.output_dir,
            "models": settings.scheduler.models,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_screen(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    data_agent = DataAgent(settings=settings)
    screener = StockScreener(data_agent=data_agent)
    candidates = screener.screen(max_count=args.max_count, history_days=args.days)
    payload = {
        "count": len(candidates),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    report = MasterAgent(settings=settings).analyze_stock(args.stock_code, history_days=args.days)
    payload = report.to_dict()
    if args.save_report:
        payload["saved_files"] = save_stock_report(report, args.output_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_run_daily(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    report = MasterAgent(settings=settings).run_daily(max_count=args.max_count, history_days=args.days)
    saved_files = save_daily_report(report, args.output_dir)
    notification_results = []
    if args.notify:
        body = f"完成 {len(report.reports)} 只股票分析，报告：{saved_files['daily_markdown']}"
        notification_results = [item.to_dict() for item in build_notifier(settings).send("A股 Agent 每日分析完成", body)]
    payload = {
        "status": "ok",
        "run_date": report.run_date,
        "candidate_count": len(report.candidates),
        "report_count": len(report.reports),
        "saved_files": saved_files,
        "notification": notification_results,
        "summary": [
            {
                "stock_code": item.stock.stock_code,
                "stock_name": item.stock.stock_name,
                "action": item.decision.action if item.decision else None,
                "confidence": item.decision.confidence if item.decision else None,
                "position_size": item.decision.position_size if item.decision else None,
            }
            for item in report.reports
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _cmd_bench_models(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    client = LLMClient(settings)
    if args.list_models:
        payload = client.list_models_safe()
    else:
        models = _parse_models(args.models) if args.models else None
        payload = ModelBench(client).run(models=models, prompt=args.prompt, limit=args.limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    if args.initial_capital is not None:
        settings.portfolio.initial_capital = float(args.initial_capital)
    stock_codes = _parse_models(args.stock_codes) if args.stock_codes else None
    result = BacktestEngine(settings=settings).run(
        stock_codes=stock_codes,
        max_count=args.max_count,
        initial_capital=args.initial_capital,
        history_days=args.days,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_notify(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    results = build_notifier(settings).send(args.title, args.body)
    print(json.dumps({"results": [item.to_dict() for item in results]}, ensure_ascii=False, indent=2))
    return 0


def _cmd_storage_status(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    payload: dict[str, object] = {
        "status": "ok",
        "mongo": {
            "uri": settings.storage.mongo_uri,
            "db": settings.storage.mongo_db,
            "timeout_ms": settings.storage.mongo_timeout_ms,
            "dependency": "unknown",
            "connection": "unknown",
        },
        "redis": {
            "url": settings.storage.redis_url,
            "dependency": "unknown",
            "connection": "unknown",
        },
        "next_steps": [],
    }

    try:
        import pymongo  # type: ignore

        mongo_info = payload["mongo"] if isinstance(payload["mongo"], dict) else {}
        mongo_info["dependency"] = f"installed:{getattr(pymongo, 'version', 'unknown')}"
        try:
            from astock_agent_system.storage import MongoClient

            mongo = MongoClient(settings)
            mongo._get_db()  # noqa: SLF001 - diagnostic command intentionally pings the lazy client.
            mongo.close()
            mongo_info["connection"] = "ok"
        except Exception as exc:  # pragma: no cover - depends on local Docker
            mongo_info["connection"] = "error"
            mongo_info["reason"] = str(exc)
    except ImportError:
        mongo_info = payload["mongo"] if isinstance(payload["mongo"], dict) else {}
        mongo_info["dependency"] = "missing"
        mongo_info["connection"] = "skipped"

    try:
        import redis  # type: ignore

        redis_info = payload["redis"] if isinstance(payload["redis"], dict) else {}
        redis_info["dependency"] = f"installed:{getattr(redis, '__version__', 'unknown')}"
        try:
            from astock_agent_system.storage import RedisClient

            redis_client = RedisClient(settings)
            redis_client._get_client().ping()  # noqa: SLF001 - diagnostic command intentionally pings the lazy client.
            redis_client.close()
            redis_info["connection"] = "ok"
        except Exception as exc:  # pragma: no cover - depends on local Docker
            redis_info["connection"] = "error"
            redis_info["reason"] = str(exc)
    except ImportError:
        redis_info = payload["redis"] if isinstance(payload["redis"], dict) else {}
        redis_info["dependency"] = "missing"
        redis_info["connection"] = "skipped"

    next_steps: list[str] = []
    mongo = payload.get("mongo") if isinstance(payload, dict) else {}
    redis_payload = payload.get("redis") if isinstance(payload, dict) else {}
    if isinstance(mongo, dict) and mongo.get("dependency") == "missing":
        next_steps.append("Install storage dependencies: python -m pip install -e \".[storage]\"")
    if isinstance(redis_payload, dict) and redis_payload.get("dependency") == "missing":
        next_steps.append("Install storage dependencies: python -m pip install -e \".[storage]\"")
    if (isinstance(mongo, dict) and mongo.get("connection") != "ok") or (
        isinstance(redis_payload, dict) and redis_payload.get("connection") != "ok"
    ):
        next_steps.append("Start Docker Desktop, then run: docker compose up -d")
    payload["next_steps"] = list(dict.fromkeys(next_steps))

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if args.strict:
        mongo_ok = isinstance(mongo, dict) and mongo.get("connection") == "ok"
        redis_ok = isinstance(redis_payload, dict) and redis_payload.get("connection") == "ok"
        return 0 if mongo_ok and redis_ok else 1
    return 0


def _cmd_scheduler_run_daily(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    if args.max_count is not None:
        settings.scheduler.max_count = int(args.max_count)
    if args.days is not None:
        settings.scheduler.history_days = int(args.days)
    if args.output_dir:
        settings.scheduler.output_dir = args.output_dir
    result = TradingTaskScheduler(settings=settings).run_daily_analysis()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if result.status == "ok" else 1


def _cmd_scheduler_run_auto_investment(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    if args.max_count is not None:
        settings.scheduler.max_count = int(args.max_count)
    if args.days is not None:
        settings.scheduler.history_days = int(args.days)
    models = _parse_models(args.models) if args.models else None
    result = TradingTaskScheduler(settings=settings).run_auto_investment(models=models)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if result.status == "ok" else 1


def _cmd_scheduler_check_stop_loss(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    result = TradingTaskScheduler(settings=settings).check_stop_loss()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if result.status in {"ok", "alert"} else 1


def _cmd_scheduler_start(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    TradingTaskScheduler(settings=settings).run_forever()
    return 0


def _cmd_compete(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.offline:
        settings.data.mode = "offline"
    models = _parse_models(args.models) if args.models else None
    payload = MultiAgentOrchestrator(settings=settings).run_competition(
        models=models,
        max_count=args.max_count,
        history_days=args.days,
        initial_capital=args.initial_capital,
        persist=not args.no_persist,
        continue_from_storage=not args.fresh_start,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload.get("status") == "ok" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astock-agent",
        description="A-share multi-agent paper trading MVP",
    )
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser("config", help="Print effective non-secret settings")
    config_parser.set_defaults(func=_cmd_config)

    screen_parser = subparsers.add_parser("screen", help="Screen dynamic stock candidates")
    screen_parser.add_argument("--max-count", type=int, default=5, help="Maximum candidates to print")
    screen_parser.add_argument("--days", type=int, default=24, help="History days used for screening")
    screen_parser.set_defaults(func=_cmd_screen)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze one stock")
    analyze_parser.add_argument("stock_code", help="A-share stock code, e.g. 600519")
    analyze_parser.add_argument("--days", type=int, default=24, help="History days used for technical analysis")
    analyze_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    analyze_parser.add_argument("--save-report", action="store_true", help="Save JSON and Markdown reports")
    analyze_parser.add_argument("--output-dir", default="reports", help="Directory for saved reports")
    analyze_parser.set_defaults(func=_cmd_analyze)

    run_daily_parser = subparsers.add_parser("run-daily", help="Run daily analysis pipeline")
    run_daily_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    run_daily_parser.add_argument("--max-count", type=int, default=3, help="Maximum candidates to analyze")
    run_daily_parser.add_argument("--days", type=int, default=24, help="History days used for analysis")
    run_daily_parser.add_argument("--output-dir", default="reports", help="Directory for saved reports")
    run_daily_parser.add_argument("--notify", action="store_true", help="Send notification after report is saved")
    run_daily_parser.set_defaults(func=_cmd_run_daily)

    def _add_bench_parser(command_name: str, help_text: str) -> None:
        bench_parser = subparsers.add_parser(command_name, help=help_text)
        bench_parser.add_argument("--list-models", action="store_true", help="Only fetch and print /models")
        bench_parser.add_argument("--models", default="", help="Comma-separated model ids to test")
        bench_parser.add_argument("--limit", type=int, default=5, help="Maximum models to test")
        bench_parser.add_argument(
            "--prompt",
            default="请只输出 JSON：{\"score\": 0.5, \"label\": \"ok\", \"reason\": \"模型连通性测试\"}",
            help="Benchmark prompt. Keep it short to control cost.",
        )
        bench_parser.set_defaults(func=_cmd_bench_models)

    _add_bench_parser("bench", "Benchmark OpenAI-compatible models")
    _add_bench_parser("bench-models", "Benchmark OpenAI-compatible models (legacy alias)")
    backtest_parser = subparsers.add_parser("backtest", help="Run historical backtest")
    backtest_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    backtest_parser.add_argument("--initial-capital", type=float, default=None, help="Override initial capital")
    backtest_parser.add_argument("--max-count", type=int, default=3, help="Maximum screened stocks to backtest")
    backtest_parser.add_argument("--stock-codes", default="", help="Comma-separated stock codes; overrides screening")
    backtest_parser.add_argument("--days", type=int, default=24, help="History days used for backtest")
    backtest_parser.set_defaults(func=_cmd_backtest)

    notify_parser = subparsers.add_parser("notify", help="Send a test notification or safely skip when unconfigured")
    notify_parser.add_argument("--title", default="A股 Agent 通知测试", help="Notification title")
    notify_parser.add_argument("--body", default="通知通道连通性测试", help="Notification body")
    notify_parser.set_defaults(func=_cmd_notify)

    storage_parser = subparsers.add_parser("storage", help="Check MongoDB/Redis storage health")
    storage_subparsers = storage_parser.add_subparsers(dest="storage_command")
    storage_status_parser = storage_subparsers.add_parser("status", help="Print storage dependency and connection status")
    storage_status_parser.add_argument("--strict", action="store_true", help="Return non-zero unless MongoDB and Redis both connect")
    storage_status_parser.set_defaults(func=_cmd_storage_status)

    scheduler_parser = subparsers.add_parser("scheduler", help="Run automatic analysis and risk-check tasks")
    scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_command")

    scheduler_run_parser = scheduler_subparsers.add_parser("run-daily", help="Run scheduled daily analysis once")
    scheduler_run_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    scheduler_run_parser.add_argument("--max-count", type=int, default=None, help="Override scheduler max candidates")
    scheduler_run_parser.add_argument("--days", type=int, default=None, help="Override scheduler history days")
    scheduler_run_parser.add_argument("--output-dir", default="", help="Override scheduler output directory")
    scheduler_run_parser.set_defaults(func=_cmd_scheduler_run_daily)

    scheduler_auto_parser = scheduler_subparsers.add_parser(
        "run-auto-investment",
        help="Run scheduled automatic LLM paper-investment round once",
    )
    scheduler_auto_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    scheduler_auto_parser.add_argument("--models", default="", help="Comma-separated model ids; empty uses default model or rule baseline")
    scheduler_auto_parser.add_argument("--max-count", type=int, default=None, help="Override scheduler max candidates")
    scheduler_auto_parser.add_argument("--days", type=int, default=None, help="Override scheduler history days")
    scheduler_auto_parser.set_defaults(func=_cmd_scheduler_run_auto_investment)

    scheduler_stop_parser = scheduler_subparsers.add_parser("check-stop-loss", help="Check persisted positions for stop-loss triggers")
    scheduler_stop_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    scheduler_stop_parser.set_defaults(func=_cmd_scheduler_check_stop_loss)

    scheduler_start_parser = scheduler_subparsers.add_parser("start", help="Start APScheduler loop")
    scheduler_start_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    scheduler_start_parser.set_defaults(func=_cmd_scheduler_start)

    compete_parser = subparsers.add_parser("compete", help="Run multi-LLM independent paper-account competition")
    compete_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    compete_parser.add_argument("--models", default="", help="Comma-separated model ids; empty uses default model or rule baseline")
    compete_parser.add_argument("--max-count", type=int, default=3, help="Maximum candidates to analyze per model")
    compete_parser.add_argument("--days", type=int, default=24, help="History days used for analysis")
    compete_parser.add_argument("--initial-capital", type=float, default=None, help="Initial capital for each model account")
    compete_parser.add_argument("--fresh-start", action="store_true", help="Ignore stored snapshots and start each account from initial capital")
    compete_parser.add_argument("--no-persist", action="store_true", help="Do not write leaderboard/trades to MongoDB")
    compete_parser.set_defaults(func=_cmd_compete)

    agent_parser = subparsers.add_parser("agent", help="Run and inspect streaming model-driven agents")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    agent_start_parser = agent_subparsers.add_parser("start", help="Start a streaming agent run")
    agent_start_parser.add_argument("--model", default="", help="Single model id to run")
    agent_start_parser.add_argument("--models", default="", help="Comma-separated model ids; overrides --model")
    agent_start_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    agent_start_parser.add_argument("--max-count", type=int, default=3, help="Maximum candidates to analyze per model")
    agent_start_parser.add_argument("--days", type=int, default=24, help="History days used for analysis")
    agent_start_parser.add_argument("--initial-capital", type=float, default=None, help="Initial capital for each model account")
    agent_start_parser.add_argument("--fresh-start", action="store_true", help="Ignore stored snapshots and start from initial capital")
    agent_start_parser.add_argument("--no-persist", action="store_true", help="Do not write leaderboard/trades to MongoDB")
    agent_start_parser.add_argument("--no-learning", action="store_true", help="Do not record learning experiences for this run")
    agent_start_parser.add_argument("--verbose", action="store_true", help="Print verbose stream events")
    agent_start_parser.add_argument("--debug", action="store_true", help="Print raw JSON events")
    agent_start_parser.set_defaults(func=cmd_agent_start)

    agent_benchmark_parser = agent_subparsers.add_parser("benchmark", help="Run streaming multi-model benchmark")
    agent_benchmark_parser.add_argument("--models", default="", help="Comma-separated model ids")
    agent_benchmark_parser.add_argument("--offline", action="store_true", help="Force offline sample data mode")
    agent_benchmark_parser.add_argument("--max-count", type=int, default=3, help="Maximum candidates to analyze per model")
    agent_benchmark_parser.add_argument("--days", type=int, default=24, help="History days used for analysis")
    agent_benchmark_parser.add_argument("--initial-capital", type=float, default=None, help="Initial capital for each model account")
    agent_benchmark_parser.add_argument("--fresh-start", action="store_true", help="Ignore stored snapshots and start from initial capital")
    agent_benchmark_parser.add_argument("--no-persist", action="store_true", help="Do not write leaderboard/trades to MongoDB")
    agent_benchmark_parser.add_argument("--no-learning", action="store_true", help="Do not record learning experiences for this run")
    agent_benchmark_parser.add_argument("--verbose", action="store_true", help="Print verbose stream events")
    agent_benchmark_parser.add_argument("--debug", action="store_true", help="Print raw JSON events")
    agent_benchmark_parser.set_defaults(func=cmd_agent_benchmark)

    agent_status_parser = agent_subparsers.add_parser("status", help="Show account, learning, memory, and datasource status")
    agent_status_parser.add_argument("--model", default="", help="Model id to show")
    agent_status_parser.add_argument("--agent-id", default="", help="Memory scope to inspect")
    agent_status_parser.add_argument("--limit", type=int, default=20, help="Maximum memory cases to count")
    agent_status_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    agent_status_parser.set_defaults(func=cmd_agent_status)

    agent_history_parser = agent_subparsers.add_parser("history", help="Show local learning experience history")
    agent_history_parser.add_argument("--model", default="", help="Filter by model id")
    agent_history_parser.add_argument("--limit", type=int, default=20, help="Maximum experience rows")
    agent_history_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    agent_history_parser.set_defaults(func=cmd_agent_history)

    agent_stop_parser = agent_subparsers.add_parser("stop", help="Print safe stop instructions for foreground runs")
    agent_stop_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    agent_stop_parser.set_defaults(func=cmd_agent_stop)

    learning_parser = agent_subparsers.add_parser("learning", help="Inspect and trigger learning suggestions")
    learning_subparsers = learning_parser.add_subparsers(dest="learning_command")
    learning_status_parser = learning_subparsers.add_parser("status", help="Show learning progress")
    learning_status_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    learning_status_parser.set_defaults(func=cmd_agent_learning_status)
    learning_suggestions_parser = learning_subparsers.add_parser("suggestions", help="Show latest learning suggestions")
    learning_suggestions_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    learning_suggestions_parser.set_defaults(func=cmd_agent_learning_suggestions)
    learning_trigger_parser = learning_subparsers.add_parser("trigger", help="Trigger learning analysis when ready")
    learning_trigger_parser.add_argument("--force", action="store_true", help="Analyze even if threshold is not reached")
    learning_trigger_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    learning_trigger_parser.set_defaults(func=cmd_agent_learning_trigger)

    agent_memory_parser = agent_subparsers.add_parser("memory", help="Show readonly Agent memory cases")
    agent_memory_parser.add_argument("--agent-id", default="agent-rule-baseline", help="Agent account id to inspect")
    agent_memory_parser.add_argument("--similar-to", default="", help="Filter by stock code")
    agent_memory_parser.add_argument("--outcome", default="", help="Filter by outcome")
    agent_memory_parser.add_argument("--limit", type=int, default=20, help="Maximum cases")
    agent_memory_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    agent_memory_parser.set_defaults(func=cmd_agent_memory)

    datasource_parser = subparsers.add_parser("datasource", help="Inspect market data provider-chain diagnostics")
    datasource_subparsers = datasource_parser.add_subparsers(dest="datasource_command")
    datasource_status_parser = datasource_subparsers.add_parser("status", help="Show datasource mode and provider-chain status")
    datasource_status_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_status_parser.set_defaults(func=cmd_datasource_status)
    datasource_test_parser = datasource_subparsers.add_parser("test", help="Smoke-test configured or selected datasource providers")
    datasource_test_parser.add_argument("--sources", default="", help="Comma-separated provider ids; empty uses configured provider chain")
    datasource_test_parser.add_argument("--all", action="store_true", help="Include non-configured catalog entries and explain skipped sources")
    datasource_test_parser.add_argument("--stock-code", default="600519", help="Stock code used for history/financial/quote checks")
    datasource_test_parser.add_argument("--days", type=int, default=5, help="History days used for smoke checks")
    datasource_test_parser.add_argument(
        "--checks",
        default="history",
        help="Comma-separated checks to run: history,financial,quote,universe. Default keeps smoke tests fast.",
    )
    datasource_test_parser.add_argument("--include-universe", action="store_true", help="Also test full/limited universe listing when the provider supports it")
    datasource_test_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_test_parser.set_defaults(func=cmd_datasource_test)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        if args.command is None:
            parser.print_help()
            return 0
        parser.error(f"command '{args.command}' is not implemented yet")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
