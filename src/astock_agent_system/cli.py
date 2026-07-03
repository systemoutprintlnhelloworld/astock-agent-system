"""Command line interface for the A-share agent system MVP."""

from __future__ import annotations

import argparse
import getpass
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
    cmd_agent_global_active,
    cmd_agent_start,
    cmd_agent_status,
    cmd_agent_stop,
    cmd_datasource_configure_ifind,
    cmd_datasource_configure_iwencai,
    cmd_datasource_configure_jqdata,
    cmd_datasource_configure_tushare,
    cmd_datasource_active_research,
    cmd_datasource_active_scan,
    cmd_datasource_history,
    cmd_datasource_iwencai_search,
    cmd_datasource_iwencai_status,
    cmd_datasource_local_status,
    cmd_datasource_smart_search_status,
    cmd_datasource_status,
    cmd_datasource_sync_local,
    cmd_datasource_test,
)
from astock_agent_system.config import PROJECT_ROOT, load_settings, save_runtime_overrides
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
            "has_ifind_access_token": bool(settings.data.ifind_access_token),
            "has_ifind_refresh_token": bool(settings.data.ifind_refresh_token),
            "ifind_base_url": settings.data.ifind_base_url,
            "iwencai_base_url": settings.data.iwencai_base_url,
            "has_iwencai_api_key": bool(settings.data.iwencai_api_key),
            "iwencai_skillhub_cli": settings.data.iwencai_skillhub_cli,
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
        "smart_search": {
            "enabled": settings.smart_search.enabled,
            "timeout_seconds": settings.smart_search.timeout_seconds,
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


def _add_active_research_options(parser: argparse.ArgumentParser) -> None:
    """Add shared options for local-first global active research commands."""

    parser.add_argument("--profile", default="ultra-short", help="Active profile; default is ultra-short")
    parser.add_argument("--db-path", default="", help="Optional local SQLite market warehouse path")
    parser.add_argument("--max-sectors", type=int, default=5, help="Maximum hot sectors to display")
    parser.add_argument("--max-candidates", type=int, default=60, help="Maximum local candidate rows to scan")
    parser.add_argument("--candidate-per-sector", type=int, default=10, help="Maximum candidates per hot sector")
    parser.add_argument("--max-buys", type=int, default=5, help="Maximum BUY actions in the paper plan")
    parser.add_argument("--history-days", type=int, default=20, help="History days used for local momentum/liquidity signals")
    parser.add_argument("--min-amount", type=float, default=None, help="Minimum turnover amount filter")
    parser.add_argument("--as-of-date", default="", help="Use local quote date YYYY-MM-DD; empty uses latest local date")
    parser.add_argument("--include-stale", action="store_true", help="Allow stale local rows when latest quotes are incomplete")
    parser.add_argument("--refresh-realtime", action="store_true", help="Refresh shortlisted quotes through provider-chain before timing")


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


def _prompt_default(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _prompt_int(label: str, default: int) -> int:
    while True:
        raw = _prompt_default(label, str(default))
        try:
            return int(raw)
        except ValueError:
            print("请输入整数，或直接回车使用默认值。")


def _prompt_float(label: str, default: float) -> float:
    while True:
        raw = _prompt_default(label, f"{default:g}")
        try:
            return float(raw)
        except ValueError:
            print("请输入数字，或直接回车使用默认值。")


def _prompt_yes_no(label: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "是", "1", "true"}:
            return True
        if raw in {"n", "no", "否", "0", "false"}:
            return False
        print("请输入 y 或 n。")


def _prompt_select(label: str, options: list[str], default: str = "", *, allow_manual: bool = False) -> str:
    choices = [str(item).strip() for item in options if str(item).strip()]
    if not choices:
        return _prompt_default(label, default) if allow_manual else default
    default_value = default if default in choices else choices[0]
    default_index = choices.index(default_value) + 1
    print(f"\n{label}:")
    for index, item in enumerate(choices, 1):
        marker = " *" if item == default_value else ""
        print(f"  {index}) {item}{marker}")
    manual_hint = "；输入 m 可手动填写" if allow_manual else ""
    while True:
        raw = input(f"请选择编号 [默认 {default_index}]{manual_hint}: ").strip().lower()
        if not raw:
            return default_value
        if allow_manual and raw in {"m", "manual", "custom", "自定义", "手动"}:
            return _prompt_default("手动输入值", default)
        try:
            index = int(raw)
        except ValueError:
            print("请输入列表编号，或直接回车使用默认值。")
            continue
        if 1 <= index <= len(choices):
            return choices[index - 1]
        print(f"编号超出范围，请输入 1-{len(choices)}。")


def _interactive_args(config: str | None, **kwargs: object) -> argparse.Namespace:
    payload: dict[str, object] = {"config": config}
    payload.update(kwargs)
    return argparse.Namespace(**payload)


def _cmd_interactive_configure(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    print("\n只保存非密钥运行配置；LLM key、Tushare token、JQData/iFinD 密钥请用对应隐藏输入或 .env。")
    data_mode = _prompt_default("数据模式：online 为主流程，offline 仅诊断", settings.data.mode or "online")
    provider_chain_raw = _prompt_default(
        "在线数据源链（逗号分隔）",
        ",".join(settings.data.provider_chain or ["tushare", "baostock", "akshare"]),
    )
    default_model = _prompt_default("默认 LLM 模型（空值表示继续使用现有配置）", settings.llm.default_model or "")
    max_count = _prompt_int("每轮最多分析候选数", int(settings.scheduler.max_count or 3))
    history_days = _prompt_int("每轮历史行情天数", int(settings.scheduler.history_days or 24))

    payload: dict[str, object] = {
        "data": {
            "mode": data_mode,
            "provider_chain": _parse_models(provider_chain_raw),
        },
        "scheduler": {
            "max_count": max_count,
            "history_days": history_days,
        },
    }
    if default_model:
        payload["llm"] = {"default_model": default_model}
    path = save_runtime_overrides(payload)
    print(f"已保存到本地运行态配置：{path}")
    print("提示：真实密钥不会写入这里；如需配置 JQData/iFinD，请回主菜单选择隐藏输入配置项。")
    return 0


def _run_llm_self_check(settings: object, *, model: str, profile: str) -> dict[str, object]:
    client = LLMClient(settings)  # type: ignore[arg-type]
    try:
        models_payload = client.list_models_safe()
        result = client.chat_json(
            [
                {"role": "system", "content": "你是 AStock 配置自检助手。必须只输出 JSON。"},
                {
                    "role": "user",
                    "content": '请只输出 {"status":"ok","answer":"一句话说明A股是什么"}，不要输出 Markdown。',
                },
            ],
            model=model,
            temperature=0.0,
            profile=profile,
        )
        return {
            "status": "ok" if result.json_parseable else "warning",
            "model": result.model,
            "profile": result.profile,
            "models": models_payload,
            "answer": result.parsed.get("answer", result.content[:120]),
        }
    except Exception as exc:  # pragma: no cover - depends on user's gateway
        return {"status": "error", "message": str(exc)[:500]}


def _cmd_interactive_llm_config(config: str | None) -> int:
    settings = load_settings(config)
    print("\nLLM 是主工作流的一等配置；API Key 使用隐藏输入，只有自检通过才写入本地忽略配置。")
    profile = _prompt_select(
        "请求协议/Provider 通道",
        ["auto", "openai", "codex", "anthropic", "claude_code"],
        settings.llm.request_profile or "auto",
        allow_manual=True,
    )
    base_url = _prompt_default("LLM Base URL", settings.llm.base_url or "")
    api_key = getpass.getpass("LLM API Key（隐藏输入，留空表示沿用当前配置）: ").strip()
    list_first = _prompt_yes_no("先拉取模型列表辅助选择吗", True)
    runtime_api_key = api_key or settings.llm.api_key
    settings.llm.request_profile = profile
    settings.llm.base_url = base_url
    settings.llm.api_key = runtime_api_key
    model_list: list[str] = []
    if list_first:
        models_payload = LLMClient(settings).list_models_safe()
        model_list = [str(item) for item in models_payload.get("models", [])] if isinstance(models_payload, dict) else []
        if model_list:
            model_list = model_list[:50]
        else:
            print(f"\n模型列表不可用: {models_payload.get('reason', models_payload.get('status', 'unknown')) if isinstance(models_payload, dict) else 'unknown'}")
    if model_list:
        default_model = _prompt_select("可用模型（输入编号即可，回车选择当前/第一个模型）", model_list, settings.llm.default_model or model_list[0], allow_manual=True)
    else:
        default_model = _prompt_default("默认模型", settings.llm.default_model or "")
    settings.llm.default_model = default_model
    self_check = _run_llm_self_check(settings, model=default_model, profile=profile)
    if self_check.get("status") == "error":
        print("LLM 自检失败，已拒绝写入本地配置。")
        print(json.dumps({"status": "error", "self_check": self_check}, ensure_ascii=False, indent=2, default=str))
        return 1
    payload: dict[str, object] = {
        "llm": {
            "base_url": base_url,
            "request_profile": profile,
            "default_model": default_model,
        }
    }
    if api_key:
        payload["llm"]["api_key"] = api_key  # type: ignore[index]
    path = save_runtime_overrides(payload)
    print(json.dumps({"status": "ok", "runtime_config_path": str(path), "self_check": self_check}, ensure_ascii=False, indent=2, default=str))
    return 0


def _make_agent_start_args(
    config: str | None,
    *,
    continuous: bool,
    settings_max_count: int,
    settings_days: int,
) -> argparse.Namespace:
    max_count = _prompt_int("本轮最多分析候选数", settings_max_count)
    days = _prompt_int("历史行情天数", settings_days)
    timeout_seconds = _prompt_float("单轮总超时秒数", 900.0)
    interval_minutes = 60.0
    max_rounds = 0
    if continuous:
        print("\n连续运行会先立即执行第 1 轮，之后按下面间隔等待；可输入 1/5/15 做短周期验证。")
        interval_minutes = _prompt_float("连续运行间隔分钟", 15.0)
        max_rounds = _prompt_int("最多运行轮数（0 表示直到 Ctrl+C）", 0)
    fresh_start = _prompt_yes_no("是否从初始资金重新开始（忽略已保存账户快照）", False)
    no_persist = _prompt_yes_no("是否跳过 MongoDB 持久化（调试时可选）", False)
    verbose = _prompt_yes_no("是否显示更详细事件", False)
    return _interactive_args(
        config,
        model="",
        models="",
        offline=False,
        max_count=max_count,
        days=days,
        initial_capital=None,
        fresh_start=fresh_start,
        no_persist=no_persist,
        no_learning=False,
        timeout_seconds=timeout_seconds,
        continuous=continuous,
        interval_minutes=interval_minutes,
        max_rounds=max_rounds,
        verbose=verbose,
        debug=False,
    )


def _run_interactive_quickstart(config: str | None) -> int:
    print("\n快速向导会按顺序完成：LLM 自检 -> 非密钥配置 -> 数据源自检 -> 本地库同步 -> 可选启动一次智能体。")
    if _prompt_yes_no("先配置并自检 LLM 吗", True):
        _cmd_interactive_llm_config(config)
    if _prompt_yes_no("先调整非密钥运行配置吗", True):
        _cmd_interactive_configure(_interactive_args(config))
    if _prompt_yes_no("现在做一次数据源快速自检吗", True):
        _run_interactive_datasource_test(config)
    if _prompt_yes_no("要先同步本地市场库（撸数据）吗", False):
        _run_interactive_sync_local(config)
    if _prompt_yes_no("现在启动一次智能体工作流吗（使用本地默认模型，不强制 offline）", False):
        return _run_interactive_agent(config, continuous=False)
    return 0


def _run_interactive_datasource_test(config: str | None) -> int:
    stock_code = _prompt_default("测试股票代码", "600519")
    days = _prompt_int("历史天数", 5)
    checks = _prompt_default("检查项", "history,quote")
    timeout_seconds = _prompt_float("单源超时秒数", 12.0)
    return cmd_datasource_test(
        _interactive_args(
            config,
            sources="",
            all=False,
            stock_code=stock_code,
            days=days,
            checks=checks,
            include_universe=False,
            timeout_seconds=timeout_seconds,
            format="text",
        )
    )


def _run_interactive_agent(config: str | None, *, continuous: bool) -> int:
    settings = load_settings(config)
    return cmd_agent_start(
        _make_agent_start_args(
            config,
            continuous=continuous,
            settings_max_count=int(settings.scheduler.max_count or 3),
            settings_days=int(settings.scheduler.history_days or 24),
        )
    )


def _run_interactive_sync_local(config: str | None) -> int:
    settings = load_settings(config)
    sources = _prompt_default("同步数据源（空/回车使用配置链）", ",".join(settings.data.provider_chain or []))
    sync_mode = _prompt_select("同步模式", ["incremental", "quick", "specified", "full"], "incremental")
    stock_codes = _prompt_default("指定股票代码（逗号分隔，留空则先拉股票池）", "")
    default_max = 20 if sync_mode == "quick" else 0
    max_stocks = _prompt_int("最多同步股票数（0 表示按股票池全量；A股全市场约 3595 只）", default_max)
    days = _prompt_int("每只股票历史天数", 120)
    checks = _prompt_default("同步项", "universe,history,quote,financial")
    provider_strategy = _prompt_select("Provider 策略", ["fill-gaps", "all-providers"], "fill-gaps")
    return cmd_datasource_sync_local(
        _interactive_args(
            config,
            sources=sources,
            stock_codes=stock_codes,
            max_stocks=max_stocks,
            sync_mode=sync_mode,
            provider_strategy=provider_strategy,
            days=days,
            checks=checks,
            db_path="",
            format="text",
        )
    )


def _render_interactive_menu(config: str | None) -> None:
    settings = load_settings(config)
    provider_chain = ", ".join(settings.data.provider_chain or []) or "(未配置)"
    default_model = settings.llm.default_model or "(未配置，将由 LLM 客户端兜底)"
    print("\n" + "=" * 72)
    print("AStock 交互式工作流控制台")
    print("日常只需要运行：python -m astock_agent_system.cli")
    print("-" * 72)
    print(f"当前数据模式: {settings.data.mode}    数据源链: {provider_chain}")
    print(f"当前默认模型: {default_model}")
    print(f"默认候选数/历史天数: {settings.scheduler.max_count}/{settings.scheduler.history_days}")
    print("-" * 72)
    print("0) 快速向导：重新初始化并运行一次测试")
    print("1) LLM 配置与诊断：Provider/Base URL/Key/模型列表/自检")
    print("2) 数据源配置与诊断：Tushare/JQData/iFinD/iWencai/smart-search 自检")
    print("3) 本地数据同步：全市场/增量/指定股票 SQLite 撸数据")
    print("4) 运行工作流：LLM 智能体单轮 / 连续运行 / Agent 状态")
    print("5) 学习中心：学习状态 / 建议 / 触发分析 / 历史 / 记忆")
    print("6) 运行日志 / 历史回放：查看最近 JSONL 与摘要")
    print("h) 显示高级长命令帮助")
    print("q) 退出")


def _is_exit_choice(choice: str) -> bool:
    return choice in {"q", "quit", "exit"}


def _is_back_choice(choice: str) -> bool:
    return choice in {"b", "back", "r", "return", "返回"}


def _render_submenu(title: str, items: list[str]) -> None:
    print("\n" + "-" * 72)
    print(title)
    print("-" * 72)
    for item in items:
        print(item)
    print("b) 返回主菜单")
    print("q) 退出")


def _interactive_llm_diagnostics(config: str | None) -> bool:
    while True:
        _render_submenu(
            "LLM 配置与诊断",
            [
                "1) 配置/重新配置 LLM Provider、Base URL、Key、默认模型并自检",
                "2) 使用当前配置执行一次 LLM 自检",
                "3) 查看当前脱敏 LLM 配置",
            ],
        )
        choice = input("LLM 配置与诊断> ").strip().lower()
        if _is_exit_choice(choice):
            return True
        if _is_back_choice(choice):
            return False
        if choice == "1":
            _cmd_interactive_llm_config(config)
        elif choice == "2":
            settings = load_settings(config)
            model = _prompt_default("自检模型", settings.llm.default_model or "")
            profile = _prompt_default("请求协议/Provider 通道", settings.llm.request_profile or "auto")
            print(json.dumps(_run_llm_self_check(settings, model=model, profile=profile), ensure_ascii=False, indent=2, default=str))
        elif choice == "3":
            _cmd_config(_interactive_args(config))
        else:
            print("未知选项，请输入菜单编号、b 或 q。")


def _interactive_datasource_diagnostics(config: str | None) -> bool:
    while True:
        _render_submenu(
            "数据源配置与诊断",
            [
                "1) 查看数据源状态",
                "2) 数据源快速自检",
                "3) 配置 Tushare token（隐藏输入，自检通过才保存）",
                "4) 配置 JQData 凭证（隐藏输入，自检通过才保存）",
                "5) 配置 iFinD/同花顺 token（隐藏输入，矩阵自检通过才保存）",
                "6) 查看 iWencai SkillHub 状态",
                "7) 配置 iWencai API Key / SkillHub CLI（隐藏输入）",
                "8) iWencai 公告检索诊断",
                "9) smart-search 舆情检索自检",
                "10) 查看当前脱敏配置和 Agent 状态",
            ],
        )
        choice = input("数据源配置与诊断> ").strip().lower()
        if _is_exit_choice(choice):
            return True
        if _is_back_choice(choice):
            return False
        if choice == "1":
            cmd_datasource_status(_interactive_args(config, format="text"))
        elif choice == "2":
            _run_interactive_datasource_test(config)
        elif choice == "3":
            cmd_datasource_configure_tushare(_interactive_args(config))
        elif choice == "4":
            cmd_datasource_configure_jqdata(_interactive_args(config))
        elif choice == "5":
            cmd_datasource_configure_ifind(_interactive_args(config))
        elif choice == "6":
            cmd_datasource_iwencai_status(_interactive_args(config, format="table"))
        elif choice == "7":
            cmd_datasource_configure_iwencai(_interactive_args(config, base_url="", skillhub_cli=""))
        elif choice == "8":
            stock_code = _prompt_default("股票代码（可空）", "600519")
            query = _prompt_default("iWencai 查询", "公告")
            cmd_datasource_iwencai_search(
                _interactive_args(config, stock_code=stock_code, query=query, limit=5, timeout_seconds=20.0, format="table")
            )
        elif choice == "9":
            cmd_datasource_smart_search_status(_interactive_args(config, timeout_seconds=20.0, format="text"))
        elif choice == "10":
            print("\n[有效配置]")
            _cmd_config(_interactive_args(config))
            print("\n[Agent 状态]")
            cmd_agent_status(_interactive_args(config, model="", agent_id="", limit=10, format="text"))
        else:
            print("未知选项，请输入菜单编号、b 或 q。")


def _interactive_sync_center(config: str | None) -> bool:
    while True:
        _render_submenu(
            "本地数据同步",
            [
                "1) 同步本地市场数据（SQLite，默认 fill-gaps 补齐策略）",
                "2) 查看本地市场数据状态（SQLite 库存量/最近同步）",
                "3) 本地市场主动扫描（广域短名单，不触发LLM）",
            ],
        )
        choice = input("本地数据同步> ").strip().lower()
        if _is_exit_choice(choice):
            return True
        if _is_back_choice(choice):
            return False
        if choice == "1":
            _run_interactive_sync_local(config)
        elif choice == "2":
            cmd_datasource_local_status(_interactive_args(config, db_path="", format="text"))
        elif choice == "3":
            limit = _prompt_int("输出候选数", 30)
            sector = _prompt_default("行业过滤（可空，多个用逗号分隔）", "")
            min_amount = _prompt_float("最小成交额（可回车用0不过滤）", 0.0)
            cmd_datasource_active_scan(
                _interactive_args(
                    config,
                    db_path="",
                    limit=limit,
                    sector=[sector] if sector else [],
                    min_amount=min_amount if min_amount > 0 else None,
                    min_volume=None,
                    min_change_pct=None,
                    max_change_pct=None,
                    history_days=20,
                    top_per_sector=0,
                    include_stale=False,
                    as_of_date="",
                    format="text",
                )
            )
        else:
            print("未知选项，请输入菜单编号、b 或 q。")


def _interactive_run_workflow(config: str | None) -> bool:
    while True:
        _render_submenu(
            "运行工作流",
            [
                "1) 启动一次智能体工作流（使用本地默认模型）",
                "2) 连续运行智能体（直到 Ctrl+C 或达到轮数）",
                "3) 查看 Agent 状态",
                "4) 查看停止说明",
            ],
        )
        choice = input("运行工作流> ").strip().lower()
        if _is_exit_choice(choice):
            return True
        if _is_back_choice(choice):
            return False
        if choice == "1":
            _run_interactive_agent(config, continuous=False)
        elif choice == "2":
            _run_interactive_agent(config, continuous=True)
        elif choice == "3":
            cmd_agent_status(_interactive_args(config, model="", agent_id="", limit=10, format="text"))
        elif choice == "4":
            cmd_agent_stop(_interactive_args(config, format="text"))
        else:
            print("未知选项，请输入菜单编号、b 或 q。")


def _interactive_learning_center(config: str | None) -> bool:
    while True:
        _render_submenu(
            "学习中心",
            [
                "1) 查看学习状态",
                "2) 查看学习建议",
                "3) 触发学习分析",
                "4) 查看经验历史",
                "5) 查看 Agent 记忆案例",
            ],
        )
        choice = input("学习中心> ").strip().lower()
        if _is_exit_choice(choice):
            return True
        if _is_back_choice(choice):
            return False
        if choice == "1":
            cmd_agent_learning_status(_interactive_args(config, format="text"))
        elif choice == "2":
            cmd_agent_learning_suggestions(_interactive_args(config, format="text"))
        elif choice == "3":
            force = _prompt_yes_no("是否强制触发学习分析", False)
            cmd_agent_learning_trigger(_interactive_args(config, force=force, format="text"))
        elif choice == "4":
            limit = _prompt_int("显示经验条数", 20)
            cmd_agent_history(_interactive_args(config, model="", limit=limit, format="text"))
        elif choice == "5":
            agent_id = _prompt_default("Agent ID", "agent-rule-baseline")
            limit = _prompt_int("显示记忆案例数", 20)
            cmd_agent_memory(
                _interactive_args(config, agent_id=agent_id, limit=limit, similar_to="", outcome="", format="text")
            )
        else:
            print("未知选项，请输入菜单编号、b 或 q。")


def _interactive_run_logs(config: str | None) -> bool:
    del config
    while True:
        _render_submenu(
            "运行日志 / 历史回放",
            [
                "1) 查看最近 10 个运行摘要文件",
                "2) 查看运行日志目录",
            ],
        )
        choice = input("运行日志> ").strip().lower()
        if _is_exit_choice(choice):
            return True
        if _is_back_choice(choice):
            return False
        run_dir = PROJECT_ROOT / "data" / "runtime" / "runs"
        if choice == "1":
            if not run_dir.exists():
                print(f"暂无运行日志目录：{run_dir}")
                continue
            summaries = sorted(run_dir.glob("*.summary.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:10]
            if not summaries:
                print("暂无运行摘要。")
                continue
            rows = []
            for item in summaries:
                try:
                    payload = json.loads(item.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {}
                rows.append(
                    [
                        item.name,
                        payload.get("status", "unknown"),
                        payload.get("model_count", 0),
                        payload.get("event_count", 0),
                        payload.get("error_count", 0),
                    ]
                )
            for row in rows:
                print(f"{row[0]} | 状态={row[1]} | 模型={row[2]} | 事件={row[3]} | 错误={row[4]}")
        elif choice == "2":
            print(f"运行日志目录：{run_dir}")
        else:
            print("未知选项，请输入菜单编号、b 或 q。")


def _cmd_interactive(args: argparse.Namespace) -> int:
    config = getattr(args, "config", None)
    print("欢迎进入 AStock CLI。长命令仍保留给自动化；日常测试从这个菜单开始。")
    try:
        while True:
            _render_interactive_menu(config)
            choice = input("请选择操作: ").strip().lower()
            if choice in {"q", "quit", "exit"}:
                print("已退出交互式工作流。")
                return 0
            if choice == "0":
                _run_interactive_quickstart(config)
            elif choice == "1":
                if _interactive_llm_diagnostics(config):
                    print("已退出交互式工作流。")
                    return 0
            elif choice == "2":
                if _interactive_datasource_diagnostics(config):
                    print("已退出交互式工作流。")
                    return 0
            elif choice == "3":
                if _interactive_sync_center(config):
                    print("已退出交互式工作流。")
                    return 0
            elif choice == "4":
                if _interactive_run_workflow(config):
                    print("已退出交互式工作流。")
                    return 0
            elif choice == "5":
                if _interactive_learning_center(config):
                    print("已退出交互式工作流。")
                    return 0
            elif choice == "6":
                if _interactive_run_logs(config):
                    print("已退出交互式工作流。")
                    return 0
            elif choice in {"h", "help", "?"}:
                build_parser().print_help()
            else:
                print("未知选项，请输入菜单编号、h 或 q。")
    except (KeyboardInterrupt, EOFError):
        print("\n已退出交互式工作流。")
        return 130


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

    agent_start_parser = agent_subparsers.add_parser("start", help="Start a streaming agent run using the local configured default model")
    agent_start_parser.add_argument("--model", default="", help="Optional single model id override; empty uses local llm.default_model")
    agent_start_parser.add_argument("--models", default="", help="Optional comma-separated model overrides; empty uses local llm.default_model")
    agent_start_parser.add_argument("--offline", action="store_true", help="Diagnostic fallback only: force offline sample data mode")
    agent_start_parser.add_argument("--max-count", type=int, default=3, help="Maximum candidates to analyze per model")
    agent_start_parser.add_argument("--days", type=int, default=24, help="History days used for analysis")
    agent_start_parser.add_argument("--initial-capital", type=float, default=None, help="Initial capital for each model account")
    agent_start_parser.add_argument("--fresh-start", action="store_true", help="Ignore stored snapshots and start from initial capital")
    agent_start_parser.add_argument("--no-persist", action="store_true", help="Do not write leaderboard/trades to MongoDB")
    agent_start_parser.add_argument("--no-learning", action="store_true", help="Do not record learning experiences for this run")
    agent_start_parser.add_argument("--timeout-seconds", type=float, default=900.0, help="Hard timeout for one foreground agent run")
    agent_start_parser.add_argument("--continuous", action="store_true", help="Keep running rounds until Ctrl+C or --max-rounds is reached")
    agent_start_parser.add_argument("--interval-minutes", type=float, default=60.0, help="Minutes to wait between continuous rounds")
    agent_start_parser.add_argument("--max-rounds", type=int, default=0, help="Maximum continuous rounds; 0 means run until Ctrl+C")
    agent_start_parser.add_argument("--verbose", action="store_true", help="Print verbose stream events")
    agent_start_parser.add_argument("--debug", action="store_true", help="Print raw JSON events")
    agent_start_parser.set_defaults(func=cmd_agent_start)

    agent_benchmark_parser = agent_subparsers.add_parser("benchmark", help="Run streaming multi-model benchmark")
    agent_benchmark_parser.add_argument("--models", default="", help="Optional comma-separated model ids; empty uses local llm.default_model")
    agent_benchmark_parser.add_argument("--offline", action="store_true", help="Diagnostic fallback only: force offline sample data mode")
    agent_benchmark_parser.add_argument("--max-count", type=int, default=3, help="Maximum candidates to analyze per model")
    agent_benchmark_parser.add_argument("--days", type=int, default=24, help="History days used for analysis")
    agent_benchmark_parser.add_argument("--initial-capital", type=float, default=None, help="Initial capital for each model account")
    agent_benchmark_parser.add_argument("--fresh-start", action="store_true", help="Ignore stored snapshots and start from initial capital")
    agent_benchmark_parser.add_argument("--no-persist", action="store_true", help="Do not write leaderboard/trades to MongoDB")
    agent_benchmark_parser.add_argument("--no-learning", action="store_true", help="Do not record learning experiences for this run")
    agent_benchmark_parser.add_argument("--timeout-seconds", type=float, default=900.0, help="Hard timeout for one foreground benchmark run")
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

    agent_global_active_parser = agent_subparsers.add_parser(
        "global-active",
        help="Run the global active ultra-short paper-trading workflow with T+1 guards",
    )
    _add_active_research_options(agent_global_active_parser)
    agent_global_active_parser.add_argument("--initial-capital", type=float, default=None, help="Optional fresh paper-account capital")
    agent_global_active_parser.add_argument("--verbose", action="store_true", help="Show verbose event output")
    agent_global_active_parser.add_argument("--debug", action="store_true", help="Show debug event output")
    agent_global_active_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    agent_global_active_parser.set_defaults(func=cmd_agent_global_active)

    datasource_parser = subparsers.add_parser("datasource", help="Inspect market data provider-chain diagnostics")
    datasource_subparsers = datasource_parser.add_subparsers(dest="datasource_command")
    datasource_status_parser = datasource_subparsers.add_parser("status", help="Show datasource mode and provider-chain status")
    datasource_status_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_status_parser.set_defaults(func=cmd_datasource_status)

    datasource_history_parser = datasource_subparsers.add_parser(
        "history",
        help="Show persisted datasource switch/attempt history",
    )
    datasource_history_parser.add_argument("--limit", type=int, default=100, help="Maximum recent history rows")
    datasource_history_parser.add_argument("--source", default="", help="Optional provider id filter")
    datasource_history_parser.add_argument("--operation", default="", help="Optional operation filter, e.g. history/quote/financial")
    datasource_history_parser.add_argument("--status", default="", help="Optional status filter, e.g. ok/error/skipped")
    datasource_history_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_history_parser.set_defaults(func=cmd_datasource_history)

    datasource_smart_search_parser = datasource_subparsers.add_parser(
        "smart-search-status",
        help="Show smart-search CLI/configuration diagnostics used by SentimentAnalyst",
    )
    datasource_smart_search_parser.add_argument("--timeout-seconds", type=float, default=20.0, help="smart-search doctor timeout")
    datasource_smart_search_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_smart_search_parser.set_defaults(func=cmd_datasource_smart_search_status)

    datasource_iwencai_status_parser = datasource_subparsers.add_parser(
        "iwencai-status",
        help="Show redacted iWencai SkillHub configuration status",
    )
    datasource_iwencai_status_parser.add_argument("--format", choices=("table", "json"), default="table", help="Output format")
    datasource_iwencai_status_parser.set_defaults(func=cmd_datasource_iwencai_status)

    datasource_iwencai_search_parser = datasource_subparsers.add_parser(
        "iwencai-search",
        help="Try any run-capable iWencai SkillHub research skill and print redacted diagnostics",
    )
    datasource_iwencai_search_parser.add_argument("--skill", default="announcement-search", help="SkillHub skill name, e.g. announcement-search")
    datasource_iwencai_search_parser.add_argument("--stock-code", default="", help="Optional stock code context")
    datasource_iwencai_search_parser.add_argument("--query", default="公告", help="Search query passed to the selected SkillHub skill")
    datasource_iwencai_search_parser.add_argument("--limit", type=int, default=5, help="Maximum announcement rows")
    datasource_iwencai_search_parser.add_argument("--timeout-seconds", type=float, default=20.0, help="SkillHub CLI timeout")
    datasource_iwencai_search_parser.add_argument("--format", choices=("table", "json"), default="json", help="Output format")
    datasource_iwencai_search_parser.set_defaults(func=cmd_datasource_iwencai_search)

    datasource_config_iwencai_parser = datasource_subparsers.add_parser(
        "configure-iwencai",
        help="Persist iWencai SkillHub credentials to local ignored runtime config",
    )
    datasource_config_iwencai_parser.add_argument("--base-url", default="", help="iWencai OpenAPI base URL")
    datasource_config_iwencai_parser.add_argument("--skillhub-cli", default="", help="SkillHub CLI command name or path")
    datasource_config_iwencai_parser.set_defaults(func=cmd_datasource_configure_iwencai)

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
    datasource_test_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=15.0,
        help="Hard timeout per provider/check so web sources cannot keep the CLI running forever",
    )
    datasource_test_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_test_parser.set_defaults(func=cmd_datasource_test)

    datasource_sync_parser = datasource_subparsers.add_parser(
        "sync-local",
        help="Sync online provider-chain market data into the ignored local SQLite store",
    )
    datasource_sync_parser.add_argument(
        "--sources",
        default="",
        help="Comma-separated provider ids; empty uses configured provider chain",
    )
    datasource_sync_parser.add_argument(
        "--stock-codes",
        default="",
        help="Comma-separated stock codes; when omitted, sync-local first pulls provider universe",
    )
    datasource_sync_parser.add_argument("--max-stocks", type=int, default=20, help="Maximum stocks to sync in one batch")
    datasource_sync_parser.add_argument(
        "--sync-mode",
        choices=("quick", "full", "incremental", "specified"),
        default="incremental",
        help="Sync scope preset; specified is implied when --stock-codes is provided",
    )
    datasource_sync_parser.add_argument(
        "--provider-strategy",
        choices=("fill-gaps", "all-providers"),
        default="fill-gaps",
        help="fill-gaps stops after the first successful provider; all-providers records every provider's participation",
    )
    datasource_sync_parser.add_argument("--days", type=int, default=120, help="History days to store for each stock")
    datasource_sync_parser.add_argument(
        "--checks",
        default="universe,history,quote,financial",
        help="Comma-separated sync operations: universe,history,quote,financial",
    )
    datasource_sync_parser.add_argument(
        "--db-path",
        default="",
        help="Optional SQLite path; default is data/market_local/market.sqlite and is ignored by Git",
    )
    datasource_sync_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_sync_parser.set_defaults(func=cmd_datasource_sync_local)

    datasource_local_status_parser = datasource_subparsers.add_parser(
        "local-status",
        help="Show local SQLite market database inventory and recent sync runs",
    )
    datasource_local_status_parser.add_argument(
        "--db-path",
        default="",
        help="Optional SQLite path; default is data/market_local/market.sqlite and is ignored by Git",
    )
    datasource_local_status_parser.add_argument("--stock-limit", type=int, default=12, help="Maximum stock rows in coverage sample")
    datasource_local_status_parser.add_argument("--date-limit", type=int, default=30, help="Maximum recent dates in coverage heatmap")
    datasource_local_status_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_local_status_parser.set_defaults(func=cmd_datasource_local_status)

    datasource_active_scan_parser = datasource_subparsers.add_parser(
        "active-scan",
        help="Scan local SQLite market data for a broad candidate shortlist without LLM/provider calls",
    )
    datasource_active_scan_parser.add_argument(
        "--db-path",
        default="",
        help="Optional SQLite path; default is data/market_local/market.sqlite and is ignored by Git",
    )
    datasource_active_scan_parser.add_argument("--limit", type=int, default=30, help="Maximum candidates to print")
    datasource_active_scan_parser.add_argument("--sector", action="append", default=[], help="Sector filter; can repeat or use comma-separated values")
    datasource_active_scan_parser.add_argument("--as-of-date", default="", help="Quote date to scan; default uses latest quote date")
    datasource_active_scan_parser.add_argument("--min-amount", type=float, default=None, help="Minimum latest quote amount")
    datasource_active_scan_parser.add_argument("--min-volume", type=float, default=None, help="Minimum latest quote volume")
    datasource_active_scan_parser.add_argument("--min-change-pct", type=float, default=None, help="Minimum latest change_pct, e.g. 0.01")
    datasource_active_scan_parser.add_argument("--max-change-pct", type=float, default=None, help="Maximum latest change_pct, e.g. 0.08")
    datasource_active_scan_parser.add_argument("--history-days", type=int, default=20, help="Local K-line window used for momentum/volume ratios")
    datasource_active_scan_parser.add_argument("--top-per-sector", type=int, default=0, help="Optional cap per sector for diversification")
    datasource_active_scan_parser.add_argument("--include-stale", action="store_true", help="Allow mixed quote dates instead of latest/as-of only")
    datasource_active_scan_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_active_scan_parser.set_defaults(func=cmd_datasource_active_scan)

    datasource_active_research_parser = datasource_subparsers.add_parser(
        "active-research",
        help="Rank sectors and batch candidates from local SQLite for global active ultra-short research",
    )
    _add_active_research_options(datasource_active_research_parser)
    datasource_active_research_parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    datasource_active_research_parser.set_defaults(func=cmd_datasource_active_research)

    datasource_jqdata_parser = datasource_subparsers.add_parser(
        "configure-jqdata",
        help="Save JQData credentials through hidden prompts into ignored runtime config",
    )
    datasource_jqdata_parser.add_argument("--username", default="", help="Optional JQData username; password is always prompted securely")
    datasource_jqdata_parser.add_argument(
        "--candidate-count",
        type=int,
        default=1,
        help="Number of hidden username candidates to probe before saving the first successful JQData preflight",
    )
    datasource_jqdata_parser.add_argument(
        "--provider-chain",
        default="",
        help="Optional comma-separated provider chain to save; jqdata is appended when absent",
    )
    datasource_jqdata_parser.set_defaults(func=cmd_datasource_configure_jqdata)

    datasource_ifind_parser = datasource_subparsers.add_parser(
        "configure-ifind",
        help="Save iFinD/同花顺 QuantAPI tokens through hidden prompts into ignored runtime config",
    )
    datasource_ifind_parser.add_argument(
        "--provider-chain",
        default="",
        help="Optional comma-separated provider chain to save; ifind is appended when absent",
    )
    datasource_ifind_parser.set_defaults(func=cmd_datasource_configure_ifind)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        if args.command is None:
            return _cmd_interactive(args)
        parser.error(f"command '{args.command}' is not implemented yet")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
