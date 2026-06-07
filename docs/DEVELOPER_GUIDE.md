# 开发者手册

本手册面向继续开发此项目的开发者。项目采用 Python src-layout，核心入口是 CLI、Streamlit UI 和调度器。

## 1. 开发环境

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
python -m pytest
```

项目脚本入口：

```powershell
python -m astock_agent_system.cli --help
astock-agent --help
.\start.bat -Mode backend -Port 18080
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
npm --prefix apps/frontend run lint
```

`apps/frontend` 的 `npm run dev` 和 `start.bat -Mode frontend/modern-ui` 默认使用 `next dev --webpack`。Next 16 的 Turbopack 在 Windows 本地持久化缓存损坏时可能触发 `range start index ... out of range` panic；只有需要复现 Turbopack 问题时才使用 `npm --prefix apps/frontend run dev:turbo`。

## 2. 目录和模块边界

```text
src/astock_agent_system/
  agents/          # 多 Agent 分析：技术、基本面、舆情、风控、组合
  backtest/        # VirtualAccount、回测和模拟盘账户
  data/            # DataAgent、TushareProvider、AkShareProvider
  llm/             # LLMClient、ModelBench、兼容 profile
  orchestrator/    # MultiAgentOrchestrator，多模型独立账户比赛
  scheduler/       # TradingTaskScheduler，自动投资和止损检查
  storage/         # MongoClient、RedisClient
  ui/              # Streamlit 看板
apps/backend/      # FastAPI/WebSocket 现代 UI 适配层
apps/frontend/     # Next.js 现代控制台
```

设计原则：

- 配置从 `config.py` 进入，真实密钥只来自环境变量或本地 `.env`。
- CLI 输出 JSON，便于 smoke、脚本和后续 API 集成。
- `apps/backend` 只做产品层 API/WebSocket 适配，不重写交易业务核心。
- 外部服务依赖懒加载，离线模式必须能运行。
- 自动投资是模拟盘，不应接入真实下单接口，除非未来单独加安全确认层。

## 3. 核心数据流

```text
DataAgent -> StockScreener -> MasterAgent -> MultiAgentOrchestrator
          -> VirtualAccount -> MongoClient -> Streamlit 观测看板
          -> TradingTaskScheduler -> stop_loss_check
```

说明：

- `MasterAgent` 负责单股票/每日分析。
- `MultiAgentOrchestrator` 负责每个模型独立账户和排行榜。
- `TradingTaskScheduler.run_auto_investment()` 是长期调度的自动投资入口。
- `VirtualAccount` 实现手续费、滑点、T+1 和持仓恢复。

## 4. LLM 扩展约定

`LLMClient` 支持：

- `openai`
- `codex`
- `anthropic`
- `claude_code`
- `auto`

新增 profile 时：

1. 在 `src/astock_agent_system/llm/client.py` 增加 profile 常量和请求体。
2. 保持 `_http_error_message` 和 `_safe_error_text` 的脱敏能力。
3. 增加单元测试，验证 header、URL、payload shape。
4. 用 `python -m astock_agent_system.cli bench --models <model-id> --limit 1` 做 smoke。

## 5. 数据源扩展约定

新增数据源时：

1. 在 `src/astock_agent_system/data/providers/` 下新增 provider。
2. 接口尽量与 `TushareProvider` / `AkShareProvider` 保持一致。
3. 在 `DataAgent` 中接入降级顺序。
4. 保持离线样例兜底，不要让无密钥环境崩溃。

## 6. 存储约定

MongoDB 主要集合职责：

- trades：模拟交易记录。
- position_snapshots：持仓快照。
- agent_decisions：Agent 决策。
- llm_rankings：模型排行榜。

Redis 用于缓存行情和 LLM 响应，不能作为唯一事实来源。

## 7. 测试和 smoke

常用测试：

```powershell
python -m pytest
python -m pytest tests/test_backend_api.py
python -c "from apps.backend.app import app; print(app.title)"
python -m astock_agent_system.cli bench --help
python -m astock_agent_system.cli bench --list-models
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
python -m mkdocs build --strict
```

如果在线 bench 失败，不要把完整错误日志和密钥公开上传。优先查看 JSON 输出中的 `next_steps`。

## 8. 代码风格

- Python 命名使用 snake_case。
- 数据对象优先使用 dataclass 和 `to_dict()`。
- CLI 输出使用 `json.dumps(..., ensure_ascii=False, indent=2)`。
- 对外部服务调用必须有异常保护和脱敏。
- 不要在代码或文档中写真实 token。

## 9. Cursor Skill、Hooks 与强制收尾

项目包含：

- `.cursor/hooks.json`：启用项目级 `stop` hook，用于开发会话结束前检查交付闭环。
- `.cursor/hooks/enforce-session-end.ps1`：检查未提交变更、代码/自动化变更是否同步文档、当前分支是否仍 ahead 未推送。
- `.cursor/skills/astock-trellis-handoff/SKILL.md`：Trellis handoff skill，固化新对话接手顺序、Phase 0/Phase 1 文档位置、smart-search/context-weaver/find-skills/create-skill 使用边界。
- `.cursor/skills/astock-delivery-workflow/SKILL.md`：交付工作流 skill，提醒维护一键启动、文档、验证和密钥保护。
- `.husky/pre-commit`：提交前强制密钥扫描、禁止本地 `.env` 入库、禁止代码/自动化变更无文档同步提交。
- `.husky/post-commit`：提交后强制推送当前分支到 GitHub `origin`。

默认不启用 `beforeShellExecution` gate，避免 Shell 命令反复要求人工审批。当前强制点放在 `pre-commit`、`post-commit` 和 Cursor `stop` hook：开发结束前必须更新受影响文档、运行相关验证、提交并推送。如果 GitHub push 因网络/TLS 失败，应保留本地提交并在交付说明中明确待执行命令。

常规收尾顺序：

```powershell
.\start.bat -Mode delivery-check
git status --short --branch
git add <changed-files>
git commit -m "<message>"
git push origin <branch>
```

若未来重新启用 shell 审批 hook，应避免返回 `ask`，只在真实密钥或 `.env` 入库等高风险场景自动 `deny`，普通开发命令应直接 `allow`。

新开对话或新 Agent 接手时，先读 `docs/trellis/HANDOFF.md`，再按该文档进入 `PHASE0_GRILLME.md`、`PRD.md`、`DESIGN.md` 和 `IMPLEMENT.md`。不要把未来设想写成已完成状态；如果 smart-search 不健康，只记录失败命令，不要声称完成了新的外部调研。

## 10. 后续开发建议

- 优先推进 `apps/backend` 的稳定 API 契约和 WebSocket 事件协议。
- 增加长期回放、模型账户长期指标、自动投资日志和止损时间线。
- 继续初始化 Next.js/React 前端和 Tauri 桌面壳。
- 实盘或半自动交易必须新增人工确认、权限隔离、审计日志和熔断机制。
