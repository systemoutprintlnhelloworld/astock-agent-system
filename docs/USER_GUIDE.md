# 使用者手册

本手册面向第一次运行系统的使用者。当前系统是模拟盘自动投资系统：它会自动筛选股票、让多个 LLM/规则账户分别管理虚拟资金、记录模拟交易和止损检查，并在 Streamlit 观测看板里展示结果。

> 当前不会真实下单，也不构成投资建议。请只用于学习、研究和模拟盘验证。

在线文档站：https://systemoutprintlnhelloworld.github.io/astock-agent-system/

## 1. 安装环境

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
python -m astock_agent_system.cli --help
```

如果只想先离线体验，也可以不配置任何在线密钥。

## 2. 准备本地配置

复制示例配置：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`。不要把 `.env` 上传到 GitHub。

最小离线配置：

```env
DATA_MODE=offline
SMART_SEARCH_ENABLED=false
SCHEDULER_MODELS=rule-baseline
```

在线运行需要补充：

```env
DATA_MODE=online
TUSHARE_TOKEN=your-tushare-token
LLM_BASE_URL=https://your-gateway.example/v1
LLM_API_KEY=your-api-key
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini
```

## 3. 启动 MongoDB 和 Redis

模拟盘排行榜、持仓快照、交易记录需要 MongoDB；缓存需要 Redis。

```powershell
docker compose up -d
python -m astock_agent_system.cli storage status --strict
```

看到 MongoDB 和 Redis 都是 `connection: ok` 后，再继续运行自动投资。

## 4. 离线验证主流程

如果你还没配置在线数据和 LLM，先跑离线流程：

```powershell
python -m astock_agent_system.cli config
python -m astock_agent_system.cli run-daily --offline --max-count 3 --days 24
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12
```

离线模式会使用 `data/samples/stocks.json`，适合确认安装、界面和模拟盘逻辑能跑通。

也可以使用一键入口：

```powershell
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12
```

## 5. 检查 LLM 模型

配置 `LLM_BASE_URL` 和 `LLM_API_KEY` 后，先查看模型列表：

```powershell
python -m astock_agent_system.cli bench --list-models
```

再选一个便宜或轻量模型做单模型测试：

```powershell
python -m astock_agent_system.cli bench --models "gpt-5.4-mini" --limit 1
```

等价的一键入口：

```powershell
.\start.bat -Mode bench
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
```

如果返回 `status: ok`，说明模型调用可用。若返回 `partial` 或 `error`，请看输出里的 `next_steps`。

## 6. 在线运行自动投资

在线模式不加 `--offline`：

```powershell
python -m astock_agent_system.cli scheduler run-auto-investment --models "rule-baseline,gpt-5.4-mini" --max-count 3 --days 24
```

等价的一键入口：

```powershell
.\start.bat -Mode online -Models "rule-baseline,gpt-5.4-mini" -MaxCount 3 -Days 24
```

说明：

- `rule-baseline` 是规则基线账户，不依赖 LLM。
- 每个 LLM 模型会拥有独立虚拟账户。
- 同一交易日重复运行时，系统会读取已有快照并跳过重复交易，避免同一天重复买入。
- 结果会写入 MongoDB，Streamlit 看板可以读取。

## 7. 启动 Streamlit 观测看板

```powershell
streamlit run src/astock_agent_system/ui/streamlit_app.py
```

等价的一键入口：

```powershell
.\start.bat -Mode dashboard
```

打开后重点看“观测看板”：

- 模型账户排行榜：哪个模型的虚拟账户收益更好。
- 当前持仓：股票代码、股数、当前价、浮动盈亏。
- 执行状态：当天是否已经执行，是否因幂等保护跳过。
- 潜力股票：候选股票、动作、系统把握、舆情评分、风控评分。

## 8. 启动长期调度器

确认 `.env` 的调度配置：

```env
SCHEDULER_DAILY_RUN_TIME=15:05
STOP_LOSS_INTERVAL_MINUTES=5
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini
```

启动：

```powershell
python -m astock_agent_system.cli scheduler start
```

调度器会在交易日指定时间运行自动投资轮次，并按间隔检查止损。

## 9. 常见问题

### bench 能列出模型，但单模型测试失败

常见原因：模型无权限、网关限流、模型不支持当前 profile。建议：

```powershell
python -m astock_agent_system.cli bench --models "your-model-id" --limit 1
```

并尝试：

```env
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
```

### Docker 连接失败

先确认 Docker Desktop 已启动，再运行：

```powershell
docker compose up -d
python -m astock_agent_system.cli storage status --strict
```

### 看板没有 LLM 元素

先确认 LLM 配置和 bench：

```powershell
python -m astock_agent_system.cli config
python -m astock_agent_system.cli bench --list-models
```

然后在看板的“LLM / 模型”页获取模型列表，或在“观测看板”运行一次自动投资轮次。
