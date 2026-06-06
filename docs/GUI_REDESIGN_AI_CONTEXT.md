# GUI 重构交接上下文（一次性快照）

> 本文件是为了把当前 GUI 重构上下文交给其他 AI/开发者而生成的一次性快照。它不是长期维护文档；后续请以 `README.md`、`DOCUMENTATION_MAP.md`、`docs/modernization-plan.md`、`docs/trellis-plan.md` 和代码为准。

## 1. 当前产品形态

这是一个 A 股 LLM 多 Agent 模拟盘投资系统，当前只做模拟盘，不接入真实下单。

桌面产品目标：用户通过 Tauri 打包出的桌面应用打开现代化控制台，在 UI 中配置数据源、LLM、模型列表、风控和调度，启动自动投资，并查看 Agent 流程、事件、日志、持仓、盈亏和模型排行榜。

核心架构：

```text
apps/desktop   Tauri 2 桌面壳，负责启动/复用 Python sidecar 并加载静态前端
apps/frontend  Next.js / React / TypeScript / Tailwind 现代 GUI
apps/backend   FastAPI + WebSocket 适配层
src/           现有 Python 业务核心，多 Agent、数据、LLM、模拟账户、调度器
```

## 2. 这些发布产物分别是什么

| 路径 | 用途 | 是否给最终用户直接打开 |
| --- | --- | --- |
| `apps/desktop/dist/index.html` | Next.js 静态前端导出文件，由 Tauri WebView 加载 | 否，不建议直接双击 |
| `apps/desktop/src-tauri/binaries/astock-backend-x86_64-pc-windows-msvc.exe` | PyInstaller 打包的 FastAPI 后端 sidecar | 否，只是后端服务 |
| `apps/desktop/src-tauri/target/release/astock-agent-desktop.exe` | 便携版桌面主程序 | 是，可直接运行 |
| `apps/desktop/src-tauri/target/release/bundle/nsis/AStock Agent System_0.1.0_x64-setup.exe` | Windows 安装包 | 是，推荐给普通用户安装 |

如果只运行 sidecar，会看到 API 后端启动，但不会有 GUI。GUI 应从 `astock-agent-desktop.exe` 或 NSIS 安装后的应用入口打开。

## 3. 当前已知桌面连接问题与修复点

现象：桌面窗口显示等待 WebSocket，但浏览器访问 `/api/health` 看起来正常。

主要原因：Tauri 打包后的 WebView 页面 origin 是 `tauri.localhost`，前端需要先用 HTTP `fetch` 探测默认 `127.0.0.1:18080..18100`（并兼容旧 `8000..8020`）的 `/api/health`，再生成 `ws://127.0.0.1:<port>/ws/events`。如果 FastAPI CORS 没允许 `http://tauri.localhost` / `https://tauri.localhost`，HTTP 探测会被 WebView 拦截，导致前端端口发现失败，WebSocket 回退到错误端口。

相关修复位置：

- `apps/backend/app.py`：FastAPI CORS 已允许 `tauri.localhost`。
- `tests/test_backend_api.py`：新增测试覆盖 Tauri origin 的 CORS 预检。
- `apps/desktop/README.md`：增加 WebSocket 等待状态排查说明。

重建命令：

```powershell
.\start.bat -Mode desktop-sidecar
.\start.bat -Mode desktop-build
```

端口探测命令：

```powershell
foreach ($p in 18080..18100 + 8000..8020) { try { Invoke-RestMethod -Uri ("http://127.0.0.1:$p/api/health") -TimeoutSec 1 } catch {} }
```

## 4. GUI 重构必须理解的产品规则

1. **只有 Benchmark 模式**：不要再设计“单 LLM 模式 / 多 LLM 模式”切换。
2. 用户选择一个或多个模型；每个模型驱动一套独立 Agent 系统。
3. 每个模型系统有独立虚拟账户、持仓、交易、盈亏、记忆作用域。
4. `N=1` 也是 Benchmark 模式，只是当前只选了一个模型。
5. 当前系统只做模拟盘，不能加入真实下单入口。
6. UI 需要尽量透明化 Agent 行为：流程、事件、日志、工具调用、决策理由和风险说明要可见。
7. 不要在 UI、日志、文档中显示真实 API Key、Tushare token、Webhook 或 `.env` 内容。

## 5. GUI 当前主要页面和数据来源

当前主组件：`apps/frontend/src/components/trading-dashboard.tsx`

API 封装：`apps/frontend/src/lib/dashboard-api.ts`

后端入口：`apps/backend/app.py`

当前 tabs：

| Tab | 目标 | 主要接口 |
| --- | --- | --- |
| 总览 | 新手首页，展示健康状态、候选股票、下一步 | `/api/health`, `/api/config`, `/api/stocks/board`, `/api/metrics/rankings` |
| 流程 | React Flow 多 Agent 节点图 | `/api/agents/flow`, `/ws/events` |
| 表现 | 权益曲线、收益、回撤、排行榜 | `/api/metrics/equity`, `/api/metrics/rankings` |
| 事件 | 交易时间、公告、新闻、系统事件输入 | `/api/events/timeline`, `/api/events/poll`, `/ws/events` |
| 日志 | 决策日志和实时事件流 | `/api/decisions`, `/ws/events` |
| 股票 | 持仓、候选股、交易记录 | `/api/stocks/board` |
| 智能体 | Agent 工具、数据源、技能、记忆案例 | `/api/agents/tools`, `/api/agents/{agent_id}/memory` |
| 设置 | 数据源、LLM、组合、风控、调度 | `/api/config`, `/api/config/test-llm`, `/api/config` POST |

WebSocket：`/ws/events`

事件类型定义：`apps/backend/schemas.py` 中的 `EventType` / `EVENT_TYPES`。

## 6. 推荐其他 AI 优先阅读的文档

按顺序阅读即可：

1. `README.md`：项目当前能力和一键命令。
2. `DOCUMENTATION_MAP.md`：文档导航，区分外部用户/核心开发者。
3. `docs/modernization-plan.md`：现代化 GUI / Tauri / FastAPI 的有效计划。
4. `docs/trellis-plan.md`：当前 Trellis 持久化计划和完成状态。
5. `docs/technical/PRD_PHASE2.md`：持续学习、事件驱动、Agent 工具和透明化 PRD。
6. `docs/technical/ARCHITECTURE.md`：系统架构和 Agent 协作。
7. `docs/technical/FLOWS.md`：初始化到自动投资结束的流程和时序。
8. `docs/technical/DESIGN_DECISIONS.md`：UI 技术选型和透明化设计理由。
9. `docs/technical/USER_NEEDS_MAPPING.md`：用户场景到功能/代码位置的映射。
10. `docs/technical/COMPARISON.md`：同类开源项目参考。
11. `apps/desktop/README.md`：桌面打包、sidecar 和 WebSocket 排查。

## 7. GUI 重构建议边界

建议优先重构：

- 拆分 `trading-dashboard.tsx`，按 tab / card / form / chart 分组件。
- 改善视觉层级、导航、空状态、加载状态、错误状态。
- 增强“等待后端 / 等待 WebSocket”的可诊断性，直接显示正在探测的后端地址和 WebSocket 地址。
- 把新手向导、LLM 配置检测、模型选择、Benchmark 排行榜做成更清晰的主流程。
- 保留现有 API 契约，先不要重写业务核心。

不要优先做：

- 不要接入真实交易下单。
- 不要把 API Key / Token 暴露到日志或文档。
- 不要引入复杂知识库系统；当前只需要简单、可解释、可维护。
- 不要恢复“单 LLM 模式 / 多 LLM 模式”的产品切换。

## 8. 可直接交给其他 AI 的提示词

```text
请基于本仓库重构 GUI，但不要重写 Python 业务核心。先阅读：
README.md、DOCUMENTATION_MAP.md、docs/modernization-plan.md、docs/trellis-plan.md、docs/technical/PRD_PHASE2.md、docs/technical/ARCHITECTURE.md、docs/technical/FLOWS.md、docs/technical/DESIGN_DECISIONS.md、docs/technical/USER_NEEDS_MAPPING.md、apps/desktop/README.md、以及本文件 docs/GUI_REDESIGN_AI_CONTEXT.md。

重点理解：本系统只有 Benchmark 模式；用户选择 N 个模型，每个模型驱动一套独立 Agent 系统，并用独立虚拟账户比较盈亏。当前只做模拟盘，不允许真实下单。GUI 需要增强 Agent 透明化、配置防呆、事件时间线、决策日志、持仓盈亏和模型排行榜。

请优先拆分 apps/frontend/src/components/trading-dashboard.tsx，保留 apps/frontend/src/lib/dashboard-api.ts 的 API 契约，并确保桌面 Tauri WebView 下的 HTTP/WebSocket 连接仍可用。
```

## 9. 最小验证命令

```powershell
npm --prefix apps/frontend run lint
python -m pytest tests/test_backend_api.py
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode desktop-sidecar
.\start.bat -Mode desktop-build
.\start.bat -Mode delivery-check
```
