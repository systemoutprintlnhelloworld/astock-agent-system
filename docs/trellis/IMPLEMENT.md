# Phase 1 - Implement：当前实现状态与下一步执行计划

更新时间：2026-06-09

本文档把当前实现状态、验证命令、下一步可执行任务写成持久化 handoff 计划。新对话应先读本文件，再继续编码。

## 最新交付记录：TUI UX / 运行可观察性

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
