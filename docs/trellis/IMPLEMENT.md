# Phase 1 - Implement：当前实现状态与下一步执行计划

更新时间：2026-06-07

本文档把当前实现状态、验证命令、下一步可执行任务写成持久化 handoff 计划。新对话应先读本文件，再继续编码。

## 1. 当前分支和最新提交

- 当前分支：`tauri-rewrite`
- 最新提交以 `git log -1 --oneline` 为准；本 handoff 批次开始前的已推送稳定点是 `e13bc16 fix: move astock backend to dedicated ports`。
- 本 handoff 批次包含的修复：Next dev 改 webpack、端口占用识别增强、handoff 文档与 skill。

## 2. 当前已经完成的实现

| 模块 | 已完成 |
| --- | --- |
| `start.ps1` | 支持 `status/storage/offline/online/bench/dashboard/backend/frontend/modern-ui/tui/desktop-* / delivery-check`；端口占用确认；后端默认 `18080`。 |
| `apps/backend` | FastAPI + WebSocket；健康检查、配置、bench、前台/后台自动投资、流程、决策、股票、指标、事件、记忆、工具接口。 |
| `apps/frontend` | Next.js 现代控制台；tabs、React Flow、Recharts、设置、事件、智能体、LLM 检测。 |
| `apps/tui` | 轻量终端客户端首版；初始化配置向导、slash 命令、20/80 文本分栏、上下文状态、附件路径保护、数据源诊断和后台任务提交。 |
| `apps/desktop` | Tauri 2 shell；PyInstaller sidecar；`.exe` 和 NSIS 安装包构建链路。 |
| Agent Markdown 持续学习 | 已新增 8 个 Agent Markdown 描述文件、用户偏好、经验记录、学习建议、后端管理接口、`/api/agents/learning/suggestions` 只读建议接口和 TUI `/agent` 命令骨架。 |
| 数据源 Provider chain | 已新增可配置数据源降级链、Baostock 默认补充源、AData/OpenBB/yfinance/Alpha Vantage/JQData 可选适配器和 `/api/data/providers` 脱敏诊断接口。 |
| Hooks | pre-commit 文档同步/密钥检查，post-commit 自动 push，Cursor stop hook 收尾检查。 |
| Docs | README、用户/开发/在线手册、Trellis、现代化计划、技术文档、交付总结。 |

## 3. 本轮正在收尾的代码修复

本轮新增 TUI 首版，让 GUI 调试困难时可直接在终端验证同一套后端能力。TUI 是 `apps/backend` 的客户端，不复制交易业务逻辑：配置、模型列表、自动投资、决策日志、股票看板、排行榜、Agent Markdown 学习和数据源诊断都通过共享 FastAPI API 获取。`/start` 默认调用 `/api/auto-investment/background`，后端立即返回 `run_id`，任务继续在后端进程中执行；TUI 退出不会强制中断后端任务。

| 文件 | 目的 |
| --- | --- |
| `apps/tui/app.py` / `apps/tui/__main__.py` | `python -m apps.tui` 终端入口，提供配置向导、对话流输入和 20/80 文本分栏首页。 |
| `apps/tui/backend_client.py` | TUI 到 FastAPI 的轻量 HTTP client，保持 GUI/TUI 同后端契约。 |
| `apps/tui/config_wizard.py` | 初始化配置向导，保存到 `data/runtime/settings.override.json`，摘要不回显密钥。 |
| `apps/tui/session.py` | TUI 本地状态、工作流/模型选择、上下文估算、自动/手动压缩、附件路径识别和敏感文件预览保护。 |
| `apps/tui/commands/slash.py` | `/status`、`/models`、`/workflow`、`/start`、`/providers`、`/dashboard`、`/compact`、`/permission`、`/sandbox` 等命令分发。 |
| `apps/tui/widgets/dashboard.py` | 排行榜、股票看板、决策日志、Agent 编排、数据源诊断、todo/status 栏的文本渲染。 |
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

### Task A：GUI 连接可诊断性

目标：用户不再只看到“连接中”。

建议实现：

1. 在 `dashboard-api.ts` 暴露最近一次探测结果：candidate URL、HTTP 状态、错误类型。
2. 在 `trading-dashboard.tsx` 总览页显示：Backend URL、WebSocket URL、HTTP health 状态、WS 状态、最近错误。
3. 若发现旧项目占用前端端口，在文案中提示当前页面来源和启动命令。
4. 增加最小测试或 lint 验证。

### Task B：前端组件拆分

目标：降低 `trading-dashboard.tsx` 单文件复杂度。

建议顺序：

1. 抽 `OverviewTab`。
2. 抽 `FlowTab`。
3. 抽 `EventsTab` / `LogsTab`。
4. 抽 `SettingsTab`，保留目录快速跳转。
5. 保持 API 契约不变。

### Task C：真实事件源最小接入

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
