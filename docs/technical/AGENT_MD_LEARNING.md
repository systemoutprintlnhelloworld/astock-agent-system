# Agent Markdown 持续学习系统

更新时间：2026-06-07

本文档说明 AStock 如何用 Markdown 文件维护 8 个投资 Agent 的指令、规则参数和学习经验。该系统保持当前固定工作流，不引入 MCP、ACP、插件总线或 LangGraph 动态编排。

## 1. 设计边界

- 当前产品仍是 A 股多模型模拟盘 Benchmark，不接入真实下单。
- 每个模型驱动独立 Agent 系统和独立虚拟账户。
- Agent 工作流保持固定：`Screener -> Technical -> Fundamental -> Sentiment -> Debate -> Risk -> Portfolio`。
- 学习系统只记录经验、生成建议和提供人工可审查的 Markdown；不会静默修改策略或绕过风控。

## 2. 文件位置

```text
config/agents/
  technical_analyst.md
  fundamental_analyst.md
  sentiment_analyst.md
  risk_manager.md
  debate_room.md
  portfolio_manager.md
  screener.md
  master_agent.md
  learning/
    strategy_evolution.md
```

运行时生成的文件被 `.gitignore` 忽略：

- `config/agents/learning/*.json`
- `config/agents/learning/*.jsonl`
- `config/agents/versions/`

## 3. Agent Markdown 格式

每个 Agent Markdown 包含人类可读说明和机器可读配置：

````markdown
# TechnicalAnalyst 技术分析师

## 基本信息
- Agent ID: technical_analyst
- 版本: v1.0.0

## 机器可读配置
```yaml
agent_id: technical_analyst
version: v1.0.0
rules:
  ma_cross_bonus: 0.16
```
````

规则型 Agent 可从 `rules` 读取权重。LLM 型 Agent 可从 `Prompt模板` 渲染 prompt。

## 4. 用户偏好

用户偏好保存在 `config/user_profile.yaml`，不包含密钥：

```yaml
user_profile:
  risk_preference: moderate
  focus_areas:
    - technical_momentum
    - fundamental_value
  custom_rules:
    - "默认保持中等风险偏好。"
```

这些偏好会注入 `SentimentAnalyst` 和 `MasterAgent` 的 LLM Prompt 模板。

## 5. 学习机制

核心模块：

- `src/astock_agent_system/agent_descriptor.py`：加载、渲染、备份、回滚 Agent Markdown。
- `src/astock_agent_system/agent_learning.py`：记录经验、统计成功率、生成学习建议。

默认每 30 条经验触发一次学习分析。输出是建议而不是自动改配置。

学习分析会把可审查的策略复盘摘要追加到 `config/agents/learning/strategy_evolution.md`。该文件是受版本控制的人工审查记录，目的是保留“系统建议过什么、为什么建议”的历史；它不会自动改变任何 Agent Markdown 规则权重，也不会触发真实下单。提交前应检查新增建议是否只包含脱敏统计、Agent ID、规则路径和人工复核建议，不应包含 API key、token、真实网关地址或未脱敏用户凭证。

## 6. 后端接口

TUI 和 GUI 共享后端接口：

- `GET /api/agents/descriptors`
- `GET /api/agents/{agent_id}/descriptor`
- `POST /api/agents/{agent_id}/descriptor/backup`
- `POST /api/agents/{agent_id}/descriptor/rollback`
- `GET /api/agents/learning/status`
- `GET /api/agents/learning/suggestions`
- `POST /api/agents/learning/trigger?force=true`

## 7. TUI 命令骨架

当前已提供无 Textual 依赖的命令处理器，后续 TUI 主界面可直接复用：

```text
/agent list
/agent view technical
/agent edit technical
/agent backup technical
/agent learning stats
/agent learning suggestions
/agent learning trigger
```

对应代码：`apps/tui/commands/agent.py` 与 `apps/tui/widgets/agent_panel.py`。

## 8. 为什么不引入 MCP / Skills / ACP

- MCP 适合跨工具协议化调用；当前工具边界较小，FastAPI 和现有 Python 接口足够。
- Skills 更适合开发工作流固化；投资 Agent 指令更适合 Markdown 业务配置。
- ACP 适合复杂异步 Agent 通信；当前固定工作流更容易验证和审计。

后续如出现真实插件生态、外部工具市场或动态 DAG 需求，再重新评估。
