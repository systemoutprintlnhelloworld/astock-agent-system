# Data Observability Handoff

更新时间：2026-06-11

## 背景

本轮开发继续推进 CLI-first 的 A 股智能体运行链路，重点不是 TUI/GUI，而是先让 Python 命令行能够清楚展示“为什么买、为什么不买、数据从哪里来、哪个 Agent 做了什么”。

用户反馈的关键问题包括：

- 只看到 `000001 BUY` 这类结论，缺少公司名称、行情、K 线、财务和舆情证据。
- 当前运行容易“一次决策就结束”，后续需要支持持续运行直到手动停止。
- 数据源不可观察，无法区分 Tushare/JQData/Baostock/AkShare/iFinD 是缺凭证、缺依赖、接口失败，还是命中了缓存/离线兜底。
- `docs/technical/ARCHITECTURE.md` 中定义的多 Agent 协作链路需要在 CLI 事件流中显性体现。

## 本轮代码行为变化

### 1. Agent 协作链路可观察性

`MasterAgent` 已开始向事件总线发射更细粒度事件：

- `screening_start` / `screening_complete`
- `analysis_start` / `analysis_complete`
- `data_fetch_start` / `data_fetch_complete`
- `agent_chain_step`
- `decision_made` / `trade_executed`

这些事件携带结构化 payload，用于展示：

- 股票代码、股票名称和板块；
- 报价、K 线、财务快照；
- 技术分析、基本面分析、舆情分析、辩论、风控、组合经理决策；
- 最终交易动作和虚拟账户变化。

### 2. CLI 渲染增强

`cli_enhanced.py` 接入 `cli_data_viz.py` 中的文本/ASCII 渲染能力，目标是在终端中直接看到客观数据，而不是只看到评分。

计划展示块包括：

- 公司/报价摘要；
- 近端 K 线 ASCII 图；
- 技术指标摘要；
- 财务指标表；
- 舆情/新闻摘要；
- Agent 链路评分与理由；
- 排名、收益和交易摘要。

### 3. 数据源配置与诊断

数据源 catalog 继续区分：

- 是否已配置到 provider chain；
- 是否需要凭证；
- 本地是否已有凭证；
- 依赖包是否安装；
- adapter 是否存在；
- capability 是否覆盖 `universe/history/financial/quote`。

本轮增加 iFinD / 同花顺 QuantAPI HTTP provider 的配置入口和 provider 注册。真实 token 只允许来自本地环境变量或 `data/runtime/settings.override.json`，不提交到仓库。

### 4. 本地资料处理

`docs/misc/*.pdf` 仅作为本地参考资料，不纳入 Git 提交。`.gitignore` 已忽略该路径下 PDF，避免把第三方手册或可能含账号信息的文件提交。

## 重要边界

- Tushare token、JQData 账号、iFinD token 等凭证必须只保存在本地 `.env` 或 `data/runtime/settings.override.json`。
- 当前系统仍是模拟盘/纸面交易，不允许静默接入真实下单。
- 数据源 smoke 不能把缓存或离线兜底误报为 provider 成功；应明确输出 `ok/error/skipped` 和原因。
- Tushare MCP 可作为后续研究方向，但当前代码主链仍以本地 provider adapter 和缓存为准。

## 推荐验证命令

```powershell
python -m py_compile src/astock_agent_system/agents/master_agent.py src/astock_agent_system/cli.py src/astock_agent_system/cli_enhanced.py src/astock_agent_system/config.py src/astock_agent_system/data/data_agent.py src/astock_agent_system/data/providers/__init__.py src/astock_agent_system/data/providers/ifind_provider.py src/astock_agent_system/orchestrator/multi_agent_orchestrator.py

python -m astock_agent_system.cli config
python -m astock_agent_system.cli datasource status --format json
python -m astock_agent_system.cli datasource test --sources baostock,akshare,jqdata,ifind --stock-code 600519 --days 5 --checks history --format json
python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --no-learning --timeout-seconds 180

.\start.bat -Mode delivery-check
```

## 后续开发建议

1. 将 `agent start --continuous` 的长程运行补齐为真正的循环看板：每轮记录开始/结束、等待时间、累计收益、当前持仓、下一次运行时间。
2. 将 Tushare “撸数据”路线拆成独立任务：批量同步股票基础信息、日线、每日指标、财务指标到本地 SQLite/Parquet，再由 `DataAgent` 优先读本地库。
3. 将新闻/舆情数据源显式分层：行情 provider 不负责新闻，舆情 provider 单独接入 AkShare/Tushare 新闻、公告或 smart-search 摘要。
4. 将 MCP/Tushare MCP 作为研究与辅助查询入口，先做只读 POC，确认接口能力、限频和数据结构后再进入主 provider chain。
