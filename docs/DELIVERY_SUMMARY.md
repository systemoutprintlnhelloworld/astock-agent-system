# 交付总结

生成时间：2026-06-11

本项目当前已交付为一个可本地运行、可在线接入、可用 Git/GitHub 托管的 A 股 LLM 多 Agent 模拟盘自动投资系统。

## 2026-06-12 增量交付：数据源与运行可观察性

- iFinD / 同花顺 QuantAPI HTTP 适配器改为官方 `cmd_history_quotation` 历史行情与 `real_time_quotation` 实时报价端点，并保留 refresh token 重试与多形态响应解析。
- 新增 iWencai SkillHub 本地配置项与 CLI 诊断/隐藏输入保存入口：`datasource iwencai-status`、`datasource configure-iwencai`；真实 key 只写入 Git 忽略的 runtime 配置。
- 新增 `datasource iwencai-search` 和 `IwencaiSkillHub` adapter，用于公告/研究信源诊断；未安装 CLI、未配置 key 或缺少 `announcement-search` 技能时返回结构化 next steps，不进入行情 provider chain。
- 交互式数据源页面增加 iWencai 配置/状态入口；`config` 输出只显示 `has_iwencai_api_key`，不泄露密钥。
- Agent 前台运行增加终端安全的 `状态栏` 输出，持续显示模型、阶段、股票、步骤、决策、成交、收益和用时。
- MongoDB 不可达时改为 `E-MONGO-CONNECT` 短提示，不再把 `ServerSelectionTimeout` 长异常刷到用户终端。
- DebateRoom 改为显式收集技术/基本面/舆情 Agent 输入，生成多头、空头和评委轮次，让多 Agent 协作链可见。
- CLI 默认渲染现在会展开 DebateRoom 的输入证据、辩论轮次和评委结论，而不是只显示总分。
- StockScreener 在线模式改为先扫描更大的候选池再排序，避免“前 N 个能取到数据的股票”伪装成择优结果。

当前已进入现代化重构批次，开发分支为 `tauri-rewrite`。新批次目标是保留现有 Python 业务核心，同时增加 Tauri 2.0 桌面壳、Next.js/React 现代 UI、FastAPI API 适配层和 WebSocket 实时事件，使小白用户可以通过 `.exe` 或 `.bat` 一键启动并在 UI 中完成配置和观测。

> 重要：系统仍是模拟盘，不会真实下单，也不构成投资建议。

## 1. 已可直接使用的能力

- 离线样例数据运行：无密钥时也能验证主流程。
- 在线数据接入：支持可配置 provider chain，默认 Tushare、Baostock、AkShare，并保留离线兜底；AData/OpenBB/yfinance/Alpha Vantage/JQData 可作为手动参考源。
- 本地市场数据仓库：支持 `datasource sync-local` 将真实 provider-chain 成功返回的股票池、K 线、报价和财务快照批量写入 Git 忽略的 `data/market_local/market.sqlite`；在线 `DataAgent` 会先读本地 SQLite，再读 TTL 文件缓存和外部 provider。
- LLM 模型 bench：支持 `bench` 和兼容旧命令 `bench-models`。
- 多模型虚拟账户：每个 LLM/规则模型独立管理一个模拟账户。
- 自动投资轮次：可手动运行，也可由调度器定时运行。
- 风控止损检查：可读取持仓快照并执行模拟强制卖出。
- 同一交易日幂等保护：避免重复运行导致重复买入。
- MongoDB/Redis：可持久化交易、决策、持仓快照和排行榜。
- Streamlit 观测看板：可查看排行榜、持仓、盈亏、潜力股票、舆情和风险摘要。
- 一键启动脚本：`start.bat` / `start.ps1` 覆盖状态检查、离线运行、在线 bench、在线自动投资、看板、调度器和文档预览。
- Git/GitHub 文档托管：仓库已转为 Public，并启用 GitHub Pages workflow 模式。
- MkDocs Material 文档站：推送到 `main` 后由 GitHub Actions 自动构建并部署。
- Cursor Skill 与强制收尾 Hook：项目级 Skill、`.husky/pre-commit`、`.husky/post-commit` 和 Cursor `stop` hook 已固化交付闭环；自动 Shell 审批 Hook 默认关闭，避免开发命令反复人工批准。
- Tauri 桌面交付链路：`desktop-release -AutoInstallRust` 可构建桌面 `.exe` 和 Windows NSIS 安装包，桌面壳内置 Python FastAPI sidecar。
- 现代化重构计划：已新增 `docs/modernization-plan.md`，明确 Tauri/Next/FastAPI/WebSocket 架构、事件协议、风险和验证门禁。
- FastAPI 后端适配层预览：已新增 `apps/backend`，支持 `health`、脱敏配置、bench、自动投资触发、运行时配置保存、流程图/决策/股票/指标接口和 WebSocket 事件流。
- Next.js 现代控制台首版：已新增 `apps/frontend`，支持 React Flow 流程图、设置中心、实时事件流、可折叠决策日志、股票看板、模型排行榜和 Recharts 长期曲线。
- 总览引导增强：现代控制台首页新增“开箱检查清单”和“首次启动向导”，帮助小白用户先补齐配置再跑首轮验证。
- TUI 长程运行入口：`apps/tui` 复用同一个 FastAPI 后端，提供单选/多选初始化向导、已保存配置动态回填、密钥状态脱敏展示、按已选数据源跳过无关凭证、输入 `/` 即显示说明的命令面板、默认交易看板、`/run` 运行观测和 `/start` 后自动展示 run_id、状态、排行、持仓/交易与决策日志。
- CLI 客观数据与本地同步：`agent start` 默认展示公司/行情、ASCII K 线、技术指标、财务估值和 Agent 协作链；运行事件会写入 Git 忽略的脱敏 JSONL 日志和摘要；`datasource sync-local` 支持 `fill-gaps` / `all-providers` 参与情况观察，用于先批量同步本地数据再运行 Agent。
- CLI 交互式入口：日常测试 Python 后端现在可直接运行 `python -m astock_agent_system.cli` 进入工作流控制台；顶层拆成“LLM 配置与诊断 / 数据源配置与诊断 / 本地数据同步 / 运行工作流 / 学习中心 / 运行日志”页面，并保留快速向导，默认使用本地 `llm.default_model`，不再要求用户记忆复杂长命令。
- 数据源凭证准入：Tushare、JQData、iFinD / 同花顺 QuantAPI 的隐藏输入配置现在先做真实自检，失败时拒绝写入本地运行态配置；iFinD 会额外输出多股票/多代码格式矩阵诊断，帮助判断是代码格式、空返回还是账号权限问题。
- CLI UX 继续收敛：LLM 模型列表支持编号选择；本地同步页的第二项改为 SQLite 本地市场库状态；`datasource local-status` 可查看库存量、最近同步时间和最近同步记录；连续运行会先立即启动第 1 轮并显示倒计时。
- 运行结束看板补强：`agent start` 摘要新增账户看板、当前持仓、最近交易、买/卖次数和本轮 PnL，避免一轮跑完后只看到收益排行。
- smart-search 现在默认启用；若 CLI 请求失败会显示 `smart-search-error` 风险提示，而不是继续误导为“未启用”。iFinD 新增 `IFIND_BASE_URL` 配置、常见代码格式归一化和矩阵失败诊断；iWencai SkillHub 仍作为研究/公告技能边界记录，不把真实 key 写入仓库。

## 2. 最短运行路径

### 离线验证（推荐一键入口）

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
.\start.bat -Mode storage
.\start.bat -Mode offline -MaxCount 1 -Days 12
.\start.bat -Mode dashboard
```

### 在线验证

先复制并编辑 `.env`：

```powershell
Copy-Item .env.example .env
```

确认 `.env` 至少包含：

```env
DATA_MODE=online
DATA_PROVIDER_CHAIN=tushare,baostock,akshare
TUSHARE_TOKEN=your-tushare-token
LLM_BASE_URL=https://your-gateway.example/v1
LLM_API_KEY=your-api-key
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
LLM_DEFAULT_MODEL=gpt-5.5
SCHEDULER_MODELS=gpt-5.5
```

然后运行：

```powershell
python -m astock_agent_system.cli
.\start.bat -Mode status
.\start.bat -Mode bench
.\start.bat -Mode bench -BenchModel "gpt-5.5"
.\start.bat -Mode online -Models "gpt-5.5" -MaxCount 3 -Days 24
.\start.bat -Mode backend -Port 18080
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
.\start.bat -Mode tui -BackendPort 18080
```

其中 `python -m astock_agent_system.cli` 是推荐给日常测试的最短入口；后续 `start.bat` 命令仍保留给一键脚本、前后端联调和自动化验证。

### TUI 长程运行观测

```powershell
.\start.bat -Mode backend -Port 18080
python -m apps.tui --skip-wizard
```

进入 TUI 后可优先执行：

```text
/models list
/models select
/dashboard
/start --offline --max-count 2 --days 12
/run
/dashboard run
```

说明：初始化向导只保存基础配置和默认模型；比赛模型属于每轮并行 Agent/虚拟账户选择，可在运行前通过 `/models select`、`/models set` 或 `/start --models` 指定。向导保存到 `data/runtime/settings.override.json`，该运行态配置优先于本地 `.env` 的同名旧值，真实进程环境变量仍保持最高优先级。

## 3. 当前验证状态

最近一次本地验证结果：

- Python 测试：`81 passed`
- 前端 lint：`npm --prefix apps/frontend run lint` 通过
- `bench --help`：通过
- `bench-models --help`：通过
- `storage status --strict`：MongoDB/Redis 通过
- 离线自动投资 smoke：通过
- 一键 `status`、`bench`、`offline`：通过
- 在线 LLM `/models`：通过，返回 48 个模型
- 在线单模型 bench：`gpt-5.4-mini` 通过，JSON 可解析
- 在线自动投资：通过；同一交易日重复运行触发幂等跳过，未重复买入
- `modern-ui` 一键预览：`start.bat -Mode modern-ui -Port 3055 -BackendPort 8055` 启动通过
- `modern-ui` 默认端口链路：`start.bat -Mode modern-ui -Port 3000 -BackendPort 18080` 启动通过；可复用同项目后端并识别/清理残留 Next.js dev 进程；开发预览默认使用 Next.js webpack dev server，避免 Windows Turbopack 缓存损坏 panic 阻塞启动。
- MkDocs strict build：通过
- GitHub Pages：仓库已公开，Pages workflow 模式已启用
- Cursor Hook：逐条 Shell 审批 Hook 保持关闭；Cursor `stop` hook 已启用，用于开发结束前检查文档同步、未提交变更和未推送提交。
- Git ignore 检查：`.env` 和运行产物已忽略
- 文档/代码密钥扫描：未发现真实密钥或真实网关地址
- 桌面静态前端：`npm --prefix apps/frontend run build:desktop` 通过，产物复制到 `apps/desktop/dist`。
- 桌面 sidecar：`start.bat -Mode desktop-sidecar` 可生成 `apps/desktop/src-tauri/binaries/astock-backend-x86_64-pc-windows-msvc.exe`。
- 桌面 release：`start.bat -Mode desktop-release -AutoInstallRust` 可生成 `apps/desktop/src-tauri/target/release/astock-agent-desktop.exe` 和 `apps/desktop/src-tauri/target/release/bundle/nsis/AStock Agent System_0.1.0_x64-setup.exe`。
- 桌面运行时加固：前端不再依赖 Google Fonts；Tauri 壳与前端默认使用 `127.0.0.1:18080..18100`，并兼容探测旧的 `8000..8020` 健康 AStock 后端。
- TUI/配置回归：`python -m pytest tests/test_config.py tests/test_agent_descriptor_learning.py -q` 通过（21 passed），覆盖运行态配置优先级、向导列表型 provider chain、初始化不写比赛模型、`/agent stats` 别名、`/` 命令候选说明、`/models list` 模型缓存与补全、`/dashboard` 默认交易看板、`/start` 后运行观测和 `/run` 查看最近运行。
- CLI 交互式入口回归：`python -m pytest tests/test_cli_interactive.py tests/test_data_agent.py tests/test_llm_client.py tests/test_orchestrator.py tests/test_scheduler.py -q` 通过（37 passed），覆盖无子命令进入菜单、菜单退出、单轮 Agent 启动参数仍使用本地默认模型且不强制 offline。
- TUI 真实后端命令链路：已脱敏验证 `/help`、`/status`、`/models list/set/selected`、`/workflow offline`、`/providers`、`/config show`、`/config test-llm`、`/dashboard` 系列、`/start --offline --max-count 1 --days 12`、`/run`、`/agent list/stats`、`/compact`、`/permission`、`/sandbox`、`/theme`、`/lang`、`/attachments`、`/history` 和 `/memory` 均可执行。
- 当前交付门禁：`./start.bat -Mode delivery-check` 通过；本轮完整测试结果为 `81 passed`，并完成前端 lint、MkDocs strict build、后端 app import、sidecar entrypoint 检查和 tracked files 密钥扫描。
- 强制收尾门禁：`.husky/pre-commit` 会阻止代码/自动化变更无文档同步提交；`.husky/post-commit` 会强制推送当前分支；Cursor `stop` hook 会在会话结束前提示未提交、未推送和文档不同步问题。

## 4. 当前外部服务状态

当前在线 LLM 网关已验证可用。`bench --list-models` 可以获取模型列表，`gpt-5.4-mini` 单模型 JSON smoke 已通过。

需要注意：不同模型可能有不同分组、额度和可用渠道。例如某些模型可能返回“无可用渠道”，这属于网关/账户权限问题，不是本地代码失败。日常在线验证应优先使用本地 `LLM_DEFAULT_MODEL`（如 `gpt-5.5`）和 bench 通过的模型；`rule-baseline` 仅保留为诊断回退，不作为主验证路径。

当前需要用户自行准备或维护的信息只有：

1. `.env` 中的 Tushare token。
2. `.env` 中的 LLM gateway base URL 和 API key。
3. 可选 Alpha Vantage key、JQData 账号密码；只有主动加入 `DATA_PROVIDER_CHAIN` 时才使用。
4. 如需邮件/IM 推送，后续填写对应 webhook 或 SMTP 配置。

## 5. 文档入口

- GitHub 公开仓库：https://github.com/systemoutprintlnhelloworld/astock-agent-system
- 在线文档站：https://systemoutprintlnhelloworld.github.io/astock-agent-system/
- [使用者手册](USER_GUIDE.md)
- [在线运行手册](ONLINE_RUNBOOK.md)
- [开发者手册](DEVELOPER_GUIDE.md)
- [Trellis Handoff](trellis/HANDOFF.md)
- [GitHub 发布说明](GITHUB_PUBLISHING.md)
- [持久化开发计划](trellis-plan.md)
- [现代化重构计划](modernization-plan.md)
- 项目进度报告：见仓库根目录 `PROGRESS_REPORT.md`

## 6. 当前现代化重构路线

本轮重构不会删除已有 CLI、离线流程、在线 bench、调度器和 Streamlit 调试看板；这些能力继续作为验证和 fallback。现代化产品层按以下方向交付：

1. FastAPI 后端适配层和 WebSocket 事件通道。
2. Next.js/React/Shadcn/Tailwind/Lucide 前端壳和设置中心。
3. React Flow 实时 Agent 流程图，支持节点状态和流动箭头。
4. 可折叠决策日志、股票看板、模型排行榜和长期表现曲线。
5. Tauri 2.0 桌面壳与 Python sidecar，为后续便携版做准备。
6. UI 稳定后再进行文档站视觉和结构升级。

桌面交付当前推荐验证路径：

```powershell
.\start.bat -Mode desktop-doctor
.\start.bat -Mode desktop-release -AutoInstallRust
.\start.bat -Mode delivery-check
```

成功后主要产物：

```text
apps/desktop/src-tauri/target/release/astock-agent-desktop.exe
apps/desktop/src-tauri/target/release/bundle/nsis/AStock Agent System_0.1.0_x64-setup.exe
```

## 7. 后续可选增强

这些不是当前交付阻塞项，但可以继续迭代：

- 增加收益曲线和自动投资时间线。
- 增加长期模型排行榜和多日回放。
- 增加可拖拽 Agent 画布，用于自定义 Agent 节点和流程。
- 增加 Tauri 便携版发布自动化和内嵌 Python runtime 验证。
- 增加更真实的撮合、滑点和成交模型。
- 半自动或实盘交易前增加人工确认、审计日志和熔断机制。
