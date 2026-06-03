# 交付总结

生成时间：2026-06-03

本项目当前已交付为一个可本地运行、可在线接入、可用 Git/GitHub 托管的 A 股 LLM 多 Agent 模拟盘自动投资系统。

> 重要：系统仍是模拟盘，不会真实下单，也不构成投资建议。

## 1. 已可直接使用的能力

- 离线样例数据运行：无密钥时也能验证主流程。
- 在线数据接入：支持 Tushare、AkShare，并保留离线兜底。
- LLM 模型 bench：支持 `bench` 和兼容旧命令 `bench-models`。
- 多模型虚拟账户：每个 LLM/规则模型独立管理一个模拟账户。
- 自动投资轮次：可手动运行，也可由调度器定时运行。
- 风控止损检查：可读取持仓快照并执行模拟强制卖出。
- 同一交易日幂等保护：避免重复运行导致重复买入。
- MongoDB/Redis：可持久化交易、决策、持仓快照和排行榜。
- Streamlit 观测看板：可查看排行榜、持仓、盈亏、潜力股票、舆情和风险摘要。
- Git/GitHub 文档托管：已准备 README 和 docs 文档体系。

## 2. 最短运行路径

### 离线验证

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
docker compose up -d
python -m astock_agent_system.cli storage status --strict
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12
streamlit run src/astock_agent_system/ui/streamlit_app.py
```

### 在线验证

先复制并编辑 `.env`：

```powershell
Copy-Item .env.example .env
```

确认 `.env` 至少包含：

```env
DATA_MODE=online
TUSHARE_TOKEN=your-tushare-token
LLM_BASE_URL=https://your-gateway.example/v1
LLM_API_KEY=your-api-key
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini
```

然后运行：

```powershell
python -m astock_agent_system.cli config
python -m astock_agent_system.cli bench --list-models
python -m astock_agent_system.cli bench --models "gpt-5.4-mini" --limit 1
python -m astock_agent_system.cli scheduler run-auto-investment --models "rule-baseline,gpt-5.4-mini" --max-count 3 --days 24
```

## 3. 当前验证状态

最近一次本地验证结果：

- Python 测试：`33 passed`
- `bench --help`：通过
- `bench-models --help`：通过
- `storage status --strict`：MongoDB/Redis 通过
- 离线自动投资 smoke：通过
- Git ignore 检查：`.env` 和运行产物已忽略
- 文档/代码密钥扫描：未发现真实密钥或真实网关地址

## 4. 当前外部服务状态

在线 LLM 网关当前返回 `SUBSCRIPTION_OUT_OF_WINDOW`，表示订阅处于每日可用窗口之外。系统已经能识别该错误并输出 `next_steps`。

这不是本地代码失败。可选处理方式：

1. 等待网关每日可用窗口开启后重试。
2. 换一个当前可用的 LLM key 或模型。
3. 暂时使用 `rule-baseline` 规则账户继续运行模拟盘。

## 5. 文档入口

- [使用者手册](USER_GUIDE.md)
- [在线运行手册](ONLINE_RUNBOOK.md)
- [开发者手册](DEVELOPER_GUIDE.md)
- [GitHub 发布说明](GITHUB_PUBLISHING.md)
- [项目进度报告](../PROGRESS_REPORT.md)

## 6. 后续可选增强

这些不是当前交付阻塞项，但可以继续迭代：

- 增加收益曲线和自动投资时间线。
- 增加长期模型排行榜和多日回放。
- 增加 FastAPI/React 独立 Dashboard。
- 增加更真实的撮合、滑点和成交模型。
- 半自动或实盘交易前增加人工确认、审计日志和熔断机制。

