# Trellis Handoff：下一位 AI 接手入口

更新时间：2026-06-07

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
- 最新提交以 `git log -1 --oneline` 为准；本 handoff 批次开始前的已推送稳定点是 `e13bc16 fix: move astock backend to dedicated ports`。
- 本 handoff 批次新增/修复方向：
  - modern-ui / frontend dev 默认改用 `next dev --webpack`。
  - 保留 `npm run dev:turbo` 仅用于复现 Turbopack 问题。
  - `start.ps1` 端口占用检查只看 `Listen`，并打印同端口多个监听进程。
  - 新增 Trellis Phase 0 / PRD / Design / Implement / Handoff 文档。
  - 新增项目 handoff skill。

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

- context weaver：已用于本地代码检索，可继续作为代码理解第一步。
- smart-search：已按用户要求尝试；当前 `doctor` 未 ok，OpenAI-compatible 诊断遇到上游 `503` 和 CLI streaming response 异常。下一位 AI 不能声称已完成新的外部调研，除非重新跑通并保存证据。
- find-skills：已搜索 Trellis/handoff 相关 skill；搜索结果安装量偏低，暂未安装第三方 skill。
- create-skill：本轮按项目范围新增 handoff skill，固化下一轮接手流程。

## 5. 建议下一轮立即做什么

优先做 **GUI 连接可诊断性**，因为它直接解决用户对“连接中”和“黑箱”的不信任。

最小任务：

1. 在 `apps/frontend/src/lib/dashboard-api.ts` 记录最近一次 backend discovery 候选 URL、成功/失败、错误类型。
2. 在 `apps/frontend/src/components/trading-dashboard.tsx` 总览页展示：
   - backend base URL
   - WebSocket URL
   - HTTP health 是否 ok
   - WebSocket 是否 connected
   - 最近错误和下一步建议
3. 保持 API 契约，不重写 Python 业务核心。
4. 跑 `npm --prefix apps/frontend run lint` 和 `.\start.bat -Mode delivery-check`。

## 6. 常用验证命令

```powershell
python -m pytest tests/test_backend_api.py
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
