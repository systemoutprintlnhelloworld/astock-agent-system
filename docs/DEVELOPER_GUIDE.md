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
```

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
```

设计原则：

- 配置从 `config.py` 进入，真实密钥只来自环境变量或本地 `.env`。
- CLI 输出 JSON，便于 smoke、脚本和后续 API 集成。
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

## 9. Cursor Skill 与可选 Guard 脚本

项目包含：

- `.cursor/hooks.json`：当前保持空 hooks，避免 Shell 命令反复要求人工审批，保证自动化开发效率。
- `.cursor/hooks/guard-shell.ps1`：可选手动 guard 脚本，可用于验证 `.env` 入库、真实密钥形态命令、force push/reset 等策略。
- `.cursor/skills/astock-delivery-workflow/SKILL.md`：交付工作流 skill，提醒维护一键启动、文档、验证和密钥保护。

默认不启用 `beforeShellExecution` gate。若未来重新启用 hook，应避免返回 `ask`，只在真实密钥或 `.env` 入库等高风险场景自动 `deny`，普通开发命令应直接 `allow`。

## 10. 后续开发建议

- 优先增强观测看板：自动投资日志、止损时间线、收益曲线。
- 增加长期回放和模型账户长期指标。
- 再考虑 FastAPI / React 独立 Dashboard。
- 实盘或半自动交易必须新增人工确认、权限隔离、审计日志和熔断机制。
