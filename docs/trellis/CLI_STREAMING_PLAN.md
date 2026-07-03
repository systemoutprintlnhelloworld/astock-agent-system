# CLI流式智能体运行器 - 实施计划

更新时间：2026-06-09

## 项目背景

TUI/GUI开发遇到连接和交互复杂度问题，需要先用简单的Python CLI把Agent运行的完整流程打通，实时展示：
- 输入事件（股票筛选、数据获取）
- 思考过程（各Agent评分、LLM复核）  
- 工具调用（数据查询、技术分析）
- 决策输出（买入/卖出/持有）
- 盈亏统计（持仓、收益率、排行榜）

## 命令设计

```bash
# 启动智能体（选择模型后开始运行）
python -m astock_agent_system.cli agent start [--model MODEL] [--offline] [--verbose] [--max-count N] [--days N]

# 停止运行中的智能体
python -m astock_agent_system.cli agent stop [--model MODEL]

# 显示当前状态
python -m astock_agent_system.cli agent status [--model MODEL] [--format {text|json}]

# 查看历史记录
python -m astock_agent_system.cli agent history [--model MODEL] [--limit N]

# 列出可用模型
python -m astock_agent_system.cli agent list-models

# 运行benchmark（多模型对比）
python -m astock_agent_system.cli agent benchmark [--models MODEL1,MODEL2] [--offline]

# 逐源数据源 smoke，默认只跑快速 history 检查；完整检查需显式传 checks
python -m astock_agent_system.cli datasource test [--sources tushare,baostock,akshare] [--checks history] [--format json]
```

## 实施进度

### 当前增强批次：后端真实事件桥接与新闻/公告研究缓存

本批次完成上一轮计划中的两个非阻塞后端项：真实 `AgentEventEmitter` 到 FastAPI WebSocket hub 的桥接，以及不进入行情 provider chain 的新闻/公告研究缓存。

- FastAPI `/api/auto-investment` 与 `/api/auto-investment/background` 现在会为每次运行创建 `BackendAgentEventBridge`，把核心 `AgentEvent` 转换为后端 `make_event()` envelope 并广播到现有 WebSocket hub。
- 桥接使用 `loop.call_soon_threadsafe()`，可安全接收 `asyncio.to_thread()` 内部 scheduler/orchestrator 发出的技术面、基本面、舆情、辩论、风控、组合决策和 datasource 事件。
- `TradingTaskScheduler` 接受可选 `event_emitter` 并向 `MultiAgentOrchestrator` 传递；兼容 helper 会在旧测试 double 或旧嵌入方不支持新参数时回退。
- 新增 `data/news_cache.py`，默认写入 Git 忽略的 `data/runtime/news_research_cache.jsonl`，并支持 `ASTOCK_NEWS_CACHE_PATH` 在测试或临时运行中改写路径。
- 新增 `datasource news-collect` / `datasource news-cache`，用于采集和回放 smart-search / iWencai SkillHub 研究行；未配置外部工具时返回结构化 skipped/error，不伪装为行情成功。
- 新增 `/api/datasource/news-cache`，与 CLI 读取同一份脱敏 JSONL，返回 `path`、`summary` 和最近 items。
- 新闻/公告缓存当前只用于研究证据回放和诊断；它不是行情 provider，不触发真实下单，也不构成投资建议。

新增验证命令：

```powershell
python -m pytest tests/test_backend_api.py tests/test_scheduler.py tests/test_data_agent.py tests/test_cli_interactive.py -q
```

当前聚焦结果：`50 passed`。

### 当前增强批次：连续运行看板与后端事件协议复用

本批次补齐长程运行时的“跨轮可观察性”，并把 CLI 已验证的事件名称同步到后端事件协议，避免 GUI/TUI 后续重复定义另一套事件语义：

- `agent start --continuous` 每轮完成后会输出连续运行看板，包含轮次、用时、最近 run id、下一轮计划时间、模型权益/现金、本轮收益、累计收益、PnL、交易数、决策数和当前持仓。
- 新增 `ContinuousRunTracker` 聚合跨轮状态，`_render_continuous_dashboard()` 提供纯文本 fallback，适合测试、复制和日志归档。
- 连续运行看板复用 datasource switch history，展示最近数据源健康状态、来源计数和异常；同时显示 `RunLogRecorder` 捕获的最近错误。
- `RunLogRecorder.write_summary()` 持久化 `continuous_summary`，使 `data/runtime/runs/*.summary.json` 可以回放连续运行关键状态。
- `apps/backend/schemas.py` 的 `EventType` / `EVENT_TYPES` 补齐 `analysis_*`、`data_fetch_*`、`technical_analysis_*`、`fundamental_analysis_*`、`sentiment_analysis_*`、`debate_*`、`risk_analysis_*`、`portfolio_decision_*`、`agent_*`、`run_*`、`llm_*`、`progress_update` 等 CLI 事件名，`/api/health` 可向前端暴露完整事件协议。

新增验证命令：

```powershell
python -m pytest tests/test_cli_observability.py tests/test_backend_api.py -q
```

### 当前增强批次：DataAgent 事件、benchmark 统计与 datasource history 持久化

本批次把原先“运行中可见”的数据源尝试和模型对比统计沉淀为可持久化、可 API 查询、可回放的 CLI 后端能力：

- `DataAgent` 支持绑定 `AgentEventEmitter` 与 `run_id/agent_id/model` 上下文；每次 provider/cache/local/offline attempt 都会发射 `data_source_switched`。
- 新增 `src/astock_agent_system/data/switch_history.py`，默认写入 Git 忽略的 `data/runtime/datasource_switch_history.jsonl`，并对 token/password/api key/access token 等字段脱敏。
- 新增 `datasource history` 命令，可按来源、操作和状态过滤，也可输出 JSON 供脚本和后续 TUI/GUI 复用。
- `/api/datasource/history` 已读取同一份持久化历史，不再只是占位空列表。
- `agent benchmark` / `run_competition` payload 新增 `benchmark_statistics`，包含动作分布、平均置信度、平均仓位、交易效率、LLM review 来源和错误模式；运行 summary 同步保存该统计。

新增验证命令：

```powershell
python -m pytest tests/test_data_agent.py tests/test_orchestrator.py tests/test_backend_api.py -q
python -m astock_agent_system.cli datasource history --format json
```

### 当前增强批次：整合持续学习 / 记忆 / 数据源可观察性

本批次在原 CLI streaming 计划上补齐了 `docs/trellis-plan.md` 中已经落地但此前遗漏的持续学习系统：

- CLI 事件类型新增 `learning_experience_recorded`、`learning_analysis_triggered`、`learning_suggestion_generated`、`memory_case_retrieved`、`data_source_switched`。
- 新增 `src/astock_agent_system/cli_enhanced.py`，提供 Rich 优先、纯文本 fallback 的流式渲染器。
- `python -m astock_agent_system.cli agent start` 支持前台流式运行、数据源快照、学习经验记录摘要和记忆案例检索摘要。
- 新增 `agent status/history/stop/benchmark/learning status|suggestions|trigger/memory` 命令。
- 新增 `datasource status` 命令，展示 provider chain 诊断。
- 新增 `datasource test` 命令，按 provider 逐源核验，不把离线 fallback 误算为该 provider 成功；默认只做 `history` 快速检查，完整检查使用 `--checks history,financial,quote --include-universe`。
- 修复 Tushare `financial` Pandas Series 布尔判断错误、`daily_basic` 查询窗口过宽，以及在线 provider 失败后未知股票离线兜底抛 `KeyError` 的崩溃路径。
- 修复 `decision_made` 事件 payload 与事件 envelope 的 `agent_id` 字段冲突，离线 `agent start` 已能展示决策、交易和收益摘要。
- 后端事件协议新增学习/记忆/数据源事件类型；新增 `/api/datasource/status`、`/api/datasource/history`、`/api/agents/{agent_id}/memory/similar`。

### 当前增强批次：客观数据可观察性与本地行情缓存

本批次开始解决“CLI 只展示内部评分、缺少用户可复核的客观数据”的问题：

- 新增 `src/astock_agent_system/cli_data_viz.py`，提供纯文本/ASCII 形式的 K 线、技术指标、财务指标、公司/报价快照和新闻/舆情摘要渲染函数，后续可被 Rich CLI 或普通终端共同复用。
- `TradeDecision` 新增 `explanation_data` 字段；`PortfolioManager` 会根据技术面、基本面、舆情、辩论和风控结果，为每次决策选择应展示的客观数据块，例如 `kline`、`technical_indicators`、`financial`、`sentiment`、`risk`、`agent_chain`。
- 新增 `src/astock_agent_system/data/cache.py` 的 `MarketDataCache`。缓存目录为 Git 忽略的 `data/market_cache/`，用于减少重复调用 Tushare/Baostock/AkShare 等在线 provider。
- `DataAgent` 已接入文件缓存：内存缓存未命中后优先读取 `data/market_cache/`；在线 provider 成功返回 history/quote/financial 后写入文件缓存。
- CLI 事件枚举新增 `screening_start`、`screening_complete`、`analysis_start`、`analysis_complete`、`data_fetch_start`、`data_fetch_complete`、`agent_chain_step`，并补齐 `technical_analysis_*`、`fundamental_analysis_*`、`sentiment_analysis_*`、`debate_*`、`risk_analysis_*`、`portfolio_decision_*`，用于在命令行显示 `DataAgent -> TechnicalAnalyst -> FundamentalAnalyst -> SentimentAnalyst -> DebateRoom -> RiskManager -> PortfolioManager` 的完整协作链。
- `MasterAgent.analyze_stock` 现在会在每个 Agent 开始/完成时发射结构化事件，`data_fetch_complete` 还会携带本轮 provider/cache 调用链，`portfolio_decision_complete` 会携带 `explanation_data` 和各 Agent 分数。
- `RichEventRenderer` 已直接处理上述细粒度事件：技术面输出指标，基本面输出财务表，舆情输出新闻/摘要，最终决策输出 PortfolioManager 建议展示的证据块、风险提示和 Agent 分数。
- `python -m astock_agent_system.cli` 交互式入口已从平铺长菜单拆成“配置向导 / 数据源诊断 / 运行工作流 / 学习中心”四个二级页面，保留 `0) 快速向导`，让后台-first 验证不再依赖记忆复杂长命令。

缓存 TTL 当前约定：

| 数据类型 | TTL | 说明 |
| --- | --- | --- |
| history | 7 天 | 历史 K 线变化慢，优先减少重复调用 Tushare 历史接口。 |
| quote | 5 分钟 | 保持实时/准实时行情的新鲜度。 |
| financial | 1 天 | 财务和估值数据日内变化较少。 |

注意：本批次已把客观数据渲染、解释计划、文件缓存、`MasterAgent` 细粒度协作事件和 CLI 默认渲染链路打通；新闻/公告 provider、连续运行累计收益/持仓/下一轮时间看板仍需后续任务。

推荐验证命令：

```powershell
python -m astock_agent_system.cli agent learning status --format json
python -m astock_agent_system.cli agent learning suggestions
python -m astock_agent_system.cli agent memory --agent-id agent-rule-baseline --format json
python -m astock_agent_system.cli datasource status --format json
python -m astock_agent_system.cli datasource test --sources tushare,baostock,akshare,ths_skill --stock-code 600519 --days 5 --checks history --format json
python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 120
python -m astock_agent_system.cli agent start --offline --max-count 1 --days 5 --fresh-start --no-persist --no-learning --timeout-seconds 30
```

本地最新 smoke 结论：Tushare history 可用；Baostock 在当前环境缺少 `baostock` 包；AkShare 在当前网络下返回空/远端断连；`ths_skill` 为手工/参考能力，未注册行情 adapter。在线运行应把这些状态显示为可诊断结果，而不是静默声明全部可用。

### Phase 1: 事件系统基础 ✅ (增强完成)

**已完成**：
- ✅ 创建事件定义 (`AgentEvent`, `EventType`)
- ✅ 创建事件发射器 (`AgentEventEmitter`)
- ✅ 创建控制台订阅器 (`ConsoleSubscriber`)
- ✅ 在`MultiAgentOrchestrator`中集成`event_emitter`参数
- ✅ 新增学习、记忆和数据源事件类型
- ✅ 在竞赛运行中发射 run/agent/learning 事件

**本轮补齐**：
- ✅ `MasterAgent` 已发射更细粒度的各 Agent 内部步骤事件：技术分析、基本面分析、舆情分析、多 Agent 辩论、风控评估和组合决策均有 start/complete 事件。
- ✅ `data_fetch_complete` 已携带本轮 `DataAgent` provider/cache 调用链，CLI 可直接展示 history/quote/financial 来自缓存、本地库、在线 provider 还是离线兜底。
- ✅ `portfolio_decision_complete` 已携带 `TradeDecision.explanation_data`、各 Agent 分数和客观数据证据块，便于终端输出解释“为什么买/卖/拒绝”。

**仍待完成**：
- ✅ 数据源真实降级过程的长期持久化事件历史。
- ✅ 连续运行累计收益、持仓变化、下一轮时间和最近错误看板。
- ✅ 后端真实 `AgentEventEmitter` -> WebSocket 桥接。
- ✅ 新闻/公告研究缓存入库与 CLI/API 回放入口。
- ⏳ 是否让 `SentimentAnalyst` 读取持久化 news-cache 作为只读证据，需要用户确认产品边界后再做。

### Phase 2-8: 当前完成度与后续阶段

- **Phase 2: CLI 命令骨架**：已完成 `agent`、`datasource`、`learning`、`memory`、交互式默认入口等核心命令。
- **Phase 3: Rich 流式渲染**：已完成 Rich 优先/纯文本 fallback，并接入客观数据、细粒度 Agent 事件和最终决策证据块。
- **Phase 4-5: 状态查询和 Benchmark**：已完成 `agent status/history/benchmark` 与模型/账户收益摘要。
- **Phase 6-7: 配置共享和 API 化**：已通过运行态配置、FastAPI datasource/agent 接口和 WebSocket 事件协议部分完成。
- **Phase 8: 分支合并到 main**：仍需在 tauri-rewrite 稳定、用户确认后执行。

下一轮优先级建议：

1. 让前端/TUI 消费真实后端 WebSocket 事件和 `/api/datasource/news-cache`，不要重复定义另一套事件协议。
2. 若要让舆情 Agent 自动读取本地 news-cache，先确认它只作为只读研究证据，不替代实时检索和行情 provider。
3. 等 tauri-rewrite 稳定且用户确认后，再执行合并 main 的交付流程。

## 当前代码位置

- **事件系统**：`src/astock_agent_system/events/`
  - `emitter.py` - 事件发射器
  - `subscriber.py` - 事件订阅器
  - `__init__.py` - 模块导出

- **已集成**：`src/astock_agent_system/orchestrator/multi_agent_orchestrator.py`
  - 构造函数接受`event_emitter`参数
  - `run_competition`中发射`agent_start`/`agent_complete`事件

## 下一步建议

现在不需要再创建临时 `cli_streaming.py` 验证入口；主入口已经是：

```powershell
python -m astock_agent_system.cli
```

自动化/排障可继续使用：

```powershell
python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 120
```

只验证终端渲染链路时，可临时使用诊断模式，但不要把它作为在线主验证路径：

```powershell
python -m astock_agent_system.cli agent start --offline --max-count 1 --days 5 --fresh-start --no-persist --no-learning --timeout-seconds 30
```

## 技术要点

### 事件类型

```python
EventType = Literal[
    "run_start", "run_complete", "run_error",
    "stage_start", "stage_complete",
    "screening_start", "screening_complete",
    "analysis_start", "analysis_complete",
    "data_fetch_start", "data_fetch_complete",
    "technical_analysis_start", "technical_analysis_complete",
    "fundamental_analysis_start", "fundamental_analysis_complete",
    "sentiment_analysis_start", "sentiment_analysis_complete",
    "debate_start", "debate_complete",
    "risk_analysis_start", "risk_analysis_complete",
    "portfolio_decision_start", "portfolio_decision_complete",
    "agent_chain_step",
    "agent_start", "agent_step", "agent_complete", "agent_error",
    "decision_made", "trade_executed", "metric_updated",
    "llm_request", "llm_response",
    "data_fetched", "data_source_switched", "progress_update",
    "learning_experience_recorded", "learning_analysis_triggered",
    "learning_suggestion_generated", "memory_case_retrieved",
]
```

### Rich输出设计

- **颜色方案**：成功=绿色，警告=黄色，失败=红色，信息=青色
- **动画元素**：旋转图标（⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏）、动态计时、进度条
- **层级结构**：阶段标题（大号粗体）→ Agent名称（中号粗体）→ 详细信息（普通缩进）

### 与现有代码集成

- 复用`MultiAgentOrchestrator`、`MasterAgent`、`VirtualAccount`
- 事件发射不影响现有功能（可选参数，默认空发射器）
- CLI和TUI共享配置文件 (`data/runtime/settings.override.json`)

## 分支合并计划

完成CLI开发后，将tauri-rewrite合并到main：

1. 运行完整验证：`.\start.bat -Mode delivery-check`
2. 更新所有相关文档
3. 合并：`git checkout main && git merge tauri-rewrite`
4. 推送：`git push origin main`
5. 更新Trellis handoff文档

## 参考资料

- Rich文档：https://rich.readthedocs.io/
- 现有TUI实现：`apps/tui/`
- 后端API契约：`apps/backend/app.py`
- 配置系统：`src/astock_agent_system/config.py`

## 状态总结

- **当前分支**：`tauri-rewrite`
- **Phase 1进度**：事件系统、客观数据渲染、解释计划、文件缓存、细粒度 Agent 协作事件已打通。
- **下一优先级**：前端/TUI 消费真实事件流、news-cache 只读证据边界确认、tauri-rewrite 合并前验证。
- **预计工作量**：前端/TUI 消费事件流约 4-8 小时；news-cache 接入舆情只读证据约 4-8 小时；合并 main 前验证与文档收口约 2-4 小时。
