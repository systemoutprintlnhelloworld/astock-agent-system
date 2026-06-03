# A股 LLM 自动投资系统 - 开发进度报告

生成时间：2026-06-03
当前阶段：自动投资 MVP 已可运行（阶段 1 基础设施 + 自动投资闭环已完成）

---

## 当前结论

系统已经从“投资建议平台”推进为可运行的模拟盘自动投资系统：

- 每个 LLM/规则模型拥有独立虚拟账户。
- 系统可自动筛选股票、生成决策、执行模拟买入/卖出、记录持仓快照。
- 调度器可每天自动运行投资轮次，并按间隔执行止损检查。
- Streamlit 已有“观测看板”，可查看排行榜、持仓涨跌、浮动盈亏、潜力股票、舆情与风险摘要。
- MongoDB/Redis 已可用于持久化与缓存。
- 同一交易日重复运行已加入幂等保护，避免重复买入。

当前仍是模拟盘，不会真实下单。

---

## 已完成的工作

### 1. 数据源与数据 Agent

**实现内容**：

- 创建 `TushareProvider`，支持在线行情/历史/财务数据。
- 创建 `AkShareProvider`，作为免费兜底数据源。
- 扩展 `DataAgent` 智能降级机制：Tushare -> AkShare -> 离线样例数据。
- 保留离线优先能力，无外部服务时仍可跑通主流程。

**关键文件**：

- `src/astock_agent_system/data/providers/tushare_provider.py`
- `src/astock_agent_system/data/providers/akshare_provider.py`
- `src/astock_agent_system/data/data_agent.py`
- `data/samples/stocks.json`

---

### 2. MongoDB / Redis 基础设施

**实现内容**：

- `MongoClient` 支持保存交易、持仓快照、Agent 决策、LLM 排行榜。
- `RedisClient` 支持行情缓存、LLM 响应缓存和缓存统计。
- Mongo 连接增加超时和 `ping`，避免服务不可用时长时间卡住。
- `storage status --strict` 可检查 MongoDB/Redis 依赖与连接状态。
- `docker-compose.yml` 已固定 Mongo 镜像为 `mongo:7.0`。

**关键文件**：

- `src/astock_agent_system/storage/mongo_client.py`
- `src/astock_agent_system/storage/redis_client.py`
- `docker-compose.yml`

**常用命令**：

```powershell
docker compose up -d
python -m astock_agent_system.cli storage status --strict
```

---

### 3. LLM 客户端与模型 bench

**实现内容**：

- 支持 OpenAI-compatible `/chat/completions`。
- 支持多种请求 profile：`openai`、`codex`、`anthropic`、`claude_code`、`auto`。
- `auto` 会自动尝试不同兼容模式。
- 错误信息已做密钥脱敏，避免输出完整 token。
- 模型 bench 可对比多个模型的成功率与 JSON 解析率。

**已验证能力**：

- 可读取网关模型列表。
- 可使用 OpenAI-compatible profile 完成 LLM 调用。
- 可运行模型 bench。

**关键文件**：

- `src/astock_agent_system/llm/client.py`
- `src/astock_agent_system/llm/model_bench.py`

---

### 4. 多 Agent 投资分析流水线

**实现内容**：

- `MasterAgent` 汇总数据、技术、基本面、舆情、风控和组合建议。
- 支持动态股票筛选。
- 支持规则基线和 LLM 审核。
- 输出结构化决策：动作、置信度、建议仓位、理由、风险备注。

**核心模块**：

- `DataAgent`
- `StockScreener`
- `TechnicalAnalyst`
- `FundamentalAnalyst`
- `SentimentAnalyst`
- `DebateRoom`
- `RiskManager`
- `PortfolioManager`
- `MasterAgent`

---

### 5. 多模型自动投资编排器

**实现内容**：

- `MultiAgentOrchestrator` 为每个模型创建独立虚拟账户。
- 每个模型账户独立决策、独立持仓、独立排名。
- 支持从 MongoDB 恢复上一轮账户快照。
- 支持持久化：交易、决策、持仓快照、排行榜。
- 支持排行榜字段：权益、现金、总收益、最大回撤、胜率、交易次数、当日盈亏。

**关键安全修复**：

- 已加入同一交易日幂等保护。
- 如果某账户当天已经运行过，系统会读取已有快照并标记：
  - `skipped_execution=true`
  - `skip_reason=already_ran_for_trade_date`
- 该账户不会再次调用 LLM，也不会重复买入。

**关键文件**：

- `src/astock_agent_system/orchestrator/multi_agent_orchestrator.py`
- `tests/test_orchestrator.py`

---

### 6. 模拟盘与风控执行

**实现内容**：

- `VirtualAccount` 支持现金、持仓、交易记录、权益曲线。
- 支持手续费、印花税、滑点。
- 支持 T+1 卖出限制。
- 支持从持仓快照恢复账户。
- 止损检查不再只是记录信号，已经可以执行模拟强制卖出。
- 若当天买入触发止损，会按 T+1 规则阻止同日卖出。

**关键文件**：

- `src/astock_agent_system/backtest/virtual_account.py`
- `src/astock_agent_system/scheduler/task_scheduler.py`
- `tests/test_scheduler.py`

---

### 7. 自动投资调度器

**实现内容**：

- `TradingTaskScheduler.run_auto_investment()` 已实现。
- 每日定时任务现在运行自动投资轮次，而不是只生成分析报告。
- 自动投资轮次完成后会立即执行一次止损检查。
- 支持通知开关。
- 支持 CLI 手动 smoke。
- 支持调度器默认模型列表配置。

**默认模型列表配置**：

`.env`：

```env
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini,codex-auto-review
```

`config/config.yaml`：

```yaml
scheduler:
  models:
    - rule-baseline
    - gpt-5.4-mini
    - codex-auto-review
```

`.env` 中的 `SCHEDULER_MODELS` 优先级高于 YAML。

**关键命令**：

```powershell
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12
python -m astock_agent_system.cli scheduler start
```

**关键文件**：

- `src/astock_agent_system/scheduler/task_scheduler.py`
- `src/astock_agent_system/cli.py`
- `src/astock_agent_system/config.py`
- `.env.example`
- `config/config.yaml`
- `tests/test_scheduler.py`
- `tests/test_config.py`

---

### 8. Streamlit 观测看板

**实现内容**：

- 新增“观测看板”页面。
- 展示 LLM 模型账户排行榜。
- 展示持仓、当前价、浮动盈亏、总权益。
- 展示同一交易日是否已执行/已跳过。
- 展示潜力股票、动作、系统把握、舆情评分、风控评分、主要理由和主要风险。
- 减少原始 JSON 暴露，转换为更易读的表格和说明。

**关键文件**：

- `src/astock_agent_system/ui/streamlit_app.py`
- `tests/test_ui_watch.py`

**启动命令**：

```powershell
streamlit run src/astock_agent_system/ui/streamlit_app.py
```

---

### 9. 文档与配置

**实现内容**：

- `README.md` 已更新为自动投资系统说明。
- `.env.example` 已补充调度器模型配置。
- `config/config.yaml` 已补充 `scheduler.models`。
- CLI `config` 输出已展示调度器模型列表。
- 文档强调 `.env` 不应提交，不在文档中写真实密钥。

---

## 验证结果

最近一次验证结果：

```powershell
python -m py_compile "src/astock_agent_system/config.py" "src/astock_agent_system/scheduler/task_scheduler.py" "src/astock_agent_system/cli.py"
```

结果：通过。

```powershell
python -m pytest
```

结果：

```text
28 passed in 0.32s
```

```powershell
python -m astock_agent_system.cli config
```

结果：通过，并能看到 `scheduler.models`。

```powershell
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12
```

结果：通过，返回 `status=ok`，并完成一次离线自动投资轮次和止损检查。

---

## 当前系统架构

```text
┌─────────────────────────────────────────┐
│ 数据层（已完成）                         │
│ ├─ TushareProvider                      │
│ ├─ AkShareProvider                      │
│ └─ DataAgent 智能降级                   │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 多 Agent 分析层（已完成 MVP）            │
│ ├─ 技术/基本面/舆情/风控 Agent          │
│ ├─ MasterAgent                          │
│ └─ LLM / 规则基线决策                   │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 自动投资编排层（已完成 MVP）             │
│ ├─ MultiAgentOrchestrator               │
│ ├─ 每模型独立虚拟账户                   │
│ └─ 同交易日幂等保护                     │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 模拟盘与风控层（已完成 MVP）             │
│ ├─ VirtualAccount                       │
│ ├─ T+1 / 手续费 / 滑点                  │
│ └─ 强制止损模拟执行                     │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 存储层（已完成）                         │
│ ├─ MongoClient 交易/持仓/决策/排行榜     │
│ └─ RedisClient 缓存                     │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 调度与看板（已完成 MVP）                 │
│ ├─ TradingTaskScheduler                 │
│ ├─ 每日自动投资 + 间隔止损检查          │
│ └─ Streamlit 观测看板                   │
└─────────────────────────────────────────┘
```

---

## 开发进度

- **阶段 1：基础设施与离线可运行闭环**：已完成
  - 数据源适配完成
  - MongoDB/Redis 完成
  - 配置与 CLI 完成
  - 测试通过

- **阶段 2：自动投资 MVP**：已完成
  - 多模型独立账户完成
  - 自动投资轮次完成
  - 持仓快照恢复完成
  - 同交易日幂等保护完成
  - 止损模拟执行完成

- **阶段 3：观测看板 MVP**：已完成
  - Streamlit 观测看板完成
  - 排行榜/持仓/盈亏/潜力股票/舆情风险展示完成

- **阶段 4：增强与生产化**：进行中
  - 独立前端 Dashboard 待做
  - 更细的盘中事件驱动待做
  - 更完整的通知系统待做
  - 更真实的成交/撮合模型待做
  - 长期回测与效果评估待增强

---

## 下一步建议

### 优先级 1：增强观测看板

- 增加“今日自动投资日志”。
- 增加“止损动作时间线”。
- 增加“LLM 决策对比详情”。
- 增加收益曲线和每日权益变化。

### 优先级 2：增强自动投资策略评估

- 增加多日自动投资回放。
- 增加模型账户长期排行榜。
- 增加胜率、回撤、夏普等指标的长期统计。
- 增加交易成本敏感性测试。

### 优先级 3：盘中事件驱动

- 增加盘中行情轮询。
- 增加价格/跌幅/舆情事件触发检查。
- 增加高风险标的自动降仓逻辑。

### 优先级 4：独立前端或 API

- FastAPI REST/WebSocket。
- React/ECharts Dashboard。
- 更适合长期运行的运维页面。

---

## 已知限制

1. 当前仍是模拟盘，不会真实下单。
2. 在线行情依赖 Tushare/AkShare 接口可用性。
3. LLM 决策依赖网关稳定性、模型格式兼容性和配额。
4. 当前成交模型仍较简化，后续可增强为更真实的撮合/滑点模型。
5. Streamlit 看板已能使用，但独立前端 Dashboard 尚未开始。

---

## 常用命令

```powershell
# 查看配置（不会打印完整密钥）
python -m astock_agent_system.cli config

# 检查 MongoDB/Redis
python -m astock_agent_system.cli storage status --strict

# 运行一次离线分析
python -m astock_agent_system.cli run --offline --max-count 3 --days 24

# 运行一次自动投资轮次
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12

# 启动长期调度器
python -m astock_agent_system.cli scheduler start

# 启动 Streamlit UI
streamlit run src/astock_agent_system/ui/streamlit_app.py

# 运行测试
python -m pytest
```

---

## 安全说明

- 不要提交 `.env`。
- 不要把真实 API Key、Tushare Token、Webhook 写入文档或代码。
- CLI `config` 只显示是否存在密钥，不显示完整密钥。
- 错误日志会尽量脱敏，但仍建议避免把完整终端日志公开上传。

