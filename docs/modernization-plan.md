# 现代化重构计划

更新时间：2026-06-06

本计划用于将当前 Python CLI + Streamlit MVP 渐进升级为小白可直接使用的现代化桌面产品。所有示例均使用占位符，不包含真实密钥。

> 当前状态：本文件是现代化重构的有效计划文件之一，另一个有效计划入口是 [持久化开发计划](trellis-plan.md)。仓库中没有 `a股llm系统现代化重构_efa1eeac.plan.md`，该文件名不是当前可执行计划来源。

## 1. 产品目标

最终形态：用户下载便携版应用后，优先通过 Tauri 打包出的 `astock-agent-system.exe` 一键启动，在现代化 UI 中完成配置、启动自动投资、查看实时 Agent 流程、决策日志、股票看板和长期表现曲线。`start.bat` / `start.ps1` 仅作为开发期、调试期和过渡期入口，不是最终用户需要理解的产品形态。

核心体验目标：

- 不要求小白理解命令行和 JSON。
- 在 UI 中配置 LLM、数据源、投资策略、风控、调度、通知、备份、日志和性能参数。
- 用实时流程图展示 Agent 当前状态，并用流动箭头表示执行路径。
- 用可折叠日志卡片展示决策、动作、理由、评分、风险和交易结果。
- 用曲线和指标展示长期收益、回撤、排行榜、交易次数和账户表现。
- 当前仍只做模拟盘，不接入真实下单。

## 2. 架构决策

| 层次 | 技术选择 | 说明 |
| --- | --- | --- |
| 桌面壳 | Tauri 2.0 | 目标为便携版，后续通过 sidecar 启动 Python 后端。 |
| 前端 | Next.js + React + TypeScript | 目标跟进 Next.js 16、React 19；如生态依赖不兼容，记录原因后使用最新稳定等价版本。 |
| UI | Tailwind CSS + Shadcn UI + Lucide Icons | 面向现代化桌面产品设计，避免 Streamlit 式表单堆叠。 |
| 流程图 | React Flow | 展示 Agent DAG、节点状态、边动画和后续拖拽式 Agent 画布。 |
| 图表 | Recharts | 展示收益、回撤、排行榜和长期指标。 |
| 后端 | FastAPI + WebSocket | 新增适配层，复用现有 Python 业务核心。 |
| 业务核心 | 现有 `src/astock_agent_system` | 继续复用 `Settings`、`DataAgent`、`MasterAgent`、`MultiAgentOrchestrator`、`TradingTaskScheduler`、`VirtualAccount`。 |
| 打包 | PyInstaller + Tauri sidecar | 后续将 Python 后端打包为 sidecar，减少用户环境要求。 |

## 3. 目录规划

```text
apps/
  backend/        # FastAPI API 和 WebSocket 适配层
  frontend/       # Next.js/React 现代化 UI
  desktop/        # Tauri 2.0 桌面壳与 sidecar 配置
src/
  astock_agent_system/  # 现有 Python 核心，继续复用
docs/
  modernization-plan.md # 本计划
```

## 4. 后端接口边界

第一批 API 适配层只做产品层封装，不重写业务逻辑。

计划接口：

- `GET /api/health`：健康检查。
- `GET /api/config`：读取脱敏配置。
- `POST /api/bench`：触发模型 bench。
- `POST /api/auto-investment`：触发一次自动投资轮次。
- `GET /api/agents/flow`：返回 React Flow 初始节点和边。
- `GET /api/decisions`：返回结构化决策日志。
- `GET /api/stocks/board`：返回持仓、候选股、盈亏和当前价。
- `GET /api/metrics/equity`：返回长期权益曲线。
- `GET /api/metrics/rankings`：返回模型排行榜。
- `GET /api/runs/current`：返回当前运行任务状态。
- `WebSocket /ws/events`：推送 Agent 事件、日志事件、配置更新事件和错误事件。

所有 API 响应不得返回真实 API key、Tushare token 或 webhook。

已完成的首版骨架：

- `apps/backend/app.py` 已提供 FastAPI 应用、CORS、健康检查、脱敏配置、bench、自动投资触发、流程图数据、股票/决策/指标接口、运行时配置保存和 WebSocket 事件流。
- `apps/frontend` 已提供 Next.js 现代控制台首版，包含 React Flow 流程图、设置中心、实时事件流、可折叠决策日志、股票看板、模型排行榜和 Recharts 长期曲线。
- 已补齐 Phase 2 透明化最小接口：事件时间线、Agent 记忆只读查询、LLM 配置检测、Agent 工具清单。
- modern-ui 已改为 tabs 布局，并新增“事件”“智能体”页签；设置页保留目录式快速跳转。
- `start.bat -Mode backend -Port 18080` 可单独启动本地 API 预览。
- `start.bat -Mode modern-ui -Port 3000 -BackendPort 18080` 可一键拉起首版现代 UI 预览。
- `apps/desktop` 已新增 Tauri 2 桌面壳；`apps/backend/sidecar.py` 已作为 PyInstaller 入口；`start.bat` 已新增 `desktop-doctor`、`desktop-bootstrap`、`desktop-sidecar`、`desktop-dev`、`desktop-build`、`desktop-release` 和 `delivery-check`。
- `apps/frontend` 已支持 `output: "export"` 的静态桌面构建，`npm --prefix apps/frontend run build:desktop` 会把产物复制到 `apps/desktop/dist`。

最终桌面打包目标：

```text
用户双击 astock-agent-system.exe
  ↓
Tauri 主进程启动
  ↓
  ├─ Sidecar: 启动打包后的 Python FastAPI 后端
  │   └─ 内嵌运行时，不要求用户预装 Python
  │
  └─ WebView: 加载 Next.js 静态构建产物
      └─ 不要求用户预装 Node.js
  ↓
显示桌面控制台窗口
```

因此，后续 `apps/desktop` 的验收标准不是“再包一层 bat”，而是确保 `.exe` 管理 sidecar 生命周期、端口探测、异常提示和前端 WebView 加载。

## 5. 实时事件协议

事件类型初版：

- `run_started`
- `agent_started`
- `agent_step`
- `agent_completed`
- `decision_made`
- `trade_executed`
- `risk_checked`
- `timeline_event`
- `llm_checked`
- `memory_updated`
- `config_updated`
- `run_completed`
- `run_failed`
- `connection_established`
- `pong`
- `error`

事件基础结构：

```json
{
  "type": "agent_started",
  "timestamp": "2026-06-03T15:00:00",
  "run_id": "local-run-id",
  "agent_id": "technical_analyst",
  "payload": {}
}
```

## 6. 前端页面规划

第一批页面：

- 首页总览：运行状态、关键指标、下一步操作。
- Agent 流程图：React Flow DAG、节点状态、流动箭头、实时事件。
- 决策日志：折叠卡片、决策摘要、展开详情、风险和动作。
- 股票看板：当前持仓、候选股票、当前价、盈亏和交易记录。
- 曲线看板：权益曲线、回撤、排行榜、交易次数。
- 事件时间线：交易时间、公告、新闻、系统事件如何进入 Agent 输入流。
- 智能体清单：每个 Agent 的工具、数据源、技能和按模型隔离的记忆入口。
- 设置中心：LLM、数据源、策略、风控、调度、通知、备份、日志、性能和主题。
- 首次启动向导：引导用户先跑离线模式，再配置在线模式。

当前可测试产品路径：

```powershell
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
```

浏览器打开 `http://127.0.0.1:3000` 后，按“总览 → 流程 → 事件 → 智能体 → 设置”验证主要交付内容。

桌面打包检验路径：

```powershell
# 全自动路径：安装依赖、构建 sidecar、构建静态前端、运行质量门禁，并在需要时自动安装 Rust/Cargo 后打包桌面壳
.\start.bat -Mode desktop-release -AutoInstallRust

# 只验证除最终 .exe 编译外的链路
.\start.bat -Mode desktop-release -SkipDesktopBuild

# 只跑质量门禁
.\start.bat -Mode delivery-check

# 1. 检查 Node/npm/Python/Cargo 和 sidecar 状态
.\start.bat -Mode desktop-doctor

# 2. 构建 Python FastAPI sidecar；无需 Cargo
.\start.bat -Mode desktop-sidecar

# 3. 构建 Tauri 使用的 Next.js 静态前端；无需 Cargo
npm --prefix apps/frontend run build:desktop

# 4. 安装 Tauri CLI 包并启动/打包桌面壳；需要 Rust/Cargo
Push-Location apps/desktop; npm install; Pop-Location
.\start.bat -Mode desktop-dev
.\start.bat -Mode desktop-build
```

如果 `desktop-doctor` 显示 `MISSING: cargo`，说明当前机器还不能本地编译最终 `.exe`；此时可运行 `desktop-release -AutoInstallRust` 自动安装 Rust/Cargo，或先用 `desktop-release -SkipDesktopBuild` 验证除最终 `.exe` 编译外的完整链路。

## 7. 分阶段交付

| 阶段 | 目标 | 可验收结果 |
| --- | --- | --- |
| Week 1-2 | Tauri/Next/FastAPI 骨架 | 分支、计划、API skeleton、UI shell、WebSocket 协议。 |
| Week 2-3 | 配置中心和首次启动向导 | UI 可配置并保存，后端返回脱敏配置。 |
| Week 3-4 | 实时流程图和决策日志 | Agent 节点状态可更新，日志可折叠展开。 |
| Week 4-5 | 股票看板和长期曲线 | 持仓、候选股、权益曲线、排行榜可视化。 |
| Week 5-6 | Tauri sidecar 和便携版准备 | Tauri 配置、PyInstaller sidecar、静态前端构建和阶段验证入口。 |
| Week 6+ | 文档站现代化 | 学习 OpenClaw/Claude 风格，改造内容组织和视觉。 |

## 8. 风险和约束

- Tauri 便携版与内嵌 Python runtime 打包复杂，先交付 dev 启动链路，再处理完整打包。
- 配置热加载对进行中的交易任务存在一致性风险；第一版保存后立即广播 `config_updated`，但交易执行中的关键参数默认下一轮生效。
- LLM 模型可用性受网关分组、额度、限流影响；UI 必须显示可理解的错误和 next steps。
- 长期指标依赖 MongoDB 历史数据；无数据时展示空态和一键运行入口。
- 项目级 shell approval hook 按用户要求保持关闭，提交前通过密钥扫描和 Git ignore 保护安全。

## 9. 验证门禁

每个阶段提交前至少执行：

```powershell
python -m pytest
python -m mkdocs build --strict
git status --short
```

涉及桌面打包后再补充：

```powershell
python -m apps.backend.sidecar --help
.\start.bat -Mode desktop-doctor
.\start.bat -Mode desktop-sidecar
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode delivery-check
```

`desktop-dev` / `desktop-build` 属于最终桌面壳编译验证，必须在 Rust/Cargo 可用后执行；若 Cargo 缺失，应记录为环境前置条件，而不是标记为代码失败。

涉及 API/前端后再补充：

```powershell
python -c "from apps.backend.app import app; print(app.title)"
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run typecheck
```

如果某类依赖尚未安装或生态版本不兼容，应在文档中记录原因和下一步，不得假装验证通过。
