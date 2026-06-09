# Phase 1 - Design：架构与交接设计

更新时间：2026-06-09

本文档记录当前 Trellis 设计决策，帮助下一位 AI 在不破坏现有架构的基础上继续开发。

## 1. 总体架构

```text
Tauri Desktop Shell
  ├─ Python FastAPI sidecar: apps/backend/app.py
  ├─ Static Next.js frontend: apps/desktop/dist
  └─ Port discovery: 18080..18100, legacy 8000..8020

Next.js Modern UI
  ├─ apps/frontend/src/components/trading-dashboard.tsx
  ├─ apps/frontend/src/lib/dashboard-api.ts
  └─ React Flow / Recharts / Tailwind

Python Business Core
  ├─ src/astock_agent_system/agents
  ├─ src/astock_agent_system/orchestrator
  ├─ src/astock_agent_system/backtest/virtual_account.py
  ├─ src/astock_agent_system/scheduler
  └─ src/astock_agent_system/agent_memory.py
```

设计原则：`apps/backend` 和 `apps/frontend` 是产品适配层，不能把核心交易/Agent 逻辑复制到前端或 sidecar 壳里。

## 2. 关键设计决策

| 决策 | 当前选择 | 理由 |
| --- | --- | --- |
| 产品模式 | Benchmark only | 避免“单 LLM / 多 LLM”歧义，N=1 也是 Benchmark。 |
| 桌面技术 | Tauri 2 + PyInstaller sidecar | 最终用户打开 `.exe`，不要求安装 Python/Node。 |
| 后端默认端口 | `18080..18100` | 避免与其他项目常用 `8000` 冲突。 |
| 旧端口兼容 | 只复用健康 AStock `8000..8020` | 保护历史启动方式，不让非本项目进程阻塞。 |
| 前端 dev server | `next dev --webpack` | 避免 Windows Turbopack 持久化缓存 panic。 |
| 数据/密钥 | `.env` 本地维护，不入库 | 防止真实密钥泄露。 |
| 文档闭环 | code/script/hook/config 变更必须配文档 | 降低黑箱感，配合 pre-commit 强制执行。 |

## 3. 当前重点问题的设计状态

### 3.1 “连接中”问题

已完成：

- 后端新端口迁移到 `18080..18100`。
- Tauri 和前端保留旧 AStock 后端发现兼容。
- FastAPI CORS 支持 `tauri.localhost`。

下一步建议：

- 在 UI 总览页显示后端探测过程、WebSocket URL、最近错误。
- 把连接状态拆成 HTTP 健康、WebSocket、配置加载三个维度。

### 3.2 端口冲突问题

已完成：

- `start.ps1` 会显示端口占用 PID、进程名、路径、命令行，并确认后终止。
- `Get-PortOccupant` 已改为只看 `Listen` 连接，避免 `TIME_WAIT` / `CLOSE_WAIT` 误判。

下一步建议：

- 增加 `-AutoPort` 或推荐空闲端口自动选择策略。

### 3.3 Turbopack panic 问题

已完成：

- `apps/frontend/package.json` 默认 `dev` 改为 `next dev --webpack`。
- `dev:turbo` 保留用于复现。
- 文档同步解释 Windows Turbopack cache panic。

### 3.4 TUI 长程运行观测

已完成：

- TUI 作为长期并存终端客户端，复用 `apps/backend` FastAPI API，不复制交易业务逻辑。
- 初始化向导已支持单选/多选、已保存配置回填、密钥状态脱敏展示、按 provider chain 跳过无关凭证。
- `/dashboard` 默认交易看板，`/start` 后自动进入运行观测，`/run` 可查看当前/最近一次后台任务。
- Slash command palette 在输入 `/` 时显示命令和说明，并补全 `/dashboard`、`/models`、`/start`、`/agent` 等二级命令。

下一步建议：

- 加固 `astock-tui` 全局命令和任意目录启动时的项目根定位。
- 给 `/run` / `/dashboard run` 增加 `--watch` 实时刷新。
- 补充运行开始/结束时间、耗时、最近事件、错误摘要和更清晰的后台任务状态。

## 4. 外部工具与 Skill 状态

| 工具 | 当前状态 | 说明 |
| --- | --- | --- |
| fast-context / 本地检索 | 当前首选 | 用于快速定位端口、Trellis、handoff、TUI/GUI 启动和配置相关代码；不要再把 ContextWeaver 作为主要检索路径。 |
| smart-search | 当前 `doctor --format json` 可跑通 | 需要外部实时资料时先跑 doctor 并保存证据；不得伪造外部调研。 |
| find-skills | 已搜索 Trellis/handoff | 找到第三方 skill，但安装量较低，暂不安装。 |
| project skills | 已有 `astock-delivery-workflow` 与 `astock-trellis-handoff` | 固化交付闭环和下一轮接手流程。 |

## 5. 下一轮设计优先级

推荐顺序：

1. TUI 全局启动和实时刷新：`astock-tui` 任意目录启动、`/run --watch`、运行耗时/事件/错误摘要。
2. GUI 组件拆分：降低 `trading-dashboard.tsx` 单文件复杂度，保留现有 API 契约。
3. 真实事件源接入：AkShare 新闻 / Tushare 公告 / 交易时间事件。
4. Agent 记忆增强：收益归因、周总结、PortfolioManager 主动检索。
5. 桌面发布增强：自动更新、安装包签名、崩溃日志展示。
