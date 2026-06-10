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
- CLI 事件枚举新增 `screening_start`、`screening_complete`、`analysis_start`、`analysis_complete`、`data_fetch_start`、`data_fetch_complete`、`agent_chain_step`，用于后续在命令行显示 `DataAgent -> TechnicalAnalyst -> FundamentalAnalyst -> SentimentAnalyst -> DebateRoom -> RiskManager -> PortfolioManager` 的完整协作链。

缓存 TTL 当前约定：

| 数据类型 | TTL | 说明 |
| --- | --- | --- |
| history | 7 天 | 历史 K 线变化慢，优先减少重复调用 Tushare 历史接口。 |
| quote | 5 分钟 | 保持实时/准实时行情的新鲜度。 |
| financial | 1 天 | 财务和估值数据日内变化较少。 |

注意：本批次只是把客观数据渲染、解释计划和文件缓存基础打通；细粒度事件在 `MasterAgent`/`MultiAgentOrchestrator` 中的完整渲染和持续运行模式仍需继续完成后续任务。

推荐验证命令：

```powershell
python -m astock_agent_system.cli agent learning status --format json
python -m astock_agent_system.cli agent learning suggestions
python -m astock_agent_system.cli agent memory --agent-id agent-rule-baseline --format json
python -m astock_agent_system.cli datasource status --format json
python -m astock_agent_system.cli datasource test --sources tushare,baostock,akshare,ths_skill --stock-code 600519 --days 5 --checks history --format json
python -m astock_agent_system.cli agent start --model rule-baseline --offline --max-count 1 --days 12 --fresh-start --no-persist --no-learning
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

**待完成**：
- ⏳ 更细粒度的各 Agent 内部步骤事件（筛选、技术分析、基本面、舆情、风控）
- ⏳ 数据源真实降级过程的持久化事件历史

### Phase 2-8: 后续阶段

由于当前对话即将结束，建议下一位AI接手时按以下优先级继续：

1. **Phase 2: CLI命令骨架** - 扩展`cli.py`，添加`agent`子命令组
2. **Phase 3: Rich流式渲染** - 用Rich美化输出，支持颜色、动画、进度条
3. **Phase 4-5: 状态查询和Benchmark**
4. **Phase 6-7: 配置共享和API化**
5. **Phase 8: 分支合并到main**

## 当前代码位置

- **事件系统**：`src/astock_agent_system/events/`
  - `emitter.py` - 事件发射器
  - `subscriber.py` - 事件订阅器
  - `__init__.py` - 模块导出

- **已集成**：`src/astock_agent_system/orchestrator/multi_agent_orchestrator.py`
  - 构造函数接受`event_emitter`参数
  - `run_competition`中发射`agent_start`/`agent_complete`事件

## 下一步建议

由于开发过程发现完整实现需要较多工作量，建议采用**渐进式策略**：

### 选项A：继续完整实现（推荐用于充足时间）

按Phase 1-8完整实施，最终得到功能完整的CLI工具和API。

### 选项B：MVP快速验证（推荐用于快速测试）

简化方案，快速验证核心思路：

1. 创建最小CLI命令：
   ```python
   # src/astock_agent_system/cli_streaming.py
   def cmd_agent_start_simple():
       emitter = AgentEventEmitter()
       emitter.subscribe(ConsoleSubscriber(verbose=True))
       orchestrator = MultiAgentOrchestrator(event_emitter=emitter)
       orchestrator.run_competition(models=["rule-baseline"], max_count=1)
   ```

2. 运行验证：
   ```bash
   python -m astock_agent_system.cli_streaming
   ```

3. 看到事件流输出后，再决定是否继续完整实现

## 技术要点

### 事件类型

```python
EventType = Literal[
    "run_start", "run_complete", "run_error",
    "stage_start", "stage_complete",
    "agent_start", "agent_step", "agent_complete", "agent_error",
    "decision_made", "trade_executed", "metric_updated",
    "llm_request", "llm_response",
    "data_fetched", "progress_update",
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
- **Phase 1进度**：事件系统基础框架完成，待集成到更多执行点
- **下一优先级**：创建MVP验证或继续Phase 2 CLI命令骨架
- **预计工作量**：完整实现约20-24小时，MVP验证约2-4小时
