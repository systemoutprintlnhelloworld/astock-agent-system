# Trellis Handoff：下一位 AI 接手入口

更新时间：2026-06-09

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
- 最新提交以 `git log -1 --oneline` 为准；当前代码稳定点已推进到 `af20112 feat(tui): 完善配置向导与命令验证`，并已推送到 `origin/tauri-rewrite`。本 handoff 文档提交后可能会有后续 docs-only 提交。
- 本 handoff 批次已完成的重点修复：
  - TUI 配置向导支持已保存配置回填、密钥状态脱敏展示、按已选数据源跳过无关凭证问询。
  - `settings.override.json` 作为本地运行态配置优先于 `.env` 的同名旧值，避免向导保存后看起来未生效。
  - `/agent` 子命令与 slash palette 补全已对齐，`/dashboard` 默认交易看板，`/start` 会自动切换到运行观测视图。
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

优先做 **TUI 全局启动和实时刷新加固**。GUI 连接可诊断性已完成；如果新对话明确转回 GUI，则继续做组件拆分和连接诊断增强。当前 TUI 是长期并存的调试/观测入口，应先解决任意目录启动、长程任务实时刷新和运行观测细节。

最小任务：

1. 加固 `astock-tui` Windows entry point 和 `astock-tui.bat`，从任意目录启动时自动定位项目根目录。
2. 给 `/run` 增加可选轮询/刷新参数，例如 `/run --watch` 或 `/dashboard run --watch`。
3. 在运行观测中补充后台任务开始/结束时间、耗时、最近事件和错误摘要。
4. 继续保持 TUI 只调用 FastAPI 后端，不在终端层复制交易逻辑。

## 6. 常用验证命令

```powershell
python -m pytest tests/test_backend_api.py
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
