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

## 8. 启动现代控制台

当前已经提供首版 Next.js 现代控制台，可直接联动 FastAPI 后端查看流程图、实时事件流、可折叠决策日志、股票看板、排行榜和长期曲线：

```powershell
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 8000
```

启动后打开：

- `http://127.0.0.1:3000`：现代控制台首页。

新版控制台已经改成标签页布局，建议按这个顺序使用：

- `总览`：先确认后端连接、最近轮次和模型排行榜预览。
- `流程`：观察多 Agent 流程图、节点状态和动画箭头。
- `日志`：看可折叠决策卡和实时事件流。
- `股票`：切换当前持仓、候选股票和交易记录。
- `设置`：通过左侧目录快速跳转到数据源、LLM、组合、风控和调度配置。

如果你是第一次上手，建议先看 `总览` 页里的：

- `开箱检查清单`：确认后端、WebSocket、Tushare Token、API Key 和比赛模型是否已经准备好。
- `首次启动向导`：按“数据源 -> LLM -> 保存配置 -> 启动离线轮次”的顺序一步步完成首轮验证。

如果前端或后端端口已经被其他程序占用，或者同一个 `apps/frontend` 目录下已经有旧的 Next.js dev 进程在运行，`start.bat -Mode modern-ui` 现在会：

1. 在命令行里显示占用该端口的 PID、进程名、路径和命令行。
2. 询问你是否要终止该进程。
3. 在确认后自动释放端口，再继续拉起后端和前端。

此外，一键启动会先等待后端健康检查通过，再启动前端，避免出现“前端先打开但后端还没接上”的情况。

如果只想单独检查后端接口，也可以单独启动：

```powershell
.\start.bat -Mode backend -Port 8000
```

启动后可访问：

- `http://127.0.0.1:8000/api/health`：健康检查。
- `http://127.0.0.1:8000/api/config`：脱敏后的当前配置。
- `http://127.0.0.1:8000/api/agents/flow`：前端流程图节点和动画边。
- `http://127.0.0.1:8000/api/decisions`：结构化决策日志。
- `http://127.0.0.1:8000/api/stocks/board`：持仓、候选股和交易记录。
- `http://127.0.0.1:8000/api/metrics/rankings`：模型排行榜。
- `ws://127.0.0.1:8000/ws/events`：实时事件 WebSocket。

注意：这里仍是模拟盘适配层，不会真实下单；返回配置时只显示 `has_api_key`、`has_tushare_token` 等布尔状态，不返回真实密钥。

## 9. 启动长期调度器

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

## 10. 常见问题

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
