# A股 LLM 多 Agent 自动投资系统

这是一个面向模拟盘验证的 A 股多 Agent 自动投资系统。它会动态筛选股票、让多个 LLM/规则账户分别管理独立虚拟资金、自动记录模拟买卖与止损检查，并通过 Streamlit 观测看板展示账户排行榜、持仓涨跌、当前盈亏、潜力股票、舆情与风险摘要。

> 重要：当前只做模拟盘和研究验证，不会真实下单，也不构成任何投资建议。

## 当前能力

- 动态股票筛选，而不是固定股票池。
- 每个 LLM 模型独立管理一个虚拟账户，可做收益排行榜。
- 支持 OpenAI 兼容 LLM 网关、模型 bench 与规则基线账户。
- 支持模拟买入、T+1 卖出限制、手续费/印花税/滑点和强制止损检查。
- 支持同一交易日幂等保护：当天已经运行过的账户会读取已有快照，不会重复买入。
- Streamlit Web UI 已包含“观测看板”“一键分析”“LLM / 模型”“设置”等页面。
- MongoDB/Redis 可通过 Docker 提供持仓快照、交易、决策和排行榜持久化。
- 调度器可每天自动运行一次自动投资轮次，并按间隔执行止损检查。
- 一键启动脚本覆盖离线、在线、bench、看板、调度器和文档预览。
- GitHub Pages 文档站由 GitHub Actions 自动部署。
- 项目级 Cursor Skill 已固化交付规范；自动 Shell 审批 Hook 默认关闭，避免影响开发效率。

## 安全约定

不要把真实 API Key、Tushare Token 或 Webhook 写入仓库。请复制 `.env.example` 到 `.env`，或在 PowerShell 中设置环境变量。

```powershell
$env:LLM_BASE_URL = "https://your-gateway.example/v1"
$env:LLM_API_KEY = "your-api-key"
$env:TUSHARE_TOKEN = "your-token"
```

`.env` 已被忽略，不应提交。`.env.example` 只保留字段名和示例，不放真实密钥。

## 快速开始

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
.\start.bat -Mode status
```

一键入口覆盖常用调试路径：

```powershell
.\start.bat -Mode storage
.\start.bat -Mode offline -MaxCount 1 -Days 12
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
.\start.bat -Mode online -Models "rule-baseline,gpt-5.4-mini" -MaxCount 3 -Days 24
.\start.bat -Mode dashboard
```

如果不使用一键入口，也可以直接调用 CLI：

```powershell
python -m astock_agent_system.cli --help
python -m astock_agent_system.cli config
docker compose up -d
python -m astock_agent_system.cli storage status --strict
python -m astock_agent_system.cli run-daily --offline --max-count 3 --days 24
```

## 文档入口

- 在线文档站（GitHub Pages）：https://systemoutprintlnhelloworld.github.io/astock-agent-system/
- [交付总结](docs/DELIVERY_SUMMARY.md)：当前可用能力、最短运行路径、验证状态和外部服务状态。
- [使用者手册](docs/USER_GUIDE.md)：从安装到看板、自动投资、常见问题。
- [在线运行手册](docs/ONLINE_RUNBOOK.md)：Tushare、LLM、MongoDB/Redis、在线 smoke 顺序。
- [开发者手册](docs/DEVELOPER_GUIDE.md)：架构、模块边界、测试和开发约定。
- [GitHub 发布说明](docs/GITHUB_PUBLISHING.md)：初始化 Git、创建远程仓库、推送和文档托管。

本地预览文档站：

```powershell
python -m pip install -e ".[docs]"
.\start.bat -Mode docs
```

## Streamlit 观测看板

启动 Web UI：

```powershell
streamlit run src/astock_agent_system/ui/streamlit_app.py
```

重点查看“观测看板”页：

- LLM 模型账户排行榜。
- 当前持仓、当前价、浮动盈亏和总权益。
- 当天是否已执行；若同一交易日重复运行，会显示“已跳过”以避免重复交易。
- 潜力股票、模型动作、系统把握、舆情评分、风控评分和主要理由/风险。

## 自动投资轮次

手动运行一次自动投资轮次：

```powershell
python -m astock_agent_system.cli scheduler run-auto-investment --offline --models "rule-baseline,gpt-5.4-mini,codex-auto-review" --max-count 1 --days 12
```

说明：

- `--offline` 强制使用本地样例数据，适合 smoke test。
- `--models` 是本次运行的模型账户列表。留空时会读取 `SCHEDULER_MODELS` / `config/config.yaml` 中的默认模型列表；如果仍为空，则回退到默认模型或规则基线。
- `--max-count` 控制候选股票数量。
- `--days` 控制历史窗口。
- 运行结果会包含排行榜、每个账户的模拟交易、持仓快照和止损检查结果。

启动长期调度器：

```powershell
python -m astock_agent_system.cli scheduler start
```

调度器会在交易日的 `SCHEDULER_DAILY_RUN_TIME` 执行自动投资轮次，并按 `STOP_LOSS_INTERVAL_MINUTES` 执行止损检查。

## 调度器模型配置

可在 `.env` 中配置每天自动投资要使用的模型账户：

```env
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini,codex-auto-review
```

也可以在 `config/config.yaml` 中配置：

```yaml
scheduler:
  models:
    - rule-baseline
    - gpt-5.4-mini
    - codex-auto-review
```

`.env` 中的 `SCHEDULER_MODELS` 优先级高于 YAML 配置。建议先包含 `rule-baseline`，这样即使 LLM 网关暂时不可用，也能保留一个可比较的规则基线账户。

## LLM 模型 bench

配置好 `LLM_BASE_URL` 和 `LLM_API_KEY` 后，可以运行模型 bench 对比网关中的多个模型。具体参数以 CLI 帮助为准：

```powershell
python -m astock_agent_system.cli bench --help
python -m astock_agent_system.cli bench --list-models
python -m astock_agent_system.cli bench --models "gpt-5.4-mini" --limit 1
```

LLM 请求支持多种 OpenAI/Claude 兼容 profile，并可用 `LLM_REQUEST_PROFILE=auto` 自动尝试。

## 目录结构

```text
config/                       # 安全默认配置
data/samples/                 # 离线样例数据
src/astock_agent_system/      # Python 源码
  agents/                     # 多 Agent 模块
  backtest/                   # 模拟盘和回测
  data/                       # 数据源适配器
  llm/                        # LLM 客户端与模型 bench
  orchestrator/                # 多模型自动投资编排器
  scheduler/                   # 自动投资和止损调度器
  storage/                     # MongoDB/Redis 持久化
  ui/                         # Streamlit UI
tests/                        # 自动化测试
reports/                      # 运行报告输出，默认不提交
```

## 常用验证命令

```powershell
python -m pytest
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
python -m mkdocs build --strict
```

## 免责声明

本项目仅用于学习、研究和模拟盘验证，不构成任何投资建议。投资有风险，实盘前请至少完成长期模拟盘验证并自行承担决策责任。
