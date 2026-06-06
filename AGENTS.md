# AGENTS.md

本文件给继续开发本仓库的 Agent 使用，和 `.cursor/skills/astock-delivery-workflow/SKILL.md` 保持一致。

## 开发语言

- 与用户沟通默认使用中文。
- 代码、命令、路径和错误信息保持原样，避免翻译导致不可执行。

## 交付闭环是强制要求

每次开发结束前必须完成：

1. 检查受影响文档是否需要同步更新。
2. 运行相关验证，默认优先使用：

   ```powershell
   .\start.bat -Mode delivery-check
   ```

3. 提交最终变更。
4. 推送当前分支到 GitHub。若因为网络/TLS 失败，必须明确说明阻塞原因和待执行命令。

## 文档同步规则

以下变更必须同步至少一个开发者/使用者文档：

- `src/` 核心业务逻辑。
- `apps/backend/` API / WebSocket / sidecar。
- `apps/frontend/src/` 或 `apps/frontend/scripts/`。
- `apps/desktop/src-tauri/`。
- `start.ps1` / `start.bat`。
- `config/`。
- `.husky/` 或 `.cursor/hooks/` 自动化规则。

可更新的文档包括：`docs/`、`README.md`、`DOCUMENTATION_MAP.md`、`FINAL_DELIVERY.md`、`apps/desktop/README.md`、本文件或项目 Skill。

## Hooks 现状

- `.husky/pre-commit`：强制密钥扫描、禁止本地 `.env` 入库、禁止代码/自动化变更无文档同步提交。
- `.husky/post-commit`：强制自动推送当前分支到 `origin`，不再允许用环境变量跳过。
- `.cursor/hooks/enforce-session-end.ps1`：Cursor stop hook，会在会话结束前检查未提交变更、代码变更无文档同步、分支 ahead 未推送。

## 安全红线

- 不要打印或提交真实 LLM API Key、Tushare token、Webhook、SMTP 密码或 `.env`。
- 不要使用 `git reset --hard`、强推、amend 等破坏性 Git 操作，除非用户明确要求。
- 当前系统只做模拟盘，不得静默接入真实下单。
