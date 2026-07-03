# Trellis Handoff：下一位 AI 接手入口

更新时间：2026-06-10

本文档是新开对话时给下一位 AI / 开发者的交接入口。目标是让接手者先理解项目边界、当前有效计划、最新修复、验证命令和禁止事项，再继续开发。

## 1. 接手前必须先读

按顺序阅读：

1. `AGENTS.md`：强制交付闭环和安全红线。
2. `.cursor/skills/astock-trellis-handoff/SKILL.md`：Trellis handoff workflow。
3. `.cursor/skills/astock-delivery-workflow/SKILL.md`：当前项目交付 workflow。
4. `docs/trellis/PHASE0_GRILLME.md`：需求拷问共识和开放问题。
5. `docs/trellis/PRD.md`：产品需求和验收标准。
6. `docs/trellis/DESIGN.md`：架构、端口、Turbopack、工具和下一轮设计优先级。
7. `docs/trellis/IMPLEMENT.md`：当前实现状态、本 handoff 批次修复、下一轮任务。
8. `docs/trellis-plan.md` 与 `docs/modernization-plan.md`：当前有效持久化计划。
9. `DOCUMENTATION_MAP.md`：完整文档导航。

## 2. 当前分支和最新状态

- 工作分支：`tauri-rewrite`。
- 最新提交以 `git log -1 --oneline` 为准；每轮收尾必须提交并推送到 `origin/tauri-rewrite`。
- 2026-07-03 增量状态：继续暂停 GUI/TUI 扩展，优先 Python CLI 后端逻辑。本轮新增 DataAgent datasource attempt 事件与持久化历史：`DataAgent` 可绑定 `AgentEventEmitter` 和 `run_id/agent_id/model`，每次 provider/cache/local/offline attempt 会发射 `data_source_switched` 并写入 Git 忽略的 `data/runtime/datasource_switch_history.jsonl`；新增 `python -m astock_agent_system.cli datasource history` 和 `/api/datasource/history` 读取该历史并返回 summary。`MultiAgentOrchestrator.run_competition()` 现在输出 `benchmark_statistics`，运行 summary 同步保存模型决策风格、动作分布、平均置信度/仓位、交易效率、LLM review 来源和错误模式。聚焦验证命令为 `python -m pytest tests/test_data_agent.py tests/test_orchestrator.py tests/test_backend_api.py -q`，最终仍需跑 `.\start.bat -Mode delivery-check`、commit、push。
- 2026-07-03 追加状态：连续运行模式已补跨轮看板，`agent start --continuous` 每轮结束后汇总轮次、下一轮计划时间、模型累计收益、持仓、最近错误和 datasource health，并把 `continuous_summary` 写入运行 summary；`apps/backend/schemas.py` 的 `EVENT_TYPES` 已补齐 CLI 细粒度事件名，`/api/health` 会暴露 analysis/data_fetch/portfolio 等事件类型。聚焦验证为 `python -m pytest tests/test_cli_observability.py tests/test_backend_api.py -q`。下一步优先真实 `AgentEventEmitter` -> WebSocket 桥接、新闻/公告 provider 与缓存/本地库；合并 main 需用户确认。
- 2026-06-13 增量状态：本轮继续暂停 GUI/TUI 扩展，优先修复 Python CLI 后端链路。已新增 smart-search CLI 解析/doctor 自检、交互式数据源页 smart-search/iWencai 入口、本地 SQLite 市场库覆盖率/日期热力图状态页、本地市场主动扫描 `datasource active-scan`，并让运行 payload/summary 明确记录 `run_id`、fresh start、账户快照恢复和同日幂等跳过信息。JQData `configure-jqdata` 现在支持 `--candidate-count` 隐藏输入多用户名候选探测，输出只保留候选序号和不可逆长度摘要，成功 preflight 后才保存到 Git 忽略的 runtime 配置。全局主动超短线首版已新增 `datasource active-research` 和 `agent global-active`：前者按本地 SQLite 做板块热度/候选池/择时研究，后者在模拟盘中按 T+1 守门生成组合级纸面动作。聚焦验证命令为 `python -m pytest tests/test_cli_observability.py tests/test_data_agent.py tests/test_orchestrator.py -q`，最终仍需按交付闭环跑 `delivery-check`、密钥检查、commit、push。
- 本 handoff 批次已完成的重点修复：
  - `SentimentAnalyst` 不再直接用裸 `smart-search` 命令，而是通过 `src/astock_agent_system/smart_search.py` 解析 Windows/npm `.CMD` shim，避免 Agent 长程运行中出现 `[WinError 2]`。
  - `datasource smart-search-status` 会输出 doctor 摘要、解析路径、通道状态和 next steps；JSON 输出必须先脱敏，不能把真实 key 写入日志或文档。
  - `datasource local-status` 已从库存页升级为本地市场库可观察性页，包含 K 线/行情/财务覆盖率、日期热力图、样本股票覆盖和行业/分组覆盖。
  - `datasource active-scan` 新增为本地 SQLite 广域发现层：直接扫描已同步 `quotes/stocks/bars/financials`，按行业、成交额、涨跌幅、短期动量和量能输出候选短名单；它不调用 provider、不调用 LLM、不下单，也不是买卖建议。
  - `MultiAgentOrchestrator.run_competition()` 返回 payload 现在包含 `run_id`、`account_mode`、`fresh_start`、`continue_from_storage`、`snapshot_restore`、`restored_account_count` 和 `skipped_agent_count`；`RunLogRecorder.write_summary()` 也写入这些字段，便于区分当前运行、历史日志、新账户和恢复账户。
  - 交互式数据源菜单已补齐 iWencai 状态/配置/公告检索和 smart-search 自检入口。
  - TUI 配置向导支持已保存配置回填、密钥状态脱敏展示、按已选数据源跳过无关凭证问询。
  - `settings.override.json` 作为本地运行态配置优先于 `.env` 的同名旧值，避免向导保存后看起来未生效。
  - `/agent` 子命令与 slash palette 补全已对齐，`/dashboard` 默认交易看板，`/start` 会自动切换到运行观测视图。
  - 数据源诊断修复：Baostock 股票池过滤指数/退市等非正常行，Tushare/AkShare 网络或限流失败进入本轮 source cooldown，`datasource status` 显示 `dependency_installed`，`datasource test` 对缺依赖/缺凭证返回 skipped 而不是误报崩溃。
  - 可选源补齐：`yfinance`、`jqdatasdk`、`adata` 已纳入 `.[market]`；JQData 可用 `python -m astock_agent_system.cli datasource configure-jqdata` 通过隐藏输入写入 Git 忽略的运行态配置。
  - JQData 配置入口新增 `--candidate-count`，用于不确定登录名形态时通过隐藏输入逐个 preflight；不要把真实手机号、账号或密码放入命令行、文档、截图或提交记录。
  - 新增全局主动超短线工具链：本地市场库工具、板块热度、候选批筛、可选实时报价刷新、超短线择时、组合级动作和 T+1 守门；事件流新增 global active 相关节点，便于 CLI/前端后续可观测。
  - iWencai SkillHub 从单一 `announcement-search` 诊断扩展为多技能工具视图；`iwencai-search --skill <name>` 可指定技能，安装型 CLI 不会被误判为可执行工具。
  - 真实后端 slash 链路验证与 `.\start.bat -Mode delivery-check` 已通过（65 passed）。
  - modern-ui / frontend dev 默认改用 `next dev --webpack`；`npm run dev:turbo` 仅用于复现 Turbopack 问题。

## 3. 当前架构不要误解

| 主题 | 正确理解 |
| --- | --- |
| 产品模式 | 只有 Benchmark 模式；N=1 不是单独模式。 |
| 多模型 | 每个模型驱动一套独立 8-Agent 系统和独立 `VirtualAccount`。 |
| 交易 | 当前只做模拟盘，不允许静默接入实盘。 |
| 最终交付 | 桌面 `.exe` / NSIS 安装包；`start.bat` 是开发和验证入口。 |
| 后端端口 | 新启动默认 `18080..18100`，旧 `8000..8020` 仅兼容健康 AStock 后端。 |
| 前端 dev | 默认 webpack，Turbopack 仅用于复现。 |

## 4. 外部工具和技能状态

- fast-context / 本地工作区检索：作为本地代码和架构理解的首选方式，优先用于快速定位符号、模块和跨文件关系。
- smart-search：`doctor --format json` 当前可跑通；如需新的外部调研，必须先重新跑 doctor 并保存证据，不能伪造检索结果。
- find-skills：已搜索 Trellis/handoff 相关 skill；搜索结果安装量偏低，暂未安装第三方 skill。
- create-skill：本轮按项目范围新增 handoff skill，固化下一轮接手流程。

## 5. 建议下一轮立即做什么

用户明确要求**暂停TUI/GUI开发，优先通过Python CLI命令打通后端逻辑**。

### 当前进展（2026-06-09）

已完成CLI流式运行器的增强基础：
- ✅ 创建事件系统 (`src/astock_agent_system/events/`)，并补齐学习、记忆、数据源事件类型。
- ✅ `AgentEventEmitter`、`ConsoleSubscriber` 和 Rich 优先的 `cli_enhanced.RichEventRenderer`。
- ✅ 在`MultiAgentOrchestrator`中集成 run/agent/learning 事件发射。
- ✅ 新增 CLI 命令：`agent start/status/history/stop/benchmark/learning status|suggestions|trigger/memory` 与 `datasource status`。
- ✅ 新增 `datasource test` 逐源 smoke 命令，默认只做快速 `history` 检查；需要完整检查时显式传 `--checks history,financial,quote --include-universe`。
- ✅ 修复在线数据源失败后离线样例缺失股票导致 `KeyError` 崩溃的问题；未知股票会返回保守空占位，筛选器会跳过不完整数据。
- ✅ 修复 Tushare `financial` Pandas Series 布尔判断错误，并为 `daily_basic` 限定查询窗口，避免无界查询。
- ✅ 修复 CLI 事件 payload 中 `agent_id` 重复导致 `agent start --offline` 崩溃的问题，决策详情现在放入 `decision` 字段。
- ✅ 后端新增 `/api/datasource/status`、`/api/datasource/history`、`/api/agents/{agent_id}/memory/similar`，并扩展 WebSocket 事件枚举。
- ✅ 本轮已把 CLI 主验证路径切到本地默认在线模型（当前本机为 `gpt-5.5`），不再把 `--model rule-baseline` 或 `--offline` 作为通过标准。
- ✅ `DataAgent` 在线 provider 调用已加入 `DATA_PROVIDER_TIMEOUT_SECONDS` 硬超时和本轮 cooldown；`agent start` 已加入 `--timeout-seconds` 总超时，避免命令持续监听/卡住。
- ✅ Baostock 已安装并验证 history 可用；Baostock 登录 stdout 已捕获，JSON 诊断不会被 `login success!` 污染。AkShare 当前网络下可能 empty/断连/超时，但会按诊断返回，不会阻塞。
- ✅ Baostock universe 已过滤指数/非正常股票，避免 `sh.000003` 等指数代码被误当作 A 股个股；Tushare 频率超限和 AkShare 断连会触发本轮 source cooldown，降低重复失败噪音。
- ✅ 已验证 Baostock `history/quote/financial`、yfinance `history/quote` 对 `600519` 可用；JQData 未配置本地凭证时明确 skipped；AData 2.9.5 当前公开行情接口可能返回空表，作为参考源而非主链前列。

本轮本地验证结论（不要误读为所有外部源永久可用）：

- `python -m pytest tests/test_data_agent.py tests/test_agent_descriptor_learning.py -q`：29 passed。
- `python -m astock_agent_system.cli datasource test --sources baostock,akshare --stock-code 600519 --days 5 --checks history --timeout-seconds 10 --format json`：纯 JSON 输出；Baostock history 成功；AkShare 在当前网络下可能 empty/断连/超时但不会阻塞。
- `python -m astock_agent_system.cli datasource test --sources baostock --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json`：Baostock 3 checks passed。
- `python -m astock_agent_system.cli datasource test --sources yfinance --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json`：yfinance history/quote passed，financial skipped（能力未声明）。
- `python -m astock_agent_system.cli datasource test --sources jqdata --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json`：未配置本地凭证时返回 skipped/missing credentials；不要把用户凭证写入命令或文档。
- `python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 60`：已用本地默认 `gpt-5.5` 在线配置跑通，输出决策、学习记录、收益摘要并正常退出。
- Tushare 当前受本地 token 频率限制影响；用户正在自行处理 token/额度。代码应只做脱敏诊断和降级，不应打印 token。

### 下一步优先级

**选项A（推荐）：验证增强 CLI 链路**
1. 运行 `python -m astock_agent_system.cli agent learning status --format json`。
2. 运行 `python -m astock_agent_system.cli datasource status --format json`。
3. 运行 `python -m astock_agent_system.cli datasource local-status --format text --stock-limit 12 --date-limit 30` 检查本地库覆盖率。
4. 运行 `python -m astock_agent_system.cli datasource active-scan --limit 30 --history-days 20 --min-amount 100000000 --format text`，先从本地库生成候选短名单。
5. 运行 `python -m astock_agent_system.cli datasource test --sources tushare,baostock,akshare,ths_skill --checks history --format json`，先看逐源真实状态。
6. 运行 `python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 60`，确认使用本地默认模型在线运行，并核对 summary 里的 `run_id/account_mode/snapshot_restore`。
7. 若通过，再继续增加更细粒度的 Agent 内部步骤事件。

**选项B：继续完整实现**
1. 让 `MasterAgent`、各分析 Agent 和 `DataAgent` 发射更细粒度的步骤/工具/降级事件。
2. 给 `agent benchmark` 补更完整的决策风格、学习速度和错误模式统计。
3. 把 datasource switch history 持久化到事件日志或 MongoDB。
4. 验证通过后再合并 `tauri-rewrite` 到 `main`。

详细计划见：`docs/trellis/CLI_STREAMING_PLAN.md`

### 如果用户改变主意继续TUI

最小任务：
1. 加固 `astock-tui` 全局启动（任意目录自动定位项目根）
2. `/run` 增加 `--watch` 实时刷新
3. 补充运行观测细节（时间、耗时、错误摘要）

## 6. 常用验证命令

```powershell
python -m pytest tests/test_backend_api.py
python -m pytest tests/test_cli_observability.py tests/test_data_agent.py tests/test_orchestrator.py -q
python -m pytest tests/test_config.py tests/test_agent_descriptor_learning.py -q
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode delivery-check
```

现代 UI：

```powershell
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
```

端口排查：

```powershell
Get-NetTCPConnection -LocalPort 3000,18080,8000 -ErrorAction SilentlyContinue |
  Where-Object { $_.State -eq 'Listen' } |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
```

后端健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:18080/api/health
```

## 7. 交付闭环

每轮结束必须：

1. 检查受影响文档是否同步。
2. 运行相关验证，默认优先 `.\start.bat -Mode delivery-check`。
3. `git status --short --branch`、`git diff -- .`。
4. commit；`.husky/post-commit` 会自动 push。
5. 如果 push 因网络/TLS 失败，保留本地 commit 并报告：`git push origin tauri-rewrite`。

## 8. 禁止事项

- 不要提交 `.env` 或任何真实密钥。
- 不要打印真实 LLM API key、Tushare token、Webhook、SMTP 密码。
- 不要用 `git reset --hard`、force push、amend，除非用户明确要求。
- 不要把旧 `项目1-审稿agent系统` 的 Next/Turbopack 错误归因成本项目。
- 不要把新的未来想法写成已完成状态。
