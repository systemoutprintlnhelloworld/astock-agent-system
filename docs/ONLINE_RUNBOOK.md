# 在线运行手册

本手册用于把系统从离线样例模式切到在线模拟盘模式。在线模式会读取真实数据源、调用 LLM 网关，并把模拟交易结果写入 MongoDB。

## 1. 在线模式需要什么

必需项：

- Docker Desktop：用于 MongoDB 和 Redis。
- Tushare token：用于在线 A 股主数据源。
- OpenAI-compatible LLM 网关：用于模型 bench 和 LLM 决策。

可选项：

- Baostock / AkShare：免费 A 股补充源，可安装 `.[market]` 后作为降级链使用。
- yfinance：无鉴权参考行情源，可用于 Yahoo A 股映射代码的 history/quote 兜底。
- AData：无鉴权参考源；当前环境下包可安装，但部分公开行情接口可能返回空。
- Alpha Vantage / JQData：只有在用户本地维护相应凭证时才启用。

建议把本地 `.env` 中的 `LLM_DEFAULT_MODEL` 指向你当前可用的在线模型（例如本机网关中的 `gpt-5.5`），这样 CLI 和 TUI 会优先使用本地默认模型跑在线链路；`rule-baseline` 仅作为可选回退，不再作为主验证路径。

## 2. `.env` 推荐配置

复制：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，示例：

```env
DATA_MODE=online
DATA_PROVIDER_CHAIN=tushare,baostock,akshare
TUSHARE_TOKEN=your-tushare-token
ALPHA_VANTAGE_API_KEY=
JQDATA_USERNAME=
JQDATA_PASSWORD=

LLM_BASE_URL=https://your-gateway.example/v1
LLM_API_KEY=your-api-key
LLM_DEFAULT_MODEL=
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3

MONGO_URI=mongodb://localhost:27017
MONGO_DB=astock_agent_system
MONGO_TIMEOUT_MS=3000
REDIS_URL=redis://localhost:6379/0

SCHEDULER_MODELS=gpt-5.5
SCHEDULER_DAILY_RUN_TIME=15:05
STOP_LOSS_INTERVAL_MINUTES=5
```

注意：

- `LLM_BASE_URL` 通常要带 `/v1`。
- `DATA_PROVIDER_CHAIN` 控制在线数据源降级顺序；离线样例始终是最后兜底。
- `.env` 不要提交到 GitHub。
- CLI `config` 只显示是否存在 key，不显示完整 key。
- JQData 也可不用手写 `.env`，通过 `python -m astock_agent_system.cli datasource configure-jqdata` 隐藏输入后保存到 Git 忽略的 `data/runtime/settings.override.json`。

## 3. 启动存储服务

推荐一键入口：

```powershell
.\start.bat -Mode storage
```

等价 CLI：

```powershell
docker compose up -d
python -m astock_agent_system.cli storage status --strict
```

通过标准：MongoDB 和 Redis 都显示 `connection: ok`。

## 4. 检查有效配置

```powershell
python -m astock_agent_system.cli config
```

重点确认：

- `data_mode` 是 `online`。
- `data.provider_chain` 包含期望的数据源顺序。
- `llm.has_api_key` 是 `true`。
- `llm.base_url` 是你的网关地址。
- `scheduler.models` 包含你要比赛的模型账户。

## 5. LLM 在线 smoke

推荐一键入口：

```powershell
.\start.bat -Mode bench
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
```

等价 CLI：

先获取模型列表：

```powershell
python -m astock_agent_system.cli bench --list-models
```

再选一个模型做单模型 JSON 测试：

```powershell
python -m astock_agent_system.cli bench --models "gpt-5.4-mini" --limit 1
```

返回状态含义：

- `ok`：所测模型全部可用。
- `partial`：部分模型成功，部分失败；查看 `results` 和 `next_steps`。
- `error`：全部失败；常见原因是权限、限流、profile 不兼容或 base URL 缺少 `/v1`。
- `skipped`：未配置 API key 或未选到模型。

遇到 429：降低 `--limit`，等待后重试，或改用更小模型。

## 6. 在线数据 smoke

在线筛选候选股票：

```powershell
python -m astock_agent_system.cli screen --max-count 3 --days 24
```

在线每日分析：

```powershell
python -m astock_agent_system.cli run-daily --max-count 3 --days 24
```

如果 Tushare/Baostock/AkShare 暂时失败，`DataAgent` 会按 provider chain 尝试降级到可用数据源，最终回到离线样例。
在线 provider 失败不会再因为离线样例缺少某只在线股票而抛 `KeyError`；未知股票会生成保守空占位，筛选器会跳过空行情或零价格数据。
`datasource test` 现在支持 `--timeout-seconds`，可以对每个 provider/check 设置硬超时，避免 AkShare 这类免费网页源把诊断命令卡住：

```powershell
python -m astock_agent_system.cli datasource test --sources baostock,akshare --stock-code 600519 --days 5 --checks history --timeout-seconds 10 --format json
```

逐源定位时建议分开测试，避免一个公网源的超时掩盖另一个源的可用性：

```powershell
python -m astock_agent_system.cli datasource test --sources baostock --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json
python -m astock_agent_system.cli datasource test --sources yfinance --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json
python -m astock_agent_system.cli datasource test --sources jqdata --stock-code 600519 --days 5 --checks history,quote,financial --timeout-seconds 12 --format json
```

验证结果说明：

- Baostock 当前可作为无鉴权历史行情补充源使用，JSON 输出不会被 `login success!` 污染。
- yfinance 当前可作为无鉴权参考 history/quote 源，但 `financial` 不在能力列表内，会明确标记为 skipped。
- AkShare 在当前网络环境下可能返回 empty、断连或超时；这属于外部服务状态，不再让 CLI 无限等待。
- AData 包可安装，但当前网络/公开接口下可能返回空表；若 `datasource test` 显示 AData error/empty，优先使用 Baostock、yfinance 或 JQData，不把它放入主链前列。
- JQData 未配置时会明确返回 `skipped` / `missing credentials`；配置后再加入 provider chain 验证。
- Tushare 频率限制仍由你本地 token 配额决定；当它超限时，系统会继续降级，不会把离线 fallback 误判为已接通的在线源。

数据源诊断接口：

```powershell
Invoke-RestMethod http://127.0.0.1:18080/api/data/providers
```

该接口只返回能力、缺失凭证和最近尝试结果，不返回真实 token、API key 或密码。更多说明见 [数据源 Provider 接入说明](technical/DATA_PROVIDERS.md)。

## 7. 在线自动投资 smoke

推荐一键入口：

```powershell
.\start.bat -Mode online -Models "rule-baseline,gpt-5.4-mini" -MaxCount 3 -Days 24
```

等价 CLI：

```powershell
python -m astock_agent_system.cli scheduler run-auto-investment --models "gpt-5.5" --max-count 3 --days 24
```

通过标准：

- 顶层 `status` 为 `ok`。
- `payload.competition.rankings` 有模型账户排名。
- `payload.competition.persisted.status` 为 `ok`。
- `payload.stop_loss.status` 为 `ok` 或 `alert`。

同一交易日重复运行时，部分账户可能显示 `skipped_execution=true`，这是幂等保护，不是错误。

## 8. 启动看板

推荐一键入口：

```powershell
.\start.bat -Mode dashboard
```

等价命令：

```powershell
streamlit run src/astock_agent_system/ui/streamlit_app.py
```

看板建议顺序：

1. 打开“LLM / 模型”，获取模型列表并运行 bench。
2. 打开“观测看板”，刷新排行榜和持仓。
3. 如无数据，点击运行一次自动投资轮次。

## 9. 启动现代控制台

如果要验证新的现代 UI 链路，可直接一键启动：

```powershell
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
```

启动后打开：

- `http://127.0.0.1:3000`：现代控制台首页。

当前 modern UI 已改为标签页结构：

- `总览`：看连接状态、最近轮次和候选股票预览。
- `流程`：看 React Flow 实时链路和动画边。
- `表现`：看权益曲线和模型排行榜。
- `日志`：看决策卡和事件流。
- `股票`：看持仓、候选池和交易记录。
- `设置`：通过目录快速跳转到数据源、LLM、组合、风控和调度配置。

第一次走在线链路时，建议优先使用 `总览` 页里的：

- `开箱检查清单`：先确认 Token、API Key、模型列表和 WebSocket 是否都已就绪。
- `首次启动向导`：按“数据源 -> LLM -> 保存配置 -> 启动离线轮次”的顺序做首轮联调，再切在线模式。

`start.bat -Mode modern-ui` 现在会先检查前后端端口，并检查同一个 `apps/frontend` 目录下是否已经存在旧的 Next.js dev 进程；如发现冲突，会打印进程信息并在你确认后自动结束该进程。脚本还会等待 `api/health` 可用后再拉起前端，减少“前端已开但后端未接上”的假失败。

本项目的 modern-ui 开发预览默认走 Next.js webpack dev server。若看到 `Turbopack` panic 或错误路径来自其他项目的 `.next-gui` 缓存，通常是其他 Next dev 进程占用了前端端口，而不是 AStock 后端错误；先按脚本提示释放端口，或使用 `-Port 3002` 等空闲端口重新启动。

如只想单独检查 API，也可以：

```powershell
.\start.bat -Mode backend -Port 18080
```

建议优先检查：

- `http://127.0.0.1:18080/api/health`
- `http://127.0.0.1:18080/api/config`
- `http://127.0.0.1:18080/api/agents/flow`
- `http://127.0.0.1:18080/api/decisions`
- `http://127.0.0.1:18080/api/stocks/board`
- `http://127.0.0.1:18080/api/metrics/rankings`
- `ws://127.0.0.1:18080/ws/events`

## 10. 启动长期调度器

确认 smoke 都通过后再启动：

```powershell
.\start.bat -Mode scheduler
```

长期运行时建议保持 Docker Desktop、MongoDB、Redis 和网络稳定。

## 11. 当前在线验证状态

当前本地在线链路已验证：

- `LLM_BASE_URL` 使用带 `/v1` 的 OpenAI-compatible 网关。
- `bench --list-models` 可返回模型列表。
- 本轮主验证路径为本地默认 `LLM_DEFAULT_MODEL=gpt-5.5`：
  `python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 60` 已完成并正常退出。
- CLI 数据源快速 smoke 可区分逐源真实状态：Baostock history 成功；AkShare 在当前网络下可能 empty/断连/超时但不会阻塞；Tushare 当前受本地 token 频率限制影响，由用户自行处理配额。
- 在线自动投资可运行；同一交易日重复运行会触发幂等跳过，避免重复买入。

不同模型仍可能因账户分组、额度或渠道限制失败。遇到模型不可用时，请先换用已 bench 通过的模型；`rule-baseline` 只是诊断回退，不再作为默认在线验证命令。
