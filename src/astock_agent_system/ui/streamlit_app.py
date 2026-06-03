"""Beginner-friendly Streamlit dashboard for the A-share agent MVP."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from astock_agent_system.agents import MasterAgent
from astock_agent_system.backtest import BacktestEngine
from astock_agent_system.config import PROJECT_ROOT, Settings, load_settings
from astock_agent_system.llm import LLMClient, ModelBench
from astock_agent_system.orchestrator import MultiAgentOrchestrator
from astock_agent_system.reporting import save_daily_report


UI_SETTINGS_PATH = PROJECT_ROOT / "data" / "runtime" / "ui_settings.json"

RISK_PRESETS: dict[str, dict[str, float | int]] = {
    "保守": {
        "max_count": 3,
        "history_days": 24,
        "max_position_per_stock": 0.05,
        "max_total_position": 0.30,
        "stop_loss_pct": 0.04,
    },
    "平衡": {
        "max_count": 5,
        "history_days": 24,
        "max_position_per_stock": 0.10,
        "max_total_position": 0.50,
        "stop_loss_pct": 0.05,
    },
    "激进": {
        "max_count": 8,
        "history_days": 36,
        "max_position_per_stock": 0.20,
        "max_total_position": 0.80,
        "stop_loss_pct": 0.08,
    },
}

ACTION_COPY: dict[str, tuple[str, str]] = {
    "BUY": ("模拟买入", "系统认为机会相对更大，但仍建议小仓位、分批、先模拟验证。"),
    "HOLD": ("先观察", "暂时没有足够强的买入理由，适合放入观察名单。"),
    "SELL": ("模拟卖出", "系统认为需要降低风险，适合在模拟盘里减仓或退出。"),
    "REJECT": ("暂不买入", "风控或综合评分没有通过，当前不适合纳入模拟买入。"),
}

AGENT_HELP: dict[str, str] = {
    "technical": "技术面：只看股价、成交量和趋势，回答“最近走势好不好”。",
    "fundamental": "基本面：看估值、盈利、增长和负债，回答“公司质地和价格是否合理”。",
    "sentiment": "舆情面：看新闻、社区和行业情绪。离线模式下默认是中性。",
    "debate": "多 Agent 讨论：把看多和看空理由放在一起，给出折中判断。",
    "risk": "风控：最后一道安全检查，主要看流动性、波动和仓位是否过大。",
}

TERM_HELP: dict[str, str] = {
    "仓位": "你准备拿账户里多少钱买这只股票。例如 10% 仓位，就是 10 万账户最多用 1 万买。",
    "止损": "提前设好的退出线。如果价格跌到这里，模拟盘会认为应该先离场，避免亏损扩大。",
    "置信度": "系统对自己判断的把握程度。越高代表多个 Agent 的意见越一致，不代表一定会涨。",
    "最大回撤": "账户从最高点往下亏过多少。它越大，说明过程越难熬。",
    "离线模式": "使用本项目自带的样例行情和规则 Agent，不联网、不真实下单，适合先体验流程。",
    "LLM": "大语言模型。这里可用来做模型连通性测试、舆情辅助和把报告翻译成小白话。",
}


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - manual UI guard
        raise SystemExit("Streamlit is not installed. Run: python -m pip install -e .[ui]") from exc

    st.set_page_config(page_title="A股模拟投资小助手", layout="wide")
    _inject_css(st)

    settings = load_settings()
    _ensure_session_state(st, settings, _load_ui_settings())
    _render_sidebar(st)
    _apply_session_settings(st, settings)

    _render_hero(st, settings)

    tab_home, tab_watch, tab_run, tab_reports, tab_backtest, tab_llm, tab_config = st.tabs(
        ["我该怎么用", "观测看板", "一键分析", "历史报告", "模拟回测", "LLM / 模型", "设置"]
    )

    with tab_home:
        _render_home_tab(st, settings)
    with tab_watch:
        _render_watch_tab(st, settings)
    with tab_run:
        _render_run_tab(st, settings)
    with tab_reports:
        _render_reports_tab(st, settings)
    with tab_backtest:
        _render_backtest_tab(st, settings)
    with tab_llm:
        _render_llm_tab(st, settings)
    with tab_config:
        _render_config_tab(st, settings)


def _inject_css(st: Any) -> None:
    st.markdown(
        """
        <style>
        .main .block-container { padding-top: 1.6rem; }
        .hero-box {
            padding: 1.15rem 1.25rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #f2f7ff 0%, #f7fff8 100%);
            border: 1px solid #dce8ff;
            margin-bottom: 1rem;
        }
        .hero-title { font-size: 1.8rem; font-weight: 800; margin-bottom: .25rem; }
        .hero-subtitle { color: #526070; line-height: 1.6; }
        .soft-card {
            padding: .95rem 1rem;
            border-radius: 14px;
            background: #ffffff;
            border: 1px solid #e9eef5;
            box-shadow: 0 1px 3px rgba(15, 23, 42, .04);
            min-height: 108px;
            margin-bottom: .75rem;
        }
        .soft-card-title { color: #64748b; font-size: .86rem; margin-bottom: .35rem; }
        .soft-card-value { color: #0f172a; font-size: 1.15rem; font-weight: 750; margin-bottom: .3rem; }
        .soft-card-desc { color: #64748b; font-size: .86rem; line-height: 1.45; }
        .badge {
            display: inline-block;
            padding: .18rem .55rem;
            border-radius: 999px;
            font-weight: 700;
            font-size: .86rem;
        }
        .badge-buy { background: #dcfce7; color: #166534; }
        .badge-hold { background: #e0f2fe; color: #075985; }
        .badge-sell { background: #fee2e2; color: #991b1b; }
        .badge-reject { background: #f1f5f9; color: #475569; }
        .small-muted { color: #64748b; font-size: .9rem; line-height: 1.55; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _ensure_session_state(st: Any, settings: Settings, saved: dict[str, Any]) -> None:
    defaults = {
        "ui_max_count": _clamp_int(saved.get("max_count"), 3, 1, 20),
        "ui_history_days": _clamp_int(saved.get("history_days"), 24, 6, 120),
        "ui_initial_capital": _clamp_int(saved.get("initial_capital"), int(settings.portfolio.initial_capital), 10000, 100000000),
        "ui_max_position_per_stock": _clamp_float(
            saved.get("max_position_per_stock"), settings.risk.max_position_per_stock, 0.01, 0.50
        ),
        "ui_max_total_position": _clamp_float(saved.get("max_total_position"), settings.risk.max_total_position, 0.10, 1.00),
        "ui_stop_loss_pct": _clamp_float(saved.get("stop_loss_pct"), settings.risk.stop_loss_pct, 0.01, 0.20),
        "ui_risk_preset": str(saved.get("risk_preset", "平衡")) if saved.get("risk_preset", "平衡") in RISK_PRESETS else "平衡",
        "ui_llm_base_url": str(saved.get("llm_base_url", settings.llm.base_url)),
        "ui_llm_default_model": str(saved.get("llm_default_model", settings.llm.default_model)),
        "ui_llm_api_key": "",
        "ui_llm_request_profile": str(saved.get("llm_request_profile", settings.llm.request_profile or "auto")),
        "ui_llm_max_tokens": _clamp_int(saved.get("llm_max_tokens"), settings.llm.max_tokens, 64, 4096),
        "ui_bench_prompt": "请只输出 JSON：{\"score\": 0.5, \"label\": \"ok\", \"reason\": \"模型连通性测试\"}",
        "ui_bench_models": "",
        "ui_bench_limit": 3,
        "ui_compete_models": str(saved.get("compete_models", _default_compete_models(settings))),
        "ui_compete_persist": False,
        "ui_compete_continue": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_sidebar(st: Any) -> None:
    with st.sidebar:
        st.markdown("## 运行设置")
        st.caption("这里改的是模拟盘参数，不会真实下单。")

        st.selectbox("投资风格", list(RISK_PRESETS), key="ui_risk_preset", help="新手建议先选“保守”或“平衡”。")
        if st.button("套用这个风格", use_container_width=True):
            preset = RISK_PRESETS.get(str(st.session_state.ui_risk_preset), RISK_PRESETS["平衡"])
            for key, value in preset.items():
                st.session_state[f"ui_{key}"] = value
            _rerun(st)

        st.number_input("最多分析几只股票", min_value=1, max_value=20, step=1, key="ui_max_count")
        st.number_input("参考多少天历史走势", min_value=6, max_value=120, step=1, key="ui_history_days")
        st.number_input("模拟盘初始资金", min_value=10000, step=10000, key="ui_initial_capital")

        st.markdown("### 风控")
        st.slider(
            "单只股票最多买多少",
            0.01,
            0.50,
            step=0.01,
            key="ui_max_position_per_stock",
            help=TERM_HELP["仓位"],
        )
        st.slider("账户总仓位上限", 0.10, 1.00, step=0.05, key="ui_max_total_position")
        st.slider("跌多少触发止损", 0.01, 0.20, step=0.01, key="ui_stop_loss_pct", help=TERM_HELP["止损"])

        if st.button("保存这些设置", use_container_width=True):
            saved_path = _save_ui_settings(_collect_ui_settings(st))
            st.success(f"已保存到 {saved_path.relative_to(PROJECT_ROOT)}")


def _apply_session_settings(st: Any, settings: Settings) -> None:
    settings.data.dynamic_universe_limit = _clamp_int(st.session_state.get("ui_max_count"), 3, 1, 20)
    settings.portfolio.initial_capital = float(_clamp_int(st.session_state.get("ui_initial_capital"), 100000, 10000, 100000000))
    settings.risk.max_position_per_stock = _clamp_float(st.session_state.get("ui_max_position_per_stock"), 0.10, 0.01, 0.50)
    settings.risk.max_total_position = _clamp_float(st.session_state.get("ui_max_total_position"), 0.50, 0.10, 1.00)
    settings.risk.stop_loss_pct = _clamp_float(st.session_state.get("ui_stop_loss_pct"), 0.05, 0.01, 0.20)

    base_url = str(st.session_state.get("ui_llm_base_url", settings.llm.base_url)).strip()
    if base_url:
        settings.llm.base_url = base_url.rstrip("/")
    settings.llm.default_model = str(st.session_state.get("ui_llm_default_model", settings.llm.default_model)).strip()
    settings.llm.request_profile = str(st.session_state.get("ui_llm_request_profile", settings.llm.request_profile or "auto")).strip().lower()
    settings.llm.max_tokens = _clamp_int(st.session_state.get("ui_llm_max_tokens"), settings.llm.max_tokens, 64, 4096)
    session_api_key = str(st.session_state.get("ui_llm_api_key", "")).strip()
    if session_api_key:
        settings.llm.api_key = session_api_key


def _render_hero(st: Any, settings: Settings) -> None:
    llm_title, llm_desc, _ = _llm_status(settings)
    data_mode = "离线演示" if settings.data.mode == "offline" else "真实数据模式"
    data_desc = "当前用内置样例行情，适合先看懂流程。" if settings.data.mode == "offline" else "当前会尝试使用外部数据源。"
    st.markdown(
        """
        <div class="hero-box">
          <div class="hero-title">A股模拟投资小助手</div>
          <div class="hero-subtitle">
            这是一个先用于学习和模拟验证的多 Agent 系统。它不会真实下单，所有结论都应先在模拟盘观察。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "当前数据", data_mode, data_desc)
    _metric_card(c2, "LLM 状态", llm_title, llm_desc)
    _metric_card(c3, "本次最多分析", f"{int(st.session_state.ui_max_count)} 只", "从股票池里筛出更值得看的候选。")
    _metric_card(c4, "模拟资金", _format_money(float(st.session_state.ui_initial_capital)), "只用于回测和仓位换算。")


def _render_home_tab(st: Any, settings: Settings) -> None:
    st.subheader("如果你是第一次用，按这 3 步来")
    c1, c2, c3 = st.columns(3)
    _metric_card(c1, "第 1 步", "先选风格", "左侧选择保守/平衡/激进，设置模拟资金和止损。")
    _metric_card(c2, "第 2 步", "点一键分析", "系统会筛股票、打分、风控，并输出人能读懂的建议。")
    _metric_card(c3, "第 3 步", "看模拟回测", "先看历史上这套规则大概表现如何，再决定是否继续改进。")

    st.info(
        "你之前看到的 JSON 现在默认隐藏了。页面会优先展示结论卡片、理由、风险提示和术语解释；"
        "原始 JSON 只放在“高级：查看原始 JSON”里。"
    )
    if settings.llm.api_key:
        st.success("已检测到 LLM Key。你可以去“LLM / 模型”页拉取模型列表、跑模型测试，或在报告里让 LLM 做小白话解读。")
    else:
        st.warning(
            "当前还没有启用 LLM Key，所以投资结论主要来自规则 Agent 和离线样例数据。"
            "这不是 offline mode 的 bug：offline 指的是行情数据离线；LLM 需要单独填写 API Key。"
        )

    with st.expander("常见术语用大白话解释", expanded=True):
        for term, explanation in TERM_HELP.items():
            st.markdown(f"**{term}**：{explanation}")

    st.markdown("### 这个系统现在能做什么")
    st.markdown(
        "- 每天收盘后跑一次模拟分析，生成候选股票和买/不买理由。\n"
        "- 用模拟资金计算建议仓位，不会触发真实交易。\n"
        "- 用回测粗略检查策略历史表现。\n"
        "- LLM 配好后，可以做模型连通性测试和报告小白话解释。\n"
        "- 当前仍是 MVP，不构成投资建议。"
    )


def _render_watch_tab(st: Any, settings: Settings) -> None:
    st.subheader("自动投资观测看板")
    st.caption(
        "这里集中查看：每个 LLM 模型账户的资金排名、当前持仓盈亏、今日是否已经执行、以及潜力股票/舆情风险摘要。"
    )
    st.warning("当前仍是模拟盘：系统会自动记录模拟买卖和止损，但不会真实下单。")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("刷新持仓/排行榜", use_container_width=True):
            st.session_state["ui_watch_competition"] = _load_latest_persisted_competition(settings)
    with c2:
        if st.button("运行一次自动投资轮次", type="primary", use_container_width=True):
            models = [item.strip() for item in str(st.session_state.ui_compete_models).split(",") if item.strip()]
            with st.spinner("正在让各模型账户自动观察、决策并更新模拟盘..."):
                result = MultiAgentOrchestrator(settings=settings).run_competition(
                    models=models or None,
                    max_count=int(st.session_state.ui_max_count),
                    history_days=int(st.session_state.ui_history_days),
                    initial_capital=float(st.session_state.ui_initial_capital),
                    persist=True,
                    continue_from_storage=True,
                )
            st.session_state["ui_watch_competition"] = result
            st.session_state["ui_compete_result"] = result
    with c3:
        if st.button("刷新潜力股票/舆情", use_container_width=True):
            with st.spinner("正在筛选潜力股票并汇总舆情/风险..."):
                st.session_state["ui_watch_daily_report"] = MasterAgent(settings=settings).run_daily(
                    max_count=int(st.session_state.ui_max_count),
                    history_days=int(st.session_state.ui_history_days),
                ).to_dict()

    result = st.session_state.get("ui_watch_competition")
    if not result:
        result = _load_latest_persisted_competition(settings)
        st.session_state["ui_watch_competition"] = result
    _render_watch_competition_snapshot(st, result)

    st.divider()
    _render_watch_opportunities(st, settings)


def _render_watch_competition_snapshot(st: Any, result: dict[str, Any]) -> None:
    if result.get("status") == "skipped":
        st.info(f"暂时没有可展示的持仓快照：{result.get('reason', '请先运行一次自动投资轮次并保存到 MongoDB')}。")
        return
    if result.get("status") != "ok":
        st.error(f"读取观测数据异常：{result}")
        return

    rankings = [item for item in result.get("rankings", []) if isinstance(item, dict)]
    agents = [item for item in result.get("agents", []) if isinstance(item, dict)]
    position_rows = _watch_position_rows(agents)
    leader = rankings[0] if rankings else {}
    total_equity = sum(_as_float(agent.get("equity")) for agent in agents)
    floating_pnl = sum(_as_float(row.get("floating_pnl_raw")) for row in position_rows)
    skipped_count = sum(1 for item in rankings if item.get("skipped_execution"))

    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "当前冠军模型", str(leader.get("llm_model", "-")), f"日期：{result.get('run_date', '-')}")
    _metric_card(c2, "账户总权益", _format_money(total_equity), "所有模型账户权益合计。")
    _metric_card(c3, "持仓浮盈亏", _format_money(floating_pnl), "当前持仓未实现盈亏合计。")
    _metric_card(c4, "今日保护", f"{skipped_count} 个已跳过", "同日重复运行会自动防止重复交易。")

    if skipped_count:
        st.info("检测到部分账户今天已经运行过。本次看板会显示已有快照，不会重复买入/卖出。")

    if rankings:
        st.markdown("#### LLM 资金排行榜")
        st.dataframe(_watch_ranking_rows(rankings), hide_index=True, use_container_width=True)

    st.markdown("#### 当前持仓与盈亏")
    if position_rows:
        display_rows = [{key: value for key, value in row.items() if key != "floating_pnl_raw"} for row in position_rows]
        st.dataframe(display_rows, hide_index=True, use_container_width=True)
    else:
        st.info("当前还没有模型账户持仓。")


def _render_watch_opportunities(st: Any, settings: Settings) -> None:
    st.markdown("### 潜力股票与舆情/风险摘要")
    payload = st.session_state.get("ui_watch_daily_report")
    if not payload:
        st.info("点击“刷新潜力股票/舆情”后，这里会显示候选股票、系统动作、舆情评分和风控摘要。")
        return
    if not isinstance(payload, dict):
        st.warning("潜力股票结果格式异常，请重新刷新。")
        return
    reports = [item for item in payload.get("reports", []) if isinstance(item, dict)]
    if not reports:
        st.info("本次没有筛出候选股票。")
        return
    st.caption(
        f"报告日期：{payload.get('run_date', '-')}；数据模式：{((payload.get('metadata') or {}).get('data_mode') if isinstance(payload.get('metadata'), dict) else settings.data.mode)}。"
    )
    st.dataframe(_watch_opportunity_rows(reports), hide_index=True, use_container_width=True)
    with st.expander("高级：查看潜力股票原始 JSON"):
        st.json(payload)


def _render_run_tab(st: Any, settings: Settings) -> None:
    st.subheader("一键生成今天的模拟投资建议")
    st.caption("系统会：动态筛选股票 -> 多个 Agent 打分 -> 风控检查 -> 给出模拟买入/观察/拒绝。")
    st.warning("重要提醒：这是学习和模拟验证工具，不是荐股软件，也不会真实下单。")

    if st.button("开始分析并保存报告", type="primary", use_container_width=True):
        with st.spinner("正在分析样例股票和生成报告，请稍等..."):
            report = MasterAgent(settings=settings).run_daily(
                max_count=int(st.session_state.ui_max_count),
                history_days=int(st.session_state.ui_history_days),
            )
            saved = save_daily_report(report)
        st.success("分析完成，报告已经保存。")
        st.caption(_saved_report_text(saved))
        _render_daily_or_stock_report(st, report.to_dict(), settings=settings, key_prefix="latest_report")


def _render_reports_tab(st: Any, settings: Settings) -> None:
    st.subheader("历史报告")
    report_files = _load_report_files()
    if not report_files:
        st.info("暂无报告。请先去“一键分析”页生成一份报告。")
        return
    selected = st.selectbox(
        "选择一份报告",
        report_files,
        format_func=lambda path: str(path.relative_to(PROJECT_ROOT)),
        key="saved_report_picker",
    )
    payload = _read_json(selected)
    if payload:
        safe_key = _safe_key(str(selected.relative_to(PROJECT_ROOT)))
        _render_daily_or_stock_report(st, payload, settings=settings, key_prefix=f"saved_{safe_key}")
    else:
        st.error("这份报告无法读取，可能文件损坏或不是 JSON。")


def _render_backtest_tab(st: Any, settings: Settings) -> None:
    st.subheader("模拟回测：先看历史表现，再考虑优化")
    st.caption("回测是把当前规则放到过去行情里重放一遍，只能帮助发现明显问题，不能保证未来收益。")
    stock_codes_text = st.text_input(
        "指定股票代码，可留空",
        help="多个代码用英文逗号分隔，例如 600519,000333。留空则使用动态筛选。",
        key="backtest_stock_codes",
    )
    if st.button("运行模拟回测", type="primary"):
        stock_codes = [item.strip() for item in stock_codes_text.split(",") if item.strip()] or None
        with st.spinner("正在回放历史数据..."):
            result = BacktestEngine(settings=settings).run(
                stock_codes=stock_codes,
                max_count=int(st.session_state.ui_max_count),
                initial_capital=float(st.session_state.ui_initial_capital),
                history_days=int(st.session_state.ui_history_days),
            )
        _render_backtest_result(st, result.to_dict())


def _render_llm_tab(st: Any, settings: Settings) -> None:
    st.subheader("LLM / 模型测试")
    st.caption(
        "这里专门处理你关心的 LLM 元素：连接状态、模型列表、模型 bench、以及 LLM 模拟盘排行榜。"
        "API Key 可以来自本地 .env，也可以只在当前页面临时填写；页面保存设置时不会保存 Key。"
    )

    st.text_input("LLM Base URL", key="ui_llm_base_url", help="OpenAI 兼容网关地址，例如 https://example.com/v1")
    st.text_input("LLM API Key（只在本次 Streamlit 会话中使用）", type="password", key="ui_llm_api_key")
    st.text_input("默认模型", key="ui_llm_default_model", help="可以手动填写，也可以先获取模型列表后选择。")
    c_profile, c_tokens = st.columns(2)
    with c_profile:
        st.selectbox(
            "请求方式 profile",
            ["auto", "openai", "codex", "anthropic", "claude_code"],
            key="ui_llm_request_profile",
            help="auto 会依次尝试 OpenAI/Codex/Anthropic/Claude Code；新网关通常用 auto 或 openai。",
        )
    with c_tokens:
        st.number_input("单次最多输出 tokens", min_value=64, max_value=4096, step=64, key="ui_llm_max_tokens")
    _apply_session_settings(st, settings)

    llm_title, llm_desc, llm_state = _llm_status(settings)
    if llm_state == "ok":
        st.success(f"{llm_title}：{llm_desc}")
    elif llm_state == "partial":
        st.warning(f"{llm_title}：{llm_desc}")
    else:
        st.info(f"{llm_title}：{llm_desc}")

    client = LLMClient(settings)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("获取模型列表", use_container_width=True):
            with st.spinner("正在请求 /models..."):
                st.session_state["ui_models_result"] = client.list_models_safe()
    with c2:
        if st.button("清空模型测试结果", use_container_width=True):
            st.session_state.pop("ui_models_result", None)
            st.session_state.pop("ui_bench_result", None)
            st.success("已清空。")

    _render_model_list_result(st)

    st.markdown("### 跑一次模型 bench")
    st.caption("bench 只测试模型能否连通、响应速度如何、能否稳定输出 JSON，不代表投资能力。")
    st.text_input("要测试的模型，逗号分隔；留空则使用模型列表或默认模型", key="ui_bench_models")
    st.number_input("最多测试几个模型", min_value=1, max_value=10, step=1, key="ui_bench_limit")
    st.text_area("测试提示词", key="ui_bench_prompt", height=110)
    if st.button("开始模型 bench", type="primary"):
        models = [item.strip() for item in str(st.session_state.ui_bench_models).split(",") if item.strip()]
        with st.spinner("正在测试模型，遇到 429 会按后端重试规则等待..."):
            st.session_state["ui_bench_result"] = ModelBench(client).run(
                models=models or None,
                prompt=str(st.session_state.ui_bench_prompt),
                limit=int(st.session_state.ui_bench_limit),
            )
    _render_bench_result(st)

    st.divider()
    _render_competition_section(st, settings)


def _render_config_tab(st: Any, settings: Settings) -> None:
    st.subheader("可编辑设置")
    st.caption("左侧栏修改后会立刻影响本次运行；点击保存后会写入 data/runtime/ui_settings.json。API Key 永远不会保存。")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("保存当前非敏感设置", type="primary", use_container_width=True):
            saved_path = _save_ui_settings(_collect_ui_settings(st))
            st.success(f"已保存到 {saved_path.relative_to(PROJECT_ROOT)}")
    with c2:
        if st.button("清空本地保存设置", use_container_width=True):
            if UI_SETTINGS_PATH.exists():
                UI_SETTINGS_PATH.unlink()
            st.success("已清空本地 UI 设置。刷新后会回到 config.yaml / 环境变量默认值。")

    rows = [
        {"设置项": "数据模式", "当前值": settings.data.mode, "说明": TERM_HELP["离线模式"]},
        {"设置项": "模拟盘初始资金", "当前值": _format_money(settings.portfolio.initial_capital), "说明": "只用于仓位和回测换算。"},
        {"设置项": "最多分析股票数", "当前值": str(settings.data.dynamic_universe_limit), "说明": "数量越多，分析越慢。"},
        {"设置项": "单股最大仓位", "当前值": _format_pct(settings.risk.max_position_per_stock), "说明": TERM_HELP["仓位"]},
        {"设置项": "总仓位上限", "当前值": _format_pct(settings.risk.max_total_position), "说明": "控制整个账户最多投入多少钱。"},
        {"设置项": "止损比例", "当前值": _format_pct(settings.risk.stop_loss_pct), "说明": TERM_HELP["止损"]},
        {"设置项": "LLM Base URL", "当前值": settings.llm.base_url, "说明": "非敏感，可保存。"},
        {"设置项": "默认模型", "当前值": settings.llm.default_model or "未填写", "说明": "非敏感，可保存。"},
        {"设置项": "LLM 请求方式", "当前值": settings.llm.request_profile, "说明": "auto 会自动探测多种兼容请求形态。"},
        {"设置项": "LLM Max Tokens", "当前值": str(settings.llm.max_tokens), "说明": "限制单次输出长度，控制成本和速度。"},
        {"设置项": "LLM API Key", "当前值": "已配置" if settings.llm.api_key else "未配置", "说明": "敏感信息，不保存到文件。"},
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)

    with st.expander("高级：查看当前非敏感配置 JSON"):
        st.json(_non_sensitive_config(settings))


def _load_report_files() -> list[Path]:
    reports_dir = PROJECT_ROOT / "reports"
    if not reports_dir.exists():
        return []
    return sorted(reports_dir.rglob("*.json"), reverse=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _render_daily_or_stock_report(
    st: Any,
    payload: dict[str, Any],
    settings: Settings | None = None,
    key_prefix: str = "report",
) -> None:
    if "reports" not in payload:
        _render_stock_report(st, payload, settings=settings, key_prefix=key_prefix)
        return

    reports = [item for item in payload.get("reports", []) if isinstance(item, dict)]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    st.markdown("### 每日模拟决策摘要")
    c1, c2, c3, c4 = st.columns(4)
    buy_count = sum(1 for item in reports if ((item.get("decision") or {}).get("action") == "BUY"))
    reject_count = sum(1 for item in reports if ((item.get("decision") or {}).get("action") == "REJECT"))
    _metric_card(c1, "报告日期", str(payload.get("run_date", "未知")), "这是本次定盘分析生成时间。")
    _metric_card(c2, "候选股票", f"{len(reports)} 只", "系统从股票池里筛出的重点观察对象。")
    _metric_card(c3, "模拟买入", f"{buy_count} 只", "只是模拟建议，不会真实下单。")
    _metric_card(c4, "风控拒绝", f"{reject_count} 只", "风险不合格或理由不足的股票。")

    st.caption(
        f"数据模式：{metadata.get('data_mode', 'unknown')}；参考历史：{metadata.get('history_days', 'unknown')} 天。"
    )
    if not reports:
        st.info("这份报告里没有股票明细。")
        return

    rows = [_stock_summary_row(item) for item in reports]
    st.dataframe(rows, hide_index=True, use_container_width=True)

    selected_idx = st.selectbox(
        "选择一只股票，看小白话详细解释",
        list(range(len(reports))),
        format_func=lambda idx: rows[int(idx)]["股票"],
        key=f"{key_prefix}_stock_selector",
    )
    _render_stock_report(st, reports[int(selected_idx)], settings=settings, key_prefix=f"{key_prefix}_{selected_idx}")

    with st.expander("高级：查看整份原始 JSON"):
        st.json(payload)


def _render_stock_report(st: Any, payload: dict[str, Any], settings: Settings | None, key_prefix: str) -> None:
    stock = payload.get("stock") if isinstance(payload.get("stock"), dict) else {}
    quote = payload.get("quote") if isinstance(payload.get("quote"), dict) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    stock_label = _stock_label(stock, quote)
    action = str(decision.get("action", "HOLD"))
    action_text, action_desc = ACTION_COPY.get(action, (action, "这是系统给出的模拟动作。"))

    st.markdown(f"### {stock_label}")
    st.markdown(_action_badge(action, action_text), unsafe_allow_html=True)
    st.caption(action_desc)

    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "最新价", _format_price(quote.get("price")), f"涨跌幅 {_format_pct(_as_float(quote.get('change_pct')))}")
    _metric_card(c2, "系统把握", _format_pct(_as_float(decision.get("confidence"))), TERM_HELP["置信度"])
    _metric_card(c3, "建议仓位", _format_pct(_as_float(decision.get("position_size"))), TERM_HELP["仓位"])
    _metric_card(c4, "止损价", _format_price(decision.get("stop_loss")), TERM_HELP["止损"])

    _render_decision_reasons(st, decision)
    _render_llm_report_explainer(st, settings, payload, key_prefix)

    st.markdown("#### 多 Agent 分析拆解")
    agent_items = [
        ("technical", "技术面 Agent", payload.get("technical")),
        ("fundamental", "基本面 Agent", payload.get("fundamental")),
        ("sentiment", "舆情 Agent", payload.get("sentiment")),
        ("debate", "多 Agent 讨论", payload.get("debate")),
        ("risk", "风控 Agent", payload.get("risk")),
    ]
    for agent_key, title, result in agent_items:
        if isinstance(result, dict):
            _render_agent_result(st, agent_key, title, result)

    with st.expander("高级：查看这只股票的原始 JSON"):
        st.json(payload)


def _render_decision_reasons(st: Any, decision: dict[str, Any]) -> None:
    reasons = _as_list(decision.get("reasons"))
    risks = _as_list(decision.get("risk_notes"))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 为什么是这个结论")
        if reasons:
            for reason in reasons[:6]:
                st.markdown(f"- {reason}")
        else:
            st.caption("这份报告没有写入明确理由。")
    with c2:
        st.markdown("#### 需要先注意的风险")
        if risks:
            for risk in risks[:6]:
                st.markdown(f"- {risk}")
        else:
            st.caption("暂未发现硬性风险，但仍需模拟观察。")


def _render_agent_result(st: Any, agent_key: str, title: str, result: dict[str, Any]) -> None:
    label = str(result.get("label", ""))
    score = _as_float(result.get("score"))
    with st.expander(f"{title}：{label or '未标注'} / {_format_pct(score)}"):
        st.caption(AGENT_HELP.get(agent_key, "这是一个分析模块。"))
        _score_bar(st, score)
        reasons = _as_list(result.get("reasons"))
        risks = _as_list(result.get("risks"))
        if reasons:
            st.markdown("**主要理由**")
            for reason in reasons[:5]:
                st.markdown(f"- {reason}")
        if risks:
            st.markdown("**风险提示**")
            for risk in risks[:5]:
                st.markdown(f"- {risk}")


def _render_llm_report_explainer(st: Any, settings: Settings | None, payload: dict[str, Any], key_prefix: str) -> None:
    st.markdown("#### LLM 小白话解读")
    if settings is None or not settings.llm.api_key:
        st.info("还没有配置 LLM API Key。配置后，这里可以把 Agent 报告改写成更像人话的解释。")
        return
    if not settings.llm.default_model:
        st.warning("已检测到 API Key，但还没有选择默认模型。请先去“LLM / 模型”页填写或选择默认模型。")
        return

    result_key = f"{key_prefix}_llm_explain_result"
    if st.button("让 LLM 用小白话解释这份报告", key=f"{key_prefix}_llm_explain_button"):
        prompt = _build_llm_report_prompt(payload)
        try:
            with st.spinner("正在调用 LLM 生成解释..."):
                chat = LLMClient(settings).chat_json(
                    messages=[
                        {"role": "system", "content": "你是面向投资新手的报告解释助手，只输出 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
            st.session_state[result_key] = chat.to_dict()
        except Exception as exc:  # pragma: no cover - external service guard
            st.session_state[result_key] = {"error": str(exc)}

    result = st.session_state.get(result_key)
    if not result:
        return
    if result.get("error"):
        st.error(f"LLM 调用失败：{result['error']}")
        return
    parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else {}
    if parsed:
        summary = parsed.get("summary") or parsed.get("结论")
        if summary:
            st.success(str(summary))
        for title, field in [("理由", "why"), ("风险", "risks"), ("下一步", "next_steps")]:
            values = _as_list(parsed.get(field))
            if values:
                st.markdown(f"**{title}**")
                for value in values[:5]:
                    st.markdown(f"- {value}")
    else:
        st.write(result.get("content", "LLM 没有返回可解析内容。"))


def _render_backtest_result(st: Any, data: dict[str, Any]) -> None:
    st.markdown("### 回测结果")
    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "总收益", _format_pct(_as_float(data.get("total_return"))), "历史回放中的账户总涨跌。")
    _metric_card(c2, "最大回撤", _format_pct(_as_float(data.get("max_drawdown"))), TERM_HELP["最大回撤"])
    _metric_card(c3, "胜率", _format_pct(_as_float(data.get("win_rate"))), "已卖出交易里赚钱的比例。")
    _metric_card(c4, "最终权益", _format_money(_as_float(data.get("final_equity"))), "回测结束时的账户价值。")

    if data.get("status") != "ok":
        st.warning(f"回测状态：{data.get('status')}。可能是样例数据不够长。")
    if _as_float(data.get("max_drawdown")) > 0.20:
        st.warning("最大回撤超过 20%，对新手来说波动可能偏大，建议降低仓位或提高风控要求。")

    curve = data.get("equity_curve") if isinstance(data.get("equity_curve"), list) else []
    if curve:
        st.markdown("#### 账户权益曲线")
        st.line_chart([_as_float(row.get("equity")) for row in curve if isinstance(row, dict)])
        with st.expander("查看每日权益明细"):
            st.dataframe(curve, hide_index=True, use_container_width=True)

    trades = data.get("trades") if isinstance(data.get("trades"), list) else []
    if trades:
        st.markdown("#### 交易记录")
        st.dataframe(trades, hide_index=True, use_container_width=True)
    else:
        st.info("这次回测没有产生交易，可能说明规则较保守或样例周期较短。")

    with st.expander("高级：查看回测原始 JSON"):
        st.json(data)


def _render_model_list_result(st: Any) -> None:
    result = st.session_state.get("ui_models_result")
    if not result:
        st.info("点击“获取模型列表”后，这里会显示网关返回的模型。")
        return

    status = result.get("status")
    if status == "ok":
        models = [str(item) for item in result.get("models", [])]
        st.success(f"获取成功：共 {len(models)} 个模型。")
        if models:
            selected = st.selectbox("选择一个模型设为默认", models, key="ui_model_picker")
            if st.button("设为默认模型", use_container_width=True):
                st.session_state["ui_llm_default_model"] = selected
                st.success(f"已设为默认模型：{selected}")
                _rerun(st)
            st.dataframe([{"模型 ID": item} for item in models], hide_index=True, use_container_width=True)
    elif status == "skipped":
        st.warning("还没有 API Key，无法获取模型列表。请先填写 LLM API Key。")
    else:
        st.error(f"获取模型列表失败：{result.get('reason', '未知错误')}")


def _render_bench_result(st: Any) -> None:
    result = st.session_state.get("ui_bench_result")
    if not result:
        return
    if result.get("status") == "skipped":
        st.warning(f"模型测试跳过：{result.get('reason', '未配置')}")
        return
    if result.get("status") != "ok":
        st.error(f"模型测试异常：{result}")
        return

    c1, c2, c3 = st.columns(3)
    _metric_card(c1, "成功率", _format_pct(_as_float(result.get("success_rate"))), "能正常返回的模型比例。")
    _metric_card(c2, "JSON 稳定性", _format_pct(_as_float(result.get("json_parse_rate"))), "能否按要求输出结构化 JSON。")
    _metric_card(c3, "测试模型数", str(result.get("model_count", 0)), "本次参与 bench 的模型数量。")

    rows = []
    for item in result.get("results", []):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "模型": item.get("model"),
                "状态": item.get("status"),
                "实际请求方式": item.get("profile", ""),
                "耗时秒": item.get("latency_seconds"),
                "JSON 可解析": "是" if item.get("json_parseable") else "否",
                "诊断摘要": _bench_error_summary(item),
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)
    with st.expander("高级：查看 bench 原始 JSON"):
        st.json(result)


def _watch_ranking_rows(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "排名": item.get("rank"),
            "模型": item.get("llm_model"),
            "总收益": _format_pct(_as_float(item.get("total_return"))),
            "账户权益": _format_money(_as_float(item.get("equity"))),
            "现金": _format_money(_as_float(item.get("cash"))),
            "当日盈亏": _format_money(_as_float(item.get("daily_pnl"))),
            "执行状态": "已跳过" if item.get("skipped_execution") else "已执行",
            "说明": _skip_reason_text(str(item.get("skip_reason", ""))) if item.get("skipped_execution") else "本轮已完成模拟交易检查",
        }
        for item in rankings
    ]


def _watch_position_rows(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agent in agents:
        model = str(agent.get("llm_model", "-"))
        positions = agent.get("positions", []) if isinstance(agent.get("positions"), list) else []
        for item in positions:
            if not isinstance(item, dict):
                continue
            floating = _as_float(item.get("unrealized_pnl"))
            rows.append(
                {
                    "模型": model,
                    "股票": str(item.get("stock_code", "-")),
                    "股数": item.get("shares", 0),
                    "成本价": _format_price(item.get("cost_basis")),
                    "当前价": _format_price(item.get("current_price")),
                    "市值": _format_money(_as_float(item.get("market_value"))),
                    "浮动盈亏": _format_money(floating),
                    "浮动收益": _format_pct(_as_float(item.get("unrealized_return"))),
                    "最近买入日": item.get("last_buy_date", ""),
                    "floating_pnl_raw": floating,
                }
            )
    return rows


def _watch_opportunity_rows(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in reports:
        stock = item.get("stock") if isinstance(item.get("stock"), dict) else {}
        quote = item.get("quote") if isinstance(item.get("quote"), dict) else {}
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        sentiment = item.get("sentiment") if isinstance(item.get("sentiment"), dict) else {}
        risk = item.get("risk") if isinstance(item.get("risk"), dict) else {}
        action = str(decision.get("action", "HOLD"))
        rows.append(
            {
                "股票": _stock_label(stock, quote),
                "动作": ACTION_COPY.get(action, (action, ""))[0],
                "系统把握": _format_pct(_as_float(decision.get("confidence"))),
                "建议仓位": _format_pct(_as_float(decision.get("position_size"))),
                "最新价": _format_price(quote.get("price")),
                "涨跌幅": _format_pct(_as_float(quote.get("change_pct"))),
                "舆情评分": _format_pct(_as_float(sentiment.get("score"))),
                "风控评分": _format_pct(_as_float(risk.get("score"))),
                "主要理由": "; ".join(_as_list(decision.get("reasons"))[:2]) or "暂无",
                "主要风险": "; ".join(_as_list(decision.get("risk_notes"))[:2]) or "暂无",
            }
        )
    return rows


def _render_competition_section(st: Any, settings: Settings) -> None:
    st.markdown("### LLM 模拟盘排行榜")
    st.caption(
        "每个模型会管理一个独立虚拟账户，先由规则 Agent 生成报告，再由该模型复核动作。"
        "没有 API Key 或模型调用失败时，会自动降级为规则基线，保证模拟盘可以继续跑。"
    )

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.text_input(
            "参与比赛的模型，逗号分隔",
            key="ui_compete_models",
            help="建议至少保留 rule-baseline 作为规则基准；例如 rule-baseline,gpt-4o-mini,deepseek-chat。",
        )
    with c2:
        st.checkbox(
            "从上次快照续跑",
            key="ui_compete_continue",
            help="如果 MongoDB 里有该模型账户的最新持仓，会从上次现金/持仓继续；没有则自动从初始资金开始。",
        )
    with c3:
        st.checkbox(
            "保存到 MongoDB（可选）",
            key="ui_compete_persist",
            help="本地没装 pymongo 或没启动 MongoDB 时会自动跳过。新手可先不勾选。",
        )

    if st.button("读取 MongoDB 最新排行榜/持仓", use_container_width=True):
        with st.spinner("正在读取最近一次持久化的排行榜和持仓快照..."):
            st.session_state["ui_compete_result"] = _load_latest_persisted_competition(settings)

    if st.button("运行一次 LLM 模拟盘比赛", type="primary", use_container_width=True):
        models = [item.strip() for item in str(st.session_state.ui_compete_models).split(",") if item.strip()]
        with st.spinner("正在让每个模型独立跑一遍模拟盘，请稍等..."):
            st.session_state["ui_compete_result"] = MultiAgentOrchestrator(settings=settings).run_competition(
                models=models or None,
                max_count=int(st.session_state.ui_max_count),
                history_days=int(st.session_state.ui_history_days),
                initial_capital=float(st.session_state.ui_initial_capital),
                persist=bool(st.session_state.ui_compete_persist),
                continue_from_storage=bool(st.session_state.ui_compete_continue),
            )
    _render_competition_result(st)


def _render_competition_result(st: Any) -> None:
    result = st.session_state.get("ui_compete_result")
    if not result:
        st.info("点击“运行一次 LLM 模拟盘比赛”后，这里会显示排行榜、各账户持仓和交易记录。")
        return
    if result.get("status") == "skipped":
        st.warning(f"暂时读不到持久化数据：{result.get('reason', 'MongoDB 未配置或没有数据')}。")
        return
    if result.get("status") != "ok":
        st.error(f"比赛运行异常：{result}")
        return

    rankings = [item for item in result.get("rankings", []) if isinstance(item, dict)]
    agents = [item for item in result.get("agents", []) if isinstance(item, dict)]
    st.success(f"比赛完成：{result.get('run_date')}，共 {result.get('model_count', len(agents))} 个模型账户。")
    skipped_count = sum(1 for item in rankings if item.get("skipped_execution"))
    if skipped_count:
        st.info(
            f"有 {skipped_count} 个模型账户今天已经运行过，本次只读取已有持仓快照，没有重复买入/卖出。"
            "如果你确实想重新开始，请取消“从上次持仓继续”或使用 fresh-start。"
        )
    llm_review_count, fallback_count = _competition_review_counts(agents)

    if rankings:
        leader = rankings[0]
        c1, c2, c3, c4 = st.columns(4)
        _metric_card(c1, "当前第一名", str(leader.get("llm_model", "-")), "按账户总收益率排序。")
        _metric_card(c2, "第一名收益", _format_pct(_as_float(leader.get("total_return"))), "本轮模拟后的账户涨跌。")
        _metric_card(c3, "第一名权益", _format_money(_as_float(leader.get("equity"))), "现金加持仓市值。")
        _metric_card(c4, "LLM 复核", f"{llm_review_count} 次", f"规则回退 {fallback_count} 次。")

        rows = []
        for item in rankings:
            rows.append(
                {
                    "排名": item.get("rank"),
                    "模型": item.get("llm_model"),
                    "总收益": _format_pct(_as_float(item.get("total_return"))),
                    "最大回撤": _format_pct(_as_float(item.get("max_drawdown"))),
                    "胜率": _format_pct(_as_float(item.get("win_rate"))),
                    "账户权益": _format_money(_as_float(item.get("equity"))),
                    "现金": _format_money(_as_float(item.get("cash"))),
                    "当日盈亏": _format_money(_as_float(item.get("daily_pnl"))),
                    "是否续跑": "是" if item.get("restored_from_snapshot") else "否",
                    "执行状态": "已跳过" if item.get("skipped_execution") else "已执行",
                    "跳过原因": _skip_reason_text(str(item.get("skip_reason", ""))),
                    "上次日期": item.get("previous_snapshot_date", ""),
                    "买入次数": item.get("buy_count"),
                    "卖出次数": item.get("sell_count"),
                }
            )
        st.markdown("#### 排行榜")
        st.dataframe(rows, hide_index=True, use_container_width=True)

    if not agents:
        st.info("本次没有账户详情。")
        return

    label_by_agent = {str(agent.get("agent_id")): f"{agent.get('llm_model')}｜{agent.get('agent_id')}" for agent in agents}
    selected_agent_id = st.selectbox(
        "选择一个模型账户，看持仓和决策",
        list(label_by_agent),
        format_func=lambda key: label_by_agent.get(str(key), str(key)),
        key="ui_compete_agent_picker",
    )
    selected = next((agent for agent in agents if str(agent.get("agent_id")) == str(selected_agent_id)), agents[0])
    _render_competition_agent_detail(st, selected)

    persisted = result.get("persisted") if isinstance(result.get("persisted"), dict) else None
    if persisted:
        status = persisted.get("status")
        if status == "ok":
            st.caption(
                f"已写入 MongoDB：快照 {persisted.get('snapshots', 0)} 条，交易 {persisted.get('trades', 0)} 条，"
                f"决策 {persisted.get('decisions', 0)} 条。"
            )
        elif status == "skipped":
            st.caption(f"持久化已跳过：{persisted.get('reason', '未配置 MongoDB 或 pymongo')}。")

    with st.expander("高级：查看比赛原始 JSON"):
        st.json(result)


def _load_latest_persisted_competition(settings: Settings) -> dict[str, Any]:
    try:
        from astock_agent_system.storage import MongoClient

        mongo = MongoClient(settings)
        ranking = mongo.get_latest_ranking()
        if not ranking:
            mongo.close()
            return {"status": "skipped", "reason": "MongoDB 中还没有 LLM 排行榜，请先勾选保存并运行一次比赛。"}

        snapshots = mongo.get_latest_position_snapshots()
        snapshot_by_agent = {str(item.get("agent_id", "")): item for item in snapshots if isinstance(item, dict)}
        rankings = _storage_ranking_rows(ranking)
        agents: list[dict[str, Any]] = []
        for row in rankings:
            agent_id = str(row.get("agent_id", ""))
            if not agent_id:
                continue
            snapshot = snapshot_by_agent.get(agent_id, {})
            decisions = mongo.get_agent_decisions(agent_id, limit=20)
            trades = mongo.get_trades(agent_id=agent_id, limit=50)
            agents.append(_storage_agent_row(row, snapshot, decisions, trades))
        mongo.close()
        return {
            "status": "ok",
            "run_date": str(ranking.get("date", "")),
            "model_count": len(agents),
            "rankings": rankings,
            "agents": agents,
            "persisted": {
                "status": "loaded",
                "source": "MongoDB",
                "snapshot_count": len(snapshots),
            },
        }
    except Exception as exc:  # pragma: no cover - optional storage guard
        return {"status": "skipped", "reason": str(exc)}


def _storage_ranking_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    rows = ranking.get("rankings") if isinstance(ranking.get("rankings"), list) else []
    safe_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        safe = _json_safe(row)
        if isinstance(safe, dict):
            safe.setdefault("rank", idx)
            safe_rows.append(safe)
    return safe_rows


def _storage_agent_row(
    ranking: dict[str, Any],
    snapshot: dict[str, Any],
    decisions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    agent_id = str(ranking.get("agent_id") or snapshot.get("agent_id") or "")
    initial_capital = _as_float(snapshot.get("initial_capital") or ranking.get("initial_capital") or 0.0)
    equity = _as_float(snapshot.get("equity") or ranking.get("equity") or initial_capital)
    cash = _as_float(snapshot.get("cash") or ranking.get("cash") or 0.0)
    total_return = _as_float(ranking.get("total_return"))
    if not total_return and initial_capital:
        total_return = (equity - initial_capital) / initial_capital
    return {
        "agent_id": agent_id,
        "llm_model": str(ranking.get("llm_model") or agent_id),
        "initial_capital": round(initial_capital, 4),
        "equity": round(equity, 4),
        "cash": round(cash, 4),
        "total_return": round(total_return, 6),
        "max_drawdown": _as_float(ranking.get("max_drawdown")),
        "win_rate": _as_float(ranking.get("win_rate")),
        "total_trades": int(_as_float(ranking.get("total_trades"))),
        "buy_count": int(_as_float(ranking.get("buy_count"))),
        "sell_count": int(_as_float(ranking.get("sell_count"))),
        "daily_pnl": _as_float(snapshot.get("daily_pnl") or ranking.get("daily_pnl")),
        "restored_from_snapshot": True,
        "previous_snapshot_date": str(snapshot.get("previous_snapshot_date") or snapshot.get("date") or ""),
        "previous_equity": _as_float(snapshot.get("previous_equity")),
        "skipped_execution": bool(snapshot.get("skipped_execution") or ranking.get("skipped_execution")),
        "skip_reason": str(snapshot.get("skip_reason") or ranking.get("skip_reason") or ""),
        "positions": _json_safe(snapshot.get("positions", [])),
        "trades": [_storage_trade_row(item) for item in trades if isinstance(item, dict)],
        "decisions": [_json_safe(item) for item in decisions if isinstance(item, dict)],
    }


def _storage_trade_row(item: dict[str, Any]) -> dict[str, Any]:
    safe = _json_safe(item)
    if not isinstance(safe, dict):
        return {}
    safe.setdefault("side", safe.get("action", ""))
    safe.setdefault("date", str(safe.get("timestamp", ""))[:10])
    return safe


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if str(key) != "_id"}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _render_competition_agent_detail(st: Any, agent: dict[str, Any]) -> None:
    st.markdown(f"#### 账户详情：{agent.get('llm_model', '-')}")
    if agent.get("skipped_execution"):
        st.info(
            "这个账户今天已经执行过自动交易，本次只是读取已有快照，没有再次下单。"
            f"原因：{_skip_reason_text(str(agent.get('skip_reason', '')))}"
        )
    c1, c2, c3, c4, c5 = st.columns(5)
    _metric_card(c1, "账户权益", _format_money(_as_float(agent.get("equity"))), "现金 + 当前持仓市值。")
    _metric_card(c2, "现金", _format_money(_as_float(agent.get("cash"))), "尚未投入的模拟资金。")
    _metric_card(c3, "总收益", _format_pct(_as_float(agent.get("total_return"))), "本账户相对初始资金的收益。")
    _metric_card(c4, "当日盈亏", _format_money(_as_float(agent.get("daily_pnl"))), "相对上一次账户权益的变化。")
    _metric_card(
        c5,
        "续跑状态",
        "已续跑" if agent.get("restored_from_snapshot") else "新账户",
        f"上次快照：{agent.get('previous_snapshot_date') or '无'}",
    )

    positions = [item for item in agent.get("positions", []) if isinstance(item, dict)]
    st.markdown("##### 当前持仓")
    if positions:
        st.dataframe(_competition_position_rows(positions), hide_index=True, use_container_width=True)
    else:
        st.info("这个账户当前没有持仓。")

    trades = [item for item in agent.get("trades", []) if isinstance(item, dict)]
    st.markdown("##### 交易记录")
    if trades:
        st.dataframe(_competition_trade_rows(trades), hide_index=True, use_container_width=True)
    else:
        st.info("这个账户本轮没有交易。")

    decisions = [item for item in agent.get("decisions", []) if isinstance(item, dict)]
    st.markdown("##### 模型决策")
    if decisions:
        st.dataframe(_competition_decision_rows(decisions), hide_index=True, use_container_width=True)
    else:
        st.info("这个账户本轮没有生成决策。")


def _skip_reason_text(reason: str) -> str:
    return {
        "already_ran_for_trade_date": "同一交易日已运行过，已自动防止重复交易",
    }.get(reason, reason or "-")


def _competition_position_rows(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "股票": str(item.get("stock_code", "-")),
            "股数": item.get("shares", 0),
            "成本价": _format_price(item.get("cost_basis")),
            "当前价": _format_price(item.get("current_price")),
            "最近买入日": item.get("last_buy_date", ""),
            "市值": _format_money(_as_float(item.get("market_value"))),
            "浮动盈亏": _format_money(_as_float(item.get("unrealized_pnl"))),
            "浮动收益": _format_pct(_as_float(item.get("unrealized_return"))),
        }
        for item in positions
    ]


def _competition_trade_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "日期": item.get("date", "-"),
            "股票": item.get("stock_code", "-"),
            "方向": "买入" if item.get("side") == "BUY" else "卖出" if item.get("side") == "SELL" else item.get("side", "-"),
            "价格": _format_price(item.get("price")),
            "股数": item.get("shares", 0),
            "交易后现金": _format_money(_as_float(item.get("cash_after"))),
            "已实现盈亏": _format_money(_as_float(item.get("realized_pnl"))),
            "原因": item.get("reason", "-"),
        }
        for item in trades
    ]


def _competition_decision_rows(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in decisions:
        review = item.get("llm_review") if isinstance(item.get("llm_review"), dict) else {}
        rows.append(
            {
                "股票": f"{item.get('stock_name', '-') }（{item.get('stock_code', '-')}）",
                "最终动作": ACTION_COPY.get(str(item.get("action", "HOLD")), (item.get("action", "-"), ""))[0],
                "规则动作": item.get("rule_action", "-"),
                "模型复核": review.get("source", "-"),
                "复核理由": review.get("reason", ""),
                "置信度": _format_pct(_as_float(item.get("confidence"))),
                "仓位": _format_pct(_as_float(item.get("position_size"))),
                "技术面": _format_pct(_as_float(item.get("technical_score"))),
                "基本面": _format_pct(_as_float(item.get("fundamental_score"))),
                "舆情": _format_pct(_as_float(item.get("sentiment_score"))),
                "风控": _format_pct(_as_float(item.get("risk_score"))),
                "主要理由": "; ".join(_as_list(item.get("reasons"))[:2]),
            }
        )
    return rows


def _competition_review_counts(agents: list[dict[str, Any]]) -> tuple[int, int]:
    llm_count = 0
    fallback_count = 0
    for agent in agents:
        for decision in agent.get("decisions", []) if isinstance(agent.get("decisions"), list) else []:
            if not isinstance(decision, dict):
                continue
            review = decision.get("llm_review") if isinstance(decision.get("llm_review"), dict) else {}
            if review.get("source") == "llm":
                llm_count += 1
            elif review:
                fallback_count += 1
    return llm_count, fallback_count


def _bench_error_summary(item: dict[str, Any], limit: int = 160) -> str:
    diagnostics = item.get("diagnostics") if isinstance(item.get("diagnostics"), dict) else {}
    text = str(diagnostics.get("error_summary") or item.get("error") or "")
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _metric_card(container: Any, title: str, value: str, desc: str) -> None:
    container.markdown(
        f"""
        <div class="soft-card">
          <div class="soft-card-title">{html.escape(title)}</div>
          <div class="soft-card-value">{html.escape(value)}</div>
          <div class="soft-card-desc">{html.escape(desc)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _score_bar(st: Any, score: float) -> None:
    value = max(0, min(100, int(round(score * 100))))
    st.progress(value, text=f"评分 {_format_pct(score)}")


def _stock_summary_row(item: dict[str, Any]) -> dict[str, Any]:
    stock = item.get("stock") if isinstance(item.get("stock"), dict) else {}
    quote = item.get("quote") if isinstance(item.get("quote"), dict) else {}
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    action = str(decision.get("action", "HOLD"))
    action_text, _ = ACTION_COPY.get(action, (action, ""))
    reasons = _as_list(decision.get("reasons"))
    return {
        "股票": _stock_label(stock, quote),
        "建议": action_text,
        "系统把握": _format_pct(_as_float(decision.get("confidence"))),
        "建议仓位": _format_pct(_as_float(decision.get("position_size"))),
        "最新价": _format_price(quote.get("price")),
        "目标价": _format_price(decision.get("target_price")),
        "止损价": _format_price(decision.get("stop_loss")),
        "核心理由": reasons[0] if reasons else "暂无",
    }


def _stock_label(stock: dict[str, Any], quote: dict[str, Any]) -> str:
    name = stock.get("stock_name") or quote.get("stock_name") or "未知股票"
    code = stock.get("stock_code") or quote.get("stock_code") or "未知代码"
    sector = stock.get("sector") or quote.get("sector") or ""
    return f"{name}（{code}）" + (f"｜{sector}" if sector else "")


def _action_badge(action: str, text: str) -> str:
    css = {
        "BUY": "badge-buy",
        "HOLD": "badge-hold",
        "SELL": "badge-sell",
        "REJECT": "badge-reject",
    }.get(action, "badge-reject")
    return f'<span class="badge {css}">{html.escape(text)}</span>'


def _build_llm_report_prompt(payload: dict[str, Any]) -> str:
    compact = {
        "stock": payload.get("stock"),
        "quote": payload.get("quote"),
        "technical": payload.get("technical"),
        "fundamental": payload.get("fundamental"),
        "sentiment": payload.get("sentiment"),
        "risk": payload.get("risk"),
        "decision": payload.get("decision"),
    }
    return (
        "请把下面这份 A 股模拟分析报告解释给完全不懂量化和金融术语的新手。"
        "不要给确定性承诺，不要说一定涨跌。只输出 JSON，格式为："
        "{\"summary\":\"一句话结论\",\"why\":[\"理由1\"],\"risks\":[\"风险1\"],\"next_steps\":[\"下一步1\"]}。\n"
        + json.dumps(compact, ensure_ascii=False)
    )


def _default_compete_models(settings: Settings) -> str:
    if settings.llm.default_model:
        return f"rule-baseline,{settings.llm.default_model}"
    return "rule-baseline,demo-model"


def _llm_status(settings: Settings) -> tuple[str, str, str]:
    if settings.llm.api_key and settings.llm.base_url and settings.llm.default_model:
        return "已启用", f"默认模型：{settings.llm.default_model}", "ok"
    if settings.llm.api_key and settings.llm.base_url:
        return "已填 Key，待选模型", "请在“LLM / 模型”页获取模型列表并设置默认模型。", "partial"
    if settings.llm.base_url:
        return "未启用", "尚未填写 API Key，当前只运行规则 Agent。", "off"
    return "未配置", "请先填写 OpenAI 兼容 Base URL 和 API Key。", "off"


def _load_ui_settings() -> dict[str, Any]:
    if not UI_SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(UI_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_ui_settings(payload: dict[str, Any]) -> Path:
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return UI_SETTINGS_PATH


def _collect_ui_settings(st: Any) -> dict[str, Any]:
    return {
        "risk_preset": str(st.session_state.get("ui_risk_preset", "平衡")),
        "max_count": _clamp_int(st.session_state.get("ui_max_count"), 3, 1, 20),
        "history_days": _clamp_int(st.session_state.get("ui_history_days"), 24, 6, 120),
        "initial_capital": _clamp_int(st.session_state.get("ui_initial_capital"), 100000, 10000, 100000000),
        "max_position_per_stock": _clamp_float(st.session_state.get("ui_max_position_per_stock"), 0.10, 0.01, 0.50),
        "max_total_position": _clamp_float(st.session_state.get("ui_max_total_position"), 0.50, 0.10, 1.00),
        "stop_loss_pct": _clamp_float(st.session_state.get("ui_stop_loss_pct"), 0.05, 0.01, 0.20),
        "llm_base_url": str(st.session_state.get("ui_llm_base_url", "")).strip(),
        "llm_default_model": str(st.session_state.get("ui_llm_default_model", "")).strip(),
        "llm_request_profile": str(st.session_state.get("ui_llm_request_profile", "auto")).strip(),
        "llm_max_tokens": _clamp_int(st.session_state.get("ui_llm_max_tokens"), 512, 64, 4096),
        "compete_models": str(st.session_state.get("ui_compete_models", "")).strip(),
    }


def _non_sensitive_config(settings: Settings) -> dict[str, Any]:
    return {
        "data": {
            "mode": settings.data.mode,
            "offline_data_path": settings.data.offline_data_path,
            "dynamic_universe_limit": settings.data.dynamic_universe_limit,
            "has_tushare_token": bool(settings.data.tushare_token),
        },
        "portfolio": {
            "initial_capital": settings.portfolio.initial_capital,
            "commission_rate": settings.portfolio.commission_rate,
            "stamp_tax_rate": settings.portfolio.stamp_tax_rate,
            "slippage_rate": settings.portfolio.slippage_rate,
        },
        "risk": {
            "max_position_per_stock": settings.risk.max_position_per_stock,
            "max_total_position": settings.risk.max_total_position,
            "stop_loss_pct": settings.risk.stop_loss_pct,
            "max_volatility": settings.risk.max_volatility,
            "min_turnover": settings.risk.min_turnover,
        },
        "llm": {
            "base_url": settings.llm.base_url,
            "default_model": settings.llm.default_model,
            "has_api_key": bool(settings.llm.api_key),
            "timeout_seconds": settings.llm.timeout_seconds,
            "max_retries": settings.llm.max_retries,
            "request_profile": settings.llm.request_profile,
            "max_tokens": settings.llm.max_tokens,
        },
        "smart_search": {
            "enabled": settings.smart_search.enabled,
            "timeout_seconds": settings.smart_search.timeout_seconds,
        },
    }


def _saved_report_text(saved: Any) -> str:
    if isinstance(saved, dict):
        parts = []
        for key, value in saved.items():
            if isinstance(value, (str, Path)):
                parts.append(f"{key}: {value}")
        return "保存位置：" + "；".join(parts) if parts else "报告已保存。"
    return f"保存位置：{saved}"


def _format_pct(value: float) -> str:
    return f"{value:.2%}"


def _format_money(value: float) -> str:
    return f"¥{value:,.0f}"


def _format_price(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"¥{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value is None or value == "":
        return []
    return [str(value)]


def _clamp_int(value: Any, default: int, lower: int, upper: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(lower, min(upper, number))


def _clamp_float(value: Any, default: float, lower: float, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(lower, min(upper, number))


def _safe_key(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)[:80]


def _rerun(st: Any) -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


if __name__ == "__main__":
    main()
