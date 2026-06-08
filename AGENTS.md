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

## 统一持续开发规范

- 用户说“请继续”或要求持续推进时，按照 Trellis 指导开发：将当前计划、研究、决策、验证和交接写入 `docs/trellis/`、`docs/trellis-plan.md`、`docs/DELIVERY_SUMMARY.md` 或其他持久化文件。
- 对项目中需要用户申请、授权或提供的信息（Tushare token、LLM key/base URL、SMTP/Webhook、部署权限、付费额度、破坏性操作许可等），通过 cunzhi/反馈工具说明阻塞范围；其余事项默认继续开发直到可交付。
- 开发中使用 smart-search 获取外部/官方/实时知识，使用 fast-context / `fast_context_search` 搜索本地代码和架构；禁止再把 ContextWeaver、ACE、ace-tool、augment-context-engine 或 codebase-retrieval 作为首选检索入口。
- 需求不清或会影响产品/架构方向时，用 grill-me 对需求进行拷问；需要新能力时先用 find-skills 寻找可用 skill，再用 create-skill/skill creator 固化高频工作流。
- 通过 Git 做版本控制、状态检查、提交和推送，并严格遵守本项目交付闭环；禁止 `reset --hard`、强推、amend 等破坏性 Git 操作，除非用户明确要求。
- 通过 hook 强制执行安全、文档同步、验证、密钥保护和交付收尾规范；行为、命令、配置或交付状态变化必须即时更新文档。

## 安全红线

- 不要打印或提交真实 LLM API Key、Tushare token、Webhook、SMTP 密码或 `.env`。
- 不要使用 `git reset --hard`、强推、amend 等破坏性 Git 操作，除非用户明确要求。
- 当前系统只做模拟盘，不得静默接入真实下单。
