# Phase 1 - Implement：当前实现状态与下一步执行计划

更新时间：2026-06-11

本文档把当前实现状态、验证命令、下一步可执行任务写成持久化 handoff 计划。新对话应先读本文件，再继续编码。

## 最新交付记录：后端真实事件桥接与新闻/公告研究缓存（2026-07-03）

本轮继续按“Python CLI 后端优先”路线推进已知计划中的非阻塞项：把 FastAPI 自动投资端点从模拟流程事件扩展为真实 `AgentEventEmitter` 桥接，同时落地不依赖凭证的新闻/公告研究缓存入口，明确它只做研究证据回放，不进入行情 provider chain，也不会触发真实下单。

已落地：

- FastAPI 新增 `BackendAgentEventBridge`：为每次 `/api/auto-investment` 与 `/api/auto-investment/background` 创建独立 `AgentEventEmitter`，把核心 `AgentEvent` 转换为后端 `make_event()` envelope 后广播到现有 WebSocket hub。
- 事件桥接使用 `loop.call_soon_threadsafe()` 调度广播，可安全接收 `asyncio.to_thread()` 中 `TradingTaskScheduler` / `MultiAgentOrchestrator` 发出的技术面、基本面、舆情、辩论、风控、组合决策和 datasource 事件。
- `TradingTaskScheduler` 支持可选 `event_emitter`，并通过兼容 helper 构造 orchestrator；旧测试 double 或外部嵌入方未接受 `event_emitter` 时仍可回退。
- 新增 `src/astock_agent_system/data/news_cache.py`，默认写入 Git 忽略的 `data/runtime/news_research_cache.jsonl`，支持 `ASTOCK_NEWS_CACHE_PATH` 临时改写、递归脱敏 token/password/api key/authorization 等字段，并提供加载与 summary 统计。
- 新增 CLI：`datasource news-collect` 可把 smart-search / iWencai SkillHub 结果写入研究缓存；`datasource news-cache` 可按 source、stock_code、status 查看缓存。无 smart-search 或 iWencai 凭证时返回结构化 skipped/error，不伪装为行情数据。
- 新增 FastAPI：`/api/datasource/news-cache` 读取同一份研究缓存，返回 `path`、`summary` 和最近 items，供后续 TUI/GUI 或回放工具使用。
- 新增聚焦测试覆盖后端桥接广播、scheduler 兼容构造、news-cache 脱敏/统计、news-cache API 和 CLI parser wiring。

验证：

```powershell
python -m pytest tests/test_backend_api.py tests/test_scheduler.py tests/test_data_agent.py tests/test_cli_interactive.py -q
```

当前聚焦结果：`50 passed`。

下一步：

1. 本轮已运行 `.\start.bat -Mode delivery-check` 并通过；收尾继续 commit / push。
2. 后续若继续产品化，可让前端/TUI 消费真实 WebSocket 事件和 `/api/datasource/news-cache`，但不需要再重复定义事件协议。
3. 是否让 `SentimentAnalyst` 读取持久化 news-cache 作为只读证据，需要用户确认产品边界后再做；当前缓存只用于研究回放和诊断。
4. 合并 `tauri-rewrite` 到 main 仍需用户明确确认。

## 最新交付记录：连续运行看板与 CLI 事件协议复用（2026-07-03）

本轮继续按“Python CLI 后端优先”的路线推进长程模拟盘可观察性，补齐连续运行时单轮摘要之外的累计状态，并把 CLI 已验证的细粒度事件名同步给后端 WebSocket schema，方便后续 TUI/GUI 直接复用同一事件协议。

已落地：

- `agent start --continuous` 新增连续运行看板：每轮结束后展示轮次、启动时间、用时、下一轮计划时间、最近 run id 和运行日期。
- 新增 `ContinuousRunTracker` 与 `_render_continuous_dashboard()`，聚合多轮模型权益/现金、本轮收益、累计收益、PnL、交易数、决策数和当前持仓；纯文本 fallback 可测试、可复制。
- 连续运行看板接入 `datasource_switch_history.jsonl`，展示最近数据源健康状态、来源计数和最近异常；长程运行不再只看单轮账户表。
- 看板同步展示 `RunLogRecorder` 收集的最近错误，`write_summary()` 会把 `continuous_summary` 写入运行 summary，便于事后审计。
- `apps/backend/schemas.py` 的 `EventType` / `EVENT_TYPES` 补齐 CLI 细粒度事件名（analysis/data_fetch/technical/fundamental/sentiment/debate/risk/portfolio/agent/run 等），`/api/health` 现在会暴露这些事件类型，前端/WebSocket 可以按 CLI 同名事件消费。
- 新增聚焦测试覆盖连续运行看板的累计收益、持仓、最近错误和后端事件类型暴露。

验证：

```powershell
python -m pytest tests/test_cli_observability.py tests/test_backend_api.py -q
```

下一步：

1. 继续把后端实际 auto-investment 后台运行的事件广播从模拟 flow 扩展为真实 `AgentEventEmitter` 桥接，但需保持 API 线程安全与不阻塞 HTTP 响应。
2. 接入新闻/公告 provider 与缓存/本地库，补齐舆情客观数据来源。
3. 在用户确认后再推进 `tauri-rewrite` 到 main 的合并流程。

## 最新交付记录：DataAgent 事件、benchmark 统计与 datasource history 持久化（2026-07-03）

本轮继续按用户要求暂停 GUI/TUI 扩展，优先推进 Python CLI 后端逻辑，把数据源切换、Agent 细粒度事件和 benchmark 结果从“运行时可见”推进到“可持久化、可 API 查询、可回放审计”。

已落地：

- `DataAgent` 支持绑定 `AgentEventEmitter` 与 `run_id/agent_id/model` 上下文；每次 provider/cache/local/offline attempt 都会发射 `data_source_switched` 事件，前台运行可以看到具体来源、操作、状态和简短详情。
- 新增 `src/astock_agent_system/data/switch_history.py`，把数据源 attempt 追加到 Git 忽略的 `data/runtime/datasource_switch_history.jsonl`；写入前会脱敏 token/password/api key 等字段，测试可通过 `ASTOCK_DATASOURCE_HISTORY_PATH` 指向临时文件。
- 新增 CLI 命令 `python -m astock_agent_system.cli datasource history`，支持 `--limit`、`--source`、`--operation`、`--status` 和 `--format json`，用于排查一轮运行中 Tushare/Baostock/AkShare/JQData/iFinD/local/offline 的真实切换轨迹。
- `/api/datasource/history` 不再返回空占位，而是读取持久化 JSONL 并返回 `path`、`summary` 和最近 items，供 TUI/GUI 后续复用 CLI 已验证的 datasource 可观察性。
- `MultiAgentOrchestrator.run_competition()` 返回 `benchmark_statistics`：按模型统计决策数、动作分布、平均置信度、平均仓位、交易效率、LLM review 来源和错误模式；`RunLogRecorder.write_summary()` 同步写入该统计，避免只看收益排行。
- `MasterAgent` 初始化会把事件总线和 run context 传给共享 `DataAgent`，使多模型独立账户运行中的 datasource 事件能归属到对应 Agent/model。
- 新增/更新聚焦测试覆盖 DataAgent datasource history 持久化与事件发射、backend history API 脱敏读取、benchmark statistics payload 和 CLI parser wiring。

验证建议：

```powershell
python -m py_compile src/astock_agent_system/data/switch_history.py src/astock_agent_system/data/data_agent.py src/astock_agent_system/agents/master_agent.py src/astock_agent_system/orchestrator/multi_agent_orchestrator.py src/astock_agent_system/cli_enhanced.py src/astock_agent_system/cli.py apps/backend/app.py
python -m pytest tests/test_data_agent.py tests/test_orchestrator.py tests/test_backend_api.py -q
python -m astock_agent_system.cli datasource history --format json
.\start.bat -Mode delivery-check
```

下一步：

1. 将 `data_source_switched` 和 datasource history summary 进一步接入前端/TUI 事件面板，但仍以 Python CLI 验证为主。
2. 对连续运行模式补累计收益、下一轮时间、最近错误和 datasource 健康摘要，避免长程运行只看单轮结果。
3. 继续推进新闻/公告 provider 与本地库入库，但不得把研究信源接入误报为行情 provider 或真实下单能力。

## 最新交付记录：本地主动扫描、运行日志元信息与 smart-search/local-status 可观察性（2026-06-13）

本轮继续按用户要求暂停 GUI/TUI 扩展，优先把 Python CLI 后端链路做成可诊断、可解释、可交接的工作流。重点修复真实运行中暴露的 `smart-search` Windows shim/PATH 问题，把 iWencai 与本地市场 SQLite 库状态纳入交互式数据源页面，并新增本地市场主动扫描入口与运行日志账户元信息，解决“几千只股票逐股分析太慢”和“当前运行/历史摘要/新账户/恢复账户不清楚”的问题。

已落地：

- 新增 `src/astock_agent_system/smart_search.py`，统一解析并调用本机 `smart-search` CLI。Windows/npm 安装出的 `smart-search.CMD` 会先通过 `shutil.which` 解析为真实路径，再传给 `subprocess.run`，避免长程 Agent 进程内出现 `[WinError 2]`。
- `SentimentAnalyst` 改为复用 smart-search helper；调用失败时仍明确标记 `smart-search-error`、保留中性临时舆情，并把风险提示交给前台，而不是静默伪装为成功。
- 新增 `datasource smart-search-status`，输出 doctor 摘要、CLI 解析路径、已配置检索通道与 next steps；JSON 输出会先递归脱敏，避免把 doctor 返回的本地 key 状态写入用户可分享日志。
- 交互式“数据源配置与诊断”页面补齐 iWencai 状态、配置、公告检索和 smart-search 自检入口，用户无需记忆长命令即可排查 SkillHub/smart-search 状态。
- `LocalMarketStore.coverage_summary()` 新增本地 SQLite 市场库覆盖统计，包括股票/K线/行情/财务覆盖率、日期范围、最近交易日覆盖热力图、样本股票覆盖和行业/分组覆盖。
- `datasource local-status` 的 CLI 渲染增强为本地市场库可观察性页，除库存和最近同步记录外直接展示覆盖率、日期热力图、样本股票覆盖和 sector/group 分布，便于判断本地库是否足够支撑多股票/板块研究。
- `LocalMarketStore.scan_candidates()` 新增只读本地广域扫描：直接使用 SQLite 中的 `stocks/quotes/bars/financials`，按行业、成交额、成交量、涨跌幅、5/20 日收益、量能/额比和财务质量生成候选短名单。
- 新增 CLI 命令 `datasource active-scan`，并接入交互式“本地数据同步”页面。该入口不访问在线 provider、不调用 LLM、不写库、不下单，也不输出买卖建议；它只是把本地库里的几千只股票压缩成几十只候选，供 `analyze` 或 `agent start` 深度分析。
- `MultiAgentOrchestrator.run_competition()` 的 payload 新增 `run_id`、`account_mode`、`fresh_start`、`continue_from_storage`、`snapshot_restore`、`restored_account_count` 和 `skipped_agent_count`，使 CLI/日志能明确说明是否新账户、是否恢复存储、是否同日幂等跳过。
- `RunLogRecorder.write_summary()` 同步写入上述运行/账户元信息和 `summary_path`，运行日志页可据此区分当前运行与历史 summary。
- 新增/更新聚焦测试覆盖 smart-search 状态渲染、local-status 覆盖率渲染、`LocalMarketStore.coverage_summary()`、`LocalMarketStore.scan_candidates()`、`datasource active-scan` CLI JSON/parser，以及运行 payload/summary 的账户元信息。

验证：

```powershell
python -m pytest tests/test_cli_observability.py tests/test_data_agent.py tests/test_orchestrator.py -q
```

下一步：

1. 在用户本机继续运行 `datasource smart-search-status` 与 `agent start`，确认 `SentimentAnalyst` 不再出现 `[WinError 2]`。
2. 若用户需要更强的底部固定状态栏，再把当前终端安全的状态栏升级为 Rich Live footer，并保持纯文本 fallback 可测试、可复制。
3. 继续推进本地市场库 freshness/增量窗口、公告/新闻入库和更完整的板块级主动研究；不要把当前 `active-scan` 误报为完整自动交易策略或买卖建议。

## 上一交付记录：iFinD/iWencai、状态栏与多 Agent 协作可见性（2026-06-12）

本轮继续按 CLI-first 后端交付路线推进，重点修复用户反馈的 iFinD 不可用、iWencai 未配置、运行状态不可见、Mongo 错误冗长、多 Agent 辩论不像协作、股票池筛选过早停止等问题。

已落地：

- iFinD provider 对齐同花顺 QuantAPI HTTP 文档：历史行情走 `cmd_history_quotation`，实时报价走 `real_time_quotation`，默认 base URL 为 `https://quantapi.51ifind.com/api/v1`，并保留 refresh token 重试和多形态响应解析；历史行情会按官方后缀、原始代码、`SH/SZ` 前缀等候选格式重试，并在扩展指标不可用时回退到 OHLC 最小指标集。
- iWencai SkillHub 配置进入 `DataSettings`、runtime override 和 CLI：`datasource iwencai-status` 显示脱敏状态，`datasource configure-iwencai` 用隐藏输入把 API key 保存到 Git 忽略的 `data/runtime/settings.override.json`。
- 新增 `IwencaiSkillHub` 公告/研究信源 adapter 和 `datasource iwencai-search`：当本机 CLI/API key/`announcement-search` 技能可用时尝试公告搜索；缺失时返回结构化 `skipped/error`、脱敏 attempts 和 next steps，不进入行情 provider chain，也不伪装为行情成功。官方安装器实际生成 `iwencai-skillhub-cli`，代码会优先识别该命令，并在 Windows 仅 WSL 安装时通过 `skillhub_bridge=wsl` 标明桥接；外部 CLI/WSL 探测统一使用容错解码，避免安装器乱码输出触发 `UnicodeDecodeError` 或污染诊断；WSL 桥接执行时通过 `WSLENV` 传递 iWencai 环境变量，且会兜底检查 `$HOME/.local/bin/iwencai-skillhub-cli`，避免 shell profile 尚未生效导致误判未安装；若本机只有 install-only 商店 CLI，状态页会显示 `direct_run_supported=false`，`iwencai-search` 返回 `manual_screener_url` 指向 `https://www.iwencai.com/screener?query=...`，作为人工公告/问财信源入口。
- 交互式数据源菜单增加 iWencai 配置/状态入口；`config` 输出只展示 `has_iwencai_api_key`。
- `agent start` 事件流新增 `RuntimeStatusRenderer`，以 `状态栏 | 模型=... | 阶段=... | 股票=... | 决策=... | 成交=... | 收益=... | 用时=...` 方式持续给出前台运行状态。
- MongoDB 持久化失败改为 `_compact_persist_error()`，输出 `E-MONGO-CONNECT` 短提示，避免 `ServerSelectionTimeout` 长异常影响 CLI 体验。
- `DebateRoom` 改为显式记录 `agent_inputs`、`discussion_rounds`、`bull_points`、`bear_points` 和 `judge`，体现技术/基本面/舆情 Agent 的证据被收集并由评委综合。
- CLI 渲染器现在会在辩论阶段/分析总览中展开 `agent_inputs`、`discussion_rounds` 和评委结论，让多 Agent 协作不是隐藏在 JSON metadata 中。
- `StockScreener` 在线模式不再凑够 `max_count` 就停止，而是在 scan limit 内广搜后排序，减少候选池任意性。

验证：

```powershell
python -m py_compile src/astock_agent_system/config.py src/astock_agent_system/cli.py src/astock_agent_system/cli_enhanced.py src/astock_agent_system/agents/debate_room.py src/astock_agent_system/orchestrator/multi_agent_orchestrator.py src/astock_agent_system/data/providers/ifind_provider.py
python -m pytest tests/test_ifind_provider.py tests/test_config.py tests/test_cli_interactive.py tests/test_cli_observability.py -q
python -m astock_agent_system.cli datasource iwencai-search --stock-code 600519 --query "公告" --format json
```

下一步：

1. 用用户本地真实 iFinD token 做 `datasource test --sources ifind --checks history,quote`，仅输出脱敏诊断。
2. 若本机可安全安装 SkillHub，再按官方脚本安装 CLI，并执行 `iwencai-skillhub-cli install announcement-search`；项目本地技能目录可用 `iwencai-skillhub-cli --dir data/runtime/skillhub/skills install announcement-search --force`。若 WSL/网络不可用，则保持 CLI 诊断和本地 key 持久化。
3. 继续把状态栏升级为真正 Rich Live 底部区域，同时保持当前纯文本模式可测试、可复制。

## 最新交付记录：TUI UX / 运行可观察性

### CLI streaming + 持续学习可观察性增强

- `src/astock_agent_system/events/emitter.py` 新增学习、记忆和数据源事件类型：`learning_experience_recorded`、`learning_analysis_triggered`、`learning_suggestion_generated`、`memory_case_retrieved`、`data_source_switched`。
- 新增 `src/astock_agent_system/cli_enhanced.py`，提供 Rich 优先、纯文本 fallback 的流式运行渲染、学习状态/建议、记忆案例和数据源诊断展示。
- `src/astock_agent_system/cli.py` 新增 `agent start/status/history/stop/benchmark/learning status|suggestions|trigger/memory` 与 `datasource status/test` 命令。
- `python -m astock_agent_system.cli` 无子命令时不再只打印帮助，而是进入 `AStock 交互式工作流控制台`；顶层菜单拆成“配置向导 / 数据源诊断 / 运行工作流 / 学习中心”四个二级页面，保留 `0) 快速向导`，默认沿用本地 `llm.default_model`，不强制 `rule-baseline` 或 `offline`。
- `src/astock_agent_system/orchestrator/multi_agent_orchestrator.py` 在竞赛运行中发射 run/agent/learning 事件，并把学习经验记录/建议生成反馈给 CLI。
- `apps/backend/schemas.py` 扩展 WebSocket 事件枚举，`apps/backend/app.py` 新增 `/api/datasource/status`、`/api/datasource/history`、`/api/agents/{agent_id}/memory/similar`，便于后续 GUI/TUI 复用 CLI 先验证出的可观察内容。
- 本轮修复在线 provider 失败路径：Tushare `financial` 不再触发 Pandas Series 布尔判断错误，`daily_basic` 限定查询窗口；在线数据源失败后未知股票离线兜底不再抛 `KeyError`；筛选器会跳过空行情/零价格，避免第三方限频或断连导致 CLI 崩溃。
- `datasource test` 是逐源 smoke：默认只跑快速 `history`，避免 AkShare/Tushare 全市场接口长时间卡住；支持 `--timeout-seconds` 对每个 provider/check 设置硬超时，逐源结果不会把离线 fallback 误计为 provider 成功。
- 本轮继续修复 CLI 卡住和在线链路：`DataAgent` 对在线 provider 的 `universe/history/financial/quote` 调用增加 `DATA_PROVIDER_TIMEOUT_SECONDS` 硬超时和本轮 cooldown；`agent start` 增加 `--timeout-seconds` 总超时，超时返回 124 而不是持续监听；Baostock 登录 stdout 已被捕获，避免 `login success!` 污染 JSON 输出。
- 本轮继续排查“所有数据源都有问题”的在线诊断：Baostock 股票池会返回指数/非正常行，现已按 `type/status` 和交易所前缀过滤，避免 `sh.000003` 被归一化为无效 A 股 `000003` 后拖垮后续筛选；Tushare 频率超限、AkShare 远端断连/超时会触发本轮 source cooldown，避免一轮运行里重复打同一坏源；`datasource status` 增加 `dependency_module/dependency_installed`，区分缺依赖、缺凭证和公网源空返回。
- 已把 `yfinance`、`jqdatasdk`、`adata` 纳入 `.[market]`/`.[all]` 可选依赖；JQData 已声明 `financial` 保守占位能力，并新增 `datasource configure-jqdata`，通过隐藏输入把本地凭证写入 Git 忽略的 `data/runtime/settings.override.json`，不在命令、文档或提交中回显真实账号密码。
- 本轮主验证路径已改为本地默认模型在线运行，不再以 `--model rule-baseline` 或 `--offline` 作为通过标准：`python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 60` 已使用本地 `gpt-5.5` 配置跑通，输出决策、学习记录、收益摘要并正常退出。
- 本轮继续审计用户提出的“可观察性计划是否完成”：基础事件、缓存和数据源诊断已落地，但原先默认输出仍偏评分/结论；现在 `analysis_complete` 会默认输出公司/行情、K线 ASCII 图、技术指标、财务估值、舆情摘要、Agent 协作链和最终决策，`agent_chain_step` 也默认显示相关客观数据，不再只在 `--verbose` 下展示关键 K线。
- 本轮 iFinD / 同花顺接入采用安全方式：`configure-ifind` 使用隐藏输入写入 Git 忽略的运行态配置；真实 access token / refresh token 不得写入命令、文档、提交或日志。官方资料显示 iFinD 同时有 SDK 函数（`THS_BD`/`THS_DS`/`THS_DR`/`THS_RQ`）与 HTTP 路线，当前代码优先走 HTTP provider 骨架，字段权限不足时降级到下一 provider。
- 本轮新增 SQLite 本地市场数据仓库 `src/astock_agent_system/data/local_store.py`，默认写入 Git 忽略的 `data/market_local/market.sqlite`；新增 `datasource sync-local` 命令，可把真实 provider-chain 成功返回的股票池、K 线、报价和财务快照批量写入本地库；`DataAgent` 在线模式读取顺序升级为进程内缓存 -> SQLite 本地库 -> TTL 文件缓存 -> provider chain -> 离线样例兜底。
- 本轮继续修复交互式 CLI UX：LLM 模型列表现在可输入编号选择，Provider profile / 同步模式 / provider 策略也使用编号选择；“本地数据同步”二级页的第二项改为 `datasource local-status`，直接展示 SQLite 库存量、最近同步时间和最近同步记录，不再误导为 generic 数据源状态。
- 本轮继续补强运行看板：`agent start` 的运行完成摘要新增账户看板、当前持仓、最近交易、买/卖次数和本轮 PnL；连续运行默认交互间隔改为 15 分钟且会先立即执行第 1 轮，轮间等待改为倒计时提示，避免用户误以为长时间未启动。
- 本轮继续修复 smart-search 与 iFinD 边界：`smart_search.enabled` 默认改为 true，`.env.example` 也默认启用；smart-search 调用失败时返回 `smart-search-error` 风险说明而不是“未启用”；iFinD 增加 `IFIND_BASE_URL`、常见 A 股代码格式归一化、矩阵成功准入和矩阵失败中文诊断。iWencai SkillHub 记录为研究/公告技能边界，不进入行情 provider chain，也不写入真实 key。
- 已验证 `tests/test_data_agent.py` 18 passed；新增覆盖 `LocalMarketStore` roundtrip、`DataAgent` 本地优先读取、`datasource sync-local` 写库命令。Baostock `history/quote/financial` 对 `600519` 通过；yfinance `history/quote` 对 `600519` 通过且 `financial` 明确 skipped；JQData 未配置本地凭证时明确 skipped/missing credentials；AData 2.9.5 已安装但当前公开接口对 `600519` 返回空表，保留为手动参考源；AkShare 当前网络下仍可能 remote disconnect/timeout，但会按诊断返回并 cooldown，不再阻塞。

### 本轮新增的可复现实测

- `python -m astock_agent_system.cli datasource test --sources baostock --stock-code 600519 --days 5 --checks universe,history,quote,financial --timeout-seconds 12 --format json`：4 checks passed。
- `python -m astock_agent_system.cli datasource test --sources yfinance --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json`：history/quote passed，financial skipped。
- `python -m astock_agent_system.cli datasource test --sources jqdata --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json`：未配置凭证时 skipped/missing credentials。
- `python -m astock_agent_system.cli datasource test --sources akshare --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json`：当前网络下 history 断连后整源进入 source cooldown，quote/financial 跳过，不再重复打同一坏源。
- 下一步应继续把 `MasterAgent`、各分析 Agent 和 `DataAgent` 内部步骤做成更细粒度事件，并把前台 CLI 运行事件复用到后端 API/WebSocket。
- 仍未完成且不要误报为已完成：SQLite “撸数据”目前是首版批量同步和本地优先读取，尚未完成增量日期窗口、Parquet 导出、新闻/公告入库和 freshness 策略；真实 7 日后 outcome 回填、低质量学习样本过滤、连续运行累计收益/持仓/下一轮时间看板仍需后续任务。

- `apps/tui/config_wizard.py` 的初始化向导改为更接近 coding-agent TUI 的交互：数据模式单选、provider chain checkbox 多选、默认 LLM 模型从后端模型列表 fuzzy 选择；比赛模型移出初始化配置，改为运行前通过 `/models select`、`/models set` 或 `/start --models` 选择。
- 配置向导现在会先读取 `/api/config` 的脱敏当前配置并动态展示：非密钥字段回填已保存值，密钥字段只显示“已配置/未配置”；已配置密钥留空会保留旧值，且只对 provider chain 中被选中的数据源继续询问对应凭证。
- `src/astock_agent_system/config.py` 修复运行态配置优先级：真实进程环境变量仍最高，但 `data/runtime/settings.override.json` 会优先于本地 `.env` 中的旧同名字段，避免向导保存后的 `provider_chain`、默认模型、候选数量和历史窗口看起来未生效。
- `apps/tui/prompt.py` 的 slash command palette 在输入 `/` 时直接展示候选命令和说明，并支持 `/dashboard`、`/models`、`/start` 等二级命令/参数以及后端模型名补全。
- `/agent` 命令补全与实际处理器对齐，支持 `list/view/edit/backup/learning stats|suggestions|trigger` 以及 `stats/suggestions/trigger` 短别名。
- `apps/tui/app.py`、`apps/tui/commands/slash.py` 和 `apps/tui/widgets/dashboard.py` 已把 `/dashboard` 默认改为交易看板；新增 `/run` 与 `/dashboard run`；`/start` 提交后台任务后立即显示 run_id、运行状态、排行榜、持仓/交易和决策日志聚合视图。
- TUI 每次关键命令后清屏重绘 20/80 主布局，并在输入区附近显示状态栏，减少旧配置摘要和旧命令输出堆叠。TUI 仍只调用 `apps/backend` FastAPI 契约，不复制交易业务逻辑。
- 本轮脱敏真实链路验证已覆盖 `/help`、`/status`、`/models list/set/selected`、`/workflow offline`、`/providers`、`/config show`、`/config test-llm`、`/dashboard` 系列、`/start --offline --max-count 1 --days 12`、`/run`、`/agent list/stats`、`/compact`、`/permission`、`/sandbox`、`/theme`、`/lang`、`/attachments`、`/history` 和 `/memory`。
- 本轮参考 `earendil-works/pi` 和 `claude-code-best/claude-code` 的命令发现、长期会话和 TUI 运行体验，落地文档见 `docs/tui/TUI_UX_REDESIGN_PLAN.md`。

上一条交付记录：GUI 连接可诊断性

- `apps/frontend/src/lib/dashboard-api.ts` 现在会保留后端发现诊断快照：配置 URL、已解析 URL、当前候选 URL、最近成功候选、最近错误、候选探测结果、探测次数和下一步建议。
- `apps/frontend/src/components/trading-dashboard.tsx` 的“总览”页新增“连接诊断 / 连接判定”卡片，直接展示后端 URL、WebSocket URL、HTTP health 状态、WS 连接状态、最近错误类型、候选端口探测结果，以及旧项目/端口占用时的处理建议。
- 前端健康探测继续校验 `/api/health` 的 `status/app/event_types`，避免把旧项目或其他本地服务误判为 AStock 后端；WebSocket 仍使用 `/ws/events`。

## 1. 当前分支和最新提交

- 当前分支：`tauri-rewrite`
- 最新提交：`dce7b0d feat(events): add event system for CLI streaming output`，已推送到 `origin/tauri-rewrite`
- 本 handoff 批次包含的修复：
  - ✅ CLI流式运行器Phase 1：事件系统基础框架
  - ✅ `AgentEventEmitter`和`ConsoleSubscriber`创建
  - ✅ `MultiAgentOrchestrator`集成事件发射
  - ✅ 文档化CLI streaming实施计划

## 2. 当前已经完成的实现

| 模块 | 已完成 |
| --- | --- |
| `start.ps1` | 支持 `status/storage/offline/online/bench/dashboard/backend/frontend/modern-ui/tui/desktop-* / delivery-check`；端口占用确认；后端默认 `18080`。 |
| `apps/backend` | FastAPI + WebSocket；健康检查、配置、bench、前台/后台自动投资、流程、决策、股票、指标、事件、记忆、工具接口。 |
| `apps/frontend` | Next.js 现代控制台；tabs、React Flow、Recharts、设置、事件、智能体、LLM 检测。 |
| `apps/tui` | 长期并存的终端客户端；单选/多选初始化向导、输入即显式 slash command palette、20/80 交易看板、运行观测、上下文状态、附件路径保护、数据源诊断和后台任务提交。 |
| `apps/desktop` | Tauri 2 shell；PyInstaller sidecar；`.exe` 和 NSIS 安装包构建链路。 |
| Agent Markdown 持续学习 | 已新增 8 个 Agent Markdown 描述文件、用户偏好、经验记录、学习建议、后端管理接口、`/api/agents/learning/suggestions` 只读建议接口和 TUI `/agent` 命令骨架。 |
| 数据源 Provider chain | 已新增可配置数据源降级链、Baostock 默认补充源、AData/OpenBB/yfinance/Alpha Vantage/JQData 可选适配器和 `/api/data/providers` 脱敏诊断接口。 |
| Hooks | pre-commit 文档同步/密钥检查，post-commit 自动 push，Cursor stop hook 收尾检查。 |
| Docs | README、用户/开发/在线手册、Trellis、现代化计划、技术文档、交付总结。 |

## 3. 本轮正在收尾的代码修复

本轮从“可用 TUI 首版”继续打磨为长期并存的终端调试/长程运行入口。TUI 是 `apps/backend` 的客户端，不复制交易业务逻辑：配置、模型列表、自动投资、决策日志、股票看板、排行榜、Agent Markdown 学习和数据源诊断都通过共享 FastAPI API 获取。`/start` 默认调用 `/api/auto-investment/background`，后端立即返回 `run_id`，任务继续在后端进程中执行；TUI 退出不会强制中断后端任务。

| 文件 | 目的 |
| --- | --- |
| `apps/tui/app.py` / `apps/tui/__main__.py` | `python -m apps.tui` 终端入口，提供配置向导、对话流输入、清屏重绘和 20/80 交易看板/运行观测主界面。 |
| `apps/tui/backend_client.py` | TUI 到 FastAPI 的轻量 HTTP client，保持 GUI/TUI 同后端契约。 |
| `apps/tui/config_wizard.py` | 初始化配置向导，保存到 `data/runtime/settings.override.json`；数据模式单选、provider chain 多选、默认 LLM 模型 fuzzy 选择；启动时展示脱敏当前配置、回填已保存非密钥值、密钥留空保留旧值，并跳过未选数据源凭证。 |
| `apps/tui/prompt.py` | 输入 `/` 即显示带说明的命令候选，支持二级命令/参数、`/agent` 管理命令和后端模型名补全。 |
| `apps/tui/session.py` | TUI 本地状态、工作流/比赛模型选择、后端模型缓存、上下文估算、自动/手动压缩、附件路径识别和敏感文件预览保护。 |
| `apps/tui/commands/slash.py` | `/status`、`/models list/select/set/selected`、`/workflow`、`/start`、`/run`、`/providers`、`/dashboard trading/run/status`、`/compact`、`/permission`、`/sandbox` 等命令分发。 |
| `apps/tui/widgets/dashboard.py` | 排行榜、股票看板、决策日志、运行观测、Agent 编排、数据源诊断、todo/status 栏的文本渲染。 |
| `src/astock_agent_system/config.py` | 统一配置加载入口；真实环境变量优先，本地运行态配置优先于 `.env` 同名旧值，保证向导保存后立即生效且不回显密钥。 |
| `apps/backend/app.py` | 新增 `/api/auto-investment/background` 与后台任务广播复用 helper。 |
| `start.ps1` / `start.bat` | 新增 `-Mode tui`，自动复用或启动后端后进入终端客户端。 |

上一轮新增 Agent Markdown 持续学习系统，用 Markdown 维护投资 Agent 指令和可调权重，保持固定工作流，不引入 MCP / ACP / 插件总线。核心落点：

上一轮同时扩展数据源接入边界：`DataAgent` 不再硬编码 `Tushare -> AkShare`，而是通过 `DATA_PROVIDER_CHAIN` / `data.provider_chain` 控制在线降级顺序，默认 `Tushare -> Baostock -> AkShare -> offline samples`。AData、OpenBB、yfinance、Alpha Vantage、JQData 作为手动可选参考源接入；AAStock 和同花顺 Skill 只登记适配判断，当前不做未授权抓取，也不触发真实交易。

| 文件 | 目的 |
| --- | --- |
| `config/agents/*.md` | 8 个 Agent 的人类可读描述、机器可读规则、LLM Prompt 模板和学习入口。 |
| `config/user_profile.yaml` | 非密钥用户投资偏好，注入 LLM Prompt。 |
| `src/astock_agent_system/agent_descriptor.py` | Agent Markdown 加载、Prompt 渲染、备份和回滚。 |
| `src/astock_agent_system/agent_learning.py` | 经验 JSONL 记录、学习状态、统计分析、建议生成和最近建议读取。 |
| `apps/backend/app.py` | 暴露 Agent descriptor 与 learning status/suggestions/trigger API，供 GUI/TUI 共用。 |
| `apps/tui/commands/agent.py` | `/agent list/view/edit/backup/learning stats|suggestions|trigger` 命令骨架。 |
| `apps/tui/widgets/agent_panel.py` | Agent 管理面板和学习进度文本渲染骨架。 |
| `docs/technical/AGENT_MD_LEARNING.md` | Agent MD 格式、接口和维护说明。 |

旧 handoff 批次遗留修复记录如下：

| 文件 | 目的 |
| --- | --- |
| `start.ps1` | 只把 `Listen` 状态视为端口占用；打印并终止同端口多个监听进程；Next dev 使用 webpack。 |
| `apps/frontend/package.json` | `dev` 改为 `next dev --webpack`，新增 `dev:turbo`。 |
| `apps/frontend/scripts/build-desktop.mjs` | 静态桌面构建默认后端 URL 改为 `http://127.0.0.1:18080`。 |
| `apps/frontend/README.md` | 替换 create-next-app 默认说明，记录 webpack/Turbopack 边界。 |
| `README.md`、`docs/*` | 同步现代 UI 启动和 Turbopack 排障说明。 |

## 4. 下一轮首选任务

### Task A：GUI 连接可诊断性（已完成）

目标：用户不再只看到“连接中”。

完成状态：前端 API 层已导出 `getBackendDiscoveryDiagnostics()`，总览页已显示后端发现、HTTP health、WebSocket URL、WS 状态、最近错误、候选端口和下一步排障建议。下一轮应优先进入 Task B。

建议实现：

1. 在 `dashboard-api.ts` 暴露最近一次探测结果：candidate URL、HTTP 状态、错误类型。
2. 在 `trading-dashboard.tsx` 总览页显示：Backend URL、WebSocket URL、HTTP health 状态、WS 状态、最近错误。
3. 若发现旧项目占用前端端口，在文案中提示当前页面来源和启动命令。
4. 增加最小测试或 lint 验证。

### Task B：TUI 全局启动和实时刷新加固

目标：让 TUI 从任意目录稳定启动，并让长程后台任务更接近实时观测。

建议顺序：

1. 加固 `astock-tui` Windows entry point 和 `astock-tui.bat`，从任意目录启动时自动定位项目根目录。
2. 给 `/run` 增加可选轮询/刷新参数，例如 `/run --watch` 或 `/dashboard run --watch`。
3. 在运行观测中补充后台任务开始/结束时间、耗时、最近事件和错误摘要。
4. 继续保持 TUI 只调用 FastAPI 后端，不在终端层复制交易逻辑。

### Task C：前端组件拆分

目标：降低 `trading-dashboard.tsx` 单文件复杂度。

建议顺序：

1. 抽 `OverviewTab`。
2. 抽 `FlowTab`。
3. 抽 `EventsTab` / `LogsTab`。
4. 抽 `SettingsTab`，保留目录快速跳转。
5. 保持 API 契约不变。

### Task D：真实事件源最小接入

目标：把公告/新闻/交易时间输入变成 Agent 可见的事件。

建议顺序：

1. 优先复用现有 `event_timeline.py`。
2. 接入 AkShare 新闻或 Tushare 公告前先写 provider 边界。
3. 增加去重、缓存、失败降级。
4. UI 只展示脱敏摘要和来源链接。

## 5. 标准验证命令

常规：

```powershell
python -m pytest tests/test_backend_api.py
npm --prefix apps/frontend run lint
.\start.bat -Mode delivery-check
```

现代 UI：

```powershell
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
```

桌面：

```powershell
.\start.bat -Mode desktop-sidecar
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode desktop-build
```

## 6. 提交规则

每次结束前必须：

1. 更新受影响文档。
2. 运行相关验证，优先 `.\start.bat -Mode delivery-check`。
3. `git status` / `git diff` 检查。
4. 提交；post-commit 会自动 push。
5. 若 push 失败，报告重试命令：`git push origin tauri-rewrite`。

## 7. 不要做的事

- 不要提交 `.env`。
- 不要打印真实 token/key/webhook。
- 不要 `git reset --hard`、force push、amend，除非用户明确要求。
- 不要静默接入实盘交易。
- 不要把旧 `项目1-审稿agent系统` 的前端报错当成本项目前端错误。
