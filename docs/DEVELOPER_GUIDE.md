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
.\start.bat -Mode tui -BackendPort 18080
npm --prefix apps/frontend run lint
```

`apps/frontend` 的 `npm run dev` 和 `start.bat -Mode frontend/modern-ui` 默认使用 `next dev --webpack`。Next 16 的 Turbopack 在 Windows 本地持久化缓存损坏时可能触发 `range start index ... out of range` panic；只有需要复现 Turbopack 问题时才使用 `npm --prefix apps/frontend run dev:turbo`。

## 2. 目录和模块边界

```text
src/astock_agent_system/
  agents/          # 多 Agent 分析：技术、基本面、舆情、风控、组合
  backtest/        # VirtualAccount、回测和模拟盘账户
  data/            # DataAgent、provider chain、Tushare/Baostock/AkShare/可选参考源
  llm/             # LLMClient、ModelBench、兼容 profile
  orchestrator/    # MultiAgentOrchestrator，多模型独立账户比赛
  scheduler/       # TradingTaskScheduler，自动投资和止损检查
  storage/         # MongoClient、RedisClient
  ui/              # Streamlit 看板
apps/backend/      # FastAPI/WebSocket 现代 UI 适配层
apps/frontend/     # Next.js 现代控制台
apps/tui/          # 终端客户端；只调用 FastAPI，不承载交易业务逻辑
```

设计原则：

- 配置从 `config.py` 进入；优先级为真实进程环境变量 > `data/runtime/settings.override.json`（TUI/GUI 本地向导保存，Git 忽略）> 本地 `.env` > YAML 默认。密钥只允许保存在本机运行态、`.env` 或真实环境变量中，不得写入仓库。
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
- GUI 和 TUI 都通过 `apps/backend` 调用同一套业务核心；TUI 的 `/start` 默认走 `/api/auto-investment/background`，后端立即返回 `run_id`，任务继续在后端进程执行。

## 4. GUI 后端发现与连接诊断约定

现代控制台的后端发现逻辑集中在 `apps/frontend/src/lib/dashboard-api.ts`：

- 默认配置来自 `NEXT_PUBLIC_BACKEND_URL`，否则使用 `http://127.0.0.1:18080`。
- 自动探测 `18080..18100`，并兼容旧的 `8000..8020` 健康 AStock 后端。
- 健康探测必须校验 `/api/health` 的 `status === "ok"`、`app` 包含 `astock`、并且 `event_types` 是数组，避免把其他本地项目误判成后端。
- `getBackendDiscoveryDiagnostics()` 对 GUI 暴露当前候选 URL、HTTP 状态、错误类型、最近成功候选、探测次数和下一步建议。
- `apps/frontend/src/components/trading-dashboard.tsx` 的“总览”页负责展示 HTTP health、WebSocket URL、WebSocket 状态、候选端口和最近错误；不要把诊断逻辑散落到各个 tab。

后续调整连接逻辑时，应保持 API 契约向后兼容，并至少运行 `npm --prefix apps/frontend run lint`。如果修改了后端接口，还应同步 `tests/test_backend_api.py` 和本手册的接口说明。

## 5. TUI 客户端约定

`apps/tui` 当前是依赖轻量的终端客户端骨架，后续可替换为 Textual 交互壳，但模块边界保持不变：

- `apps/tui/backend_client.py`：仅封装 FastAPI HTTP 契约。
- `apps/tui/config_wizard.py`：初始化配置向导，保存到 `data/runtime/settings.override.json`，摘要不回显密钥。
- `apps/tui/session.py`：本地 UI 状态、模型/工作流选择、上下文占用估算、附件路径识别和敏感附件预览保护。
- `apps/tui/commands/slash.py`：`/status`、`/models`、`/workflow`、`/start`、`/providers`、`/dashboard`、`/compact`、`/permission`、`/sandbox` 等命令分发。
- `apps/tui/widgets/`：文本渲染 helper，供轻量 TUI、测试和未来 Textual widget 复用。

设计约束：TUI 不复制 `DataAgent`、`MasterAgent`、`TradingTaskScheduler` 或模拟盘逻辑；可观察性来自后端状态、排行榜、决策日志、股票看板、数据源诊断和本地上下文状态栏。

## 6. LLM 扩展约定

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

## 7. 数据源扩展约定

当前 `DataAgent` 使用可配置 provider chain，默认顺序为：

```text
tushare -> baostock -> akshare -> offline samples
```

更多数据源矩阵、凭证和诊断接口见 [数据源 Provider 接入说明](technical/DATA_PROVIDERS.md)。

新增数据源时：

1. 在 `src/astock_agent_system/data/providers/` 下新增 provider。
2. 接口尽量与 `TushareProvider` / `AkShareProvider` 保持一致。
3. 在 `src/astock_agent_system/data/data_agent.py` 的 `PROVIDER_CATALOG` 中注册能力、凭证字段和限制。
4. 通过 `DATA_PROVIDER_CHAIN` 或 `config/config.yaml` 控制降级顺序。
5. 保持离线样例兜底，不要让无密钥环境崩溃。

## 8. 存储约定

MongoDB 主要集合职责：

- trades：模拟交易记录。
- position_snapshots：持仓快照。
- agent_decisions：Agent 决策。
- llm_rankings：模型排行榜。

Redis 用于缓存行情和 LLM 响应，不能作为唯一事实来源。

## 9. 测试和 smoke

常用测试：

```powershell
python -m pytest
python -m pytest tests/test_backend_api.py
python -c "from apps.backend.app import app; print(app.title)"
python -m astock_agent_system.cli bench --help
python -m astock_agent_system.cli bench --list-models
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
.\start.bat -Mode tui -BackendPort 18080
python -m mkdocs build --strict
```

后端 API 契约优先以 `apps/backend/app.py`、`apps/backend/schemas.py` 和 `apps/frontend/src/lib/dashboard-api.ts` 为准。常用现代化接口包括 `POST /api/config`、`POST /api/auto-investment`、`POST /api/auto-investment/background`、`GET /api/data/providers`、`GET /api/agents/learning/status` 和 `GET /api/agents/learning/suggestions`。

如果在线 bench 失败，不要把完整错误日志和密钥公开上传。优先查看 JSON 输出中的 `next_steps`。

## 10. 代码风格

- Python 命名使用 snake_case。
- 数据对象优先使用 dataclass 和 `to_dict()`。
- CLI 输出使用 `json.dumps(..., ensure_ascii=False, indent=2)`。
- 对外部服务调用必须有异常保护和脱敏。
- 不要在代码或文档中写真实 token。

## 11. Cursor Skill、Hooks 与强制收尾

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

## 12. 后续开发建议

- 优先推进 `apps/backend` 的稳定 API 契约和 WebSocket 事件协议。
- 增加长期回放、模型账户长期指标、自动投资日志和止损时间线。
- 继续初始化 Next.js/React 前端和 Tauri 桌面壳。
- 实盘或半自动交易必须新增人工确认、权限隔离、审计日志和熔断机制。
