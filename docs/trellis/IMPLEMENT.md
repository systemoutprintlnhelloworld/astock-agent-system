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
| `start.ps1` | 支持 `status/storage/offline/online/bench/dashboard/backend/frontend/modern-ui/desktop-* / delivery-check`；端口占用确认；后端默认 `18080`。 |
| `apps/backend` | FastAPI + WebSocket；健康检查、配置、bench、自动投资、流程、决策、股票、指标、事件、记忆、工具接口。 |
| `apps/frontend` | Next.js 现代控制台；tabs、React Flow、Recharts、设置、事件、智能体、LLM 检测。 |
| `apps/desktop` | Tauri 2 shell；PyInstaller sidecar；`.exe` 和 NSIS 安装包构建链路。 |
| Hooks | pre-commit 文档同步/密钥检查，post-commit 自动 push，Cursor stop hook 收尾检查。 |
| Docs | README、用户/开发/在线手册、Trellis、现代化计划、技术文档、交付总结。 |

## 3. 本轮正在收尾的代码修复

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
