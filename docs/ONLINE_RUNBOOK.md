# 在线运行手册

本手册用于把系统从离线样例模式切到在线模拟盘模式。在线模式会读取真实数据源、调用 LLM 网关，并把模拟交易结果写入 MongoDB。

## 2026-06-12 更新：iFinD/iWencai 与运行可观察性

- 推荐日常入口仍是 `python -m astock_agent_system.cli`，数据源页面新增 iWencai SkillHub 配置/状态入口，API key 通过隐藏输入保存到 `data/runtime/settings.override.json`（Git 忽略）。
- iWencai SkillHub 现提供明确的公告信源诊断命令：`datasource iwencai-status` 查看本机 CLI/API key/必需技能状态，`datasource iwencai-search --stock-code 600519 --query 公告` 尝试调用本机 `announcement-search` 技能；官方安装器实际生成的命令名是 `iwencai-skillhub-cli`，Windows 侧若只在 WSL 中安装，状态页会显示 `skillhub_bridge=wsl`；未安装 CLI 或未配置 key 时返回 `skipped` 和 next steps，不会伪装成行情数据源成功。
- iFinD HTTP 适配器已按同花顺 QuantAPI 文档改为历史行情 `cmd_history_quotation`、实时行情 `real_time_quotation`，默认 base URL 为 `https://quantapi.51ifind.com/api/v1`。
- `smart-search` 默认开启；如果本地 `.env` 曾写入 `SMART_SEARCH_ENABLED=false`，以交互菜单或 runtime override 为准。
- 前台 Agent 运行会输出 `状态栏 | 模型=... | 阶段=... | 股票=... | 决策=... | 成交=... | 收益=... | 用时=...`，用于替代之前只看最终评分的黑盒体验。
- MongoDB 不可达时不再打印长异常；系统会返回 `E-MONGO-CONNECT`，表示本轮模拟交易已完成，仅跳过排行榜/成交持久化。调试时可使用 `--no-persist`。

## 0. 推荐入口：交互式 CLI

日常测试 Python 后端时优先只运行一个命令：

```powershell
python -m astock_agent_system.cli
```

不带子命令时会进入 `AStock 交互式工作流控制台`。顶层菜单按“先配 LLM、再配数据源、再同步本地库、再运行智能体”的日常路径拆分，降低长命令心智负担：

- **LLM 配置与诊断**：选择 OpenAI-compatible / Anthropic 等请求协议，输入 Base URL 和隐藏 API Key，拉取模型列表后可直接输入编号选择默认模型（回车使用当前/第一个模型，也可手动填写），并用“请解释 A 股是什么”的短问答完成自检；自检失败时拒绝写入本地运行态配置。
- **数据源配置与诊断**：查看 provider chain 状态；配置 Tushare、JQData、iFinD / 同花顺 QuantAPI 等凭证时先做真实自检，通过后才保存到 Git 忽略的本地运行态配置；iFinD 会额外做多股票/多代码格式矩阵诊断，矩阵全失败时输出“鉴权/权限、超时、空返回、base URL/格式”方向的中文诊断。
- **本地数据同步**：将真实 provider-chain 成功返回的股票池、K 线、报价和财务快照同步到本地 SQLite；默认使用 `fill-gaps` 补齐策略，也可用 `all-providers` 观察各数据源参与情况；二级页的“查看本地市场数据状态”会展示 SQLite 库存量、最近同步时间和最近 10 条同步记录。
- **运行工作流**：启动一次 LLM 智能体工作流，或进入连续运行模式直到 `Ctrl+C` / 达到最大轮数；连续运行会先立即执行第 1 轮，之后按交互式配置的间隔倒计时等待；运行结束摘要会展示账户看板、持仓、最近交易和本轮 PnL，并写入脱敏 JSONL 日志和摘要。
- **学习中心**：查看持续学习状态和建议，触发学习分析，浏览经验历史和 Agent 记忆案例。
- **运行日志 / 历史回放**：查看最近运行摘要、事件数量、错误数量和完整 JSONL 日志路径。

顶层仍保留 `0) 快速向导`，用于按“配置 -> 自检 -> 可选同步 -> 可选运行”的顺序完成首轮验证。

交互式入口默认使用本地配置里的 `llm.default_model`，例如你本机网关配置的 `gpt-5.5`；不会把 `rule-baseline` 或 `offline` 当作主运行路径。下面保留的长命令适合自动化、CI、问题定位和精确复现。

## 1. 在线模式需要什么

必需项：

- Docker Desktop：用于 MongoDB 和 Redis。
- Tushare token：用于在线 A 股主数据源。
- OpenAI-compatible LLM 网关：用于模型 bench 和 LLM 决策。

可选项：

- Baostock / AkShare：免费 A 股补充源，可安装 `.[market]` 后作为降级链使用。
- yfinance：无鉴权参考行情源，可用于 Yahoo A 股映射代码的 history/quote 兜底。
- AData：无鉴权参考源；当前环境下包可安装，但部分公开行情接口可能返回空。
- Alpha Vantage / JQData / iFinD：只有在用户本地维护相应凭证时才启用；iFinD / 同花顺 QuantAPI 推荐用隐藏输入配置，不要把 token 写入命令行。

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
IFIND_ACCESS_TOKEN=
IFIND_REFRESH_TOKEN=
IFIND_BASE_URL=https://quantapi.51ifind.com/api/v1

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

SMART_SEARCH_ENABLED=true
SMART_SEARCH_TIMEOUT_SECONDS=60

SCHEDULER_MODELS=gpt-5.5
SCHEDULER_DAILY_RUN_TIME=15:05
STOP_LOSS_INTERVAL_MINUTES=5
```

注意：

- `LLM_BASE_URL` 通常要带 `/v1`。
- `DATA_PROVIDER_CHAIN` 控制在线数据源降级顺序；离线样例始终是最后兜底。
- 在线 provider 返回的 history/quote/financial 会写入本地文件缓存 `data/market_cache/`（Git 忽略），下次同类请求会先读缓存再调用外部 API，以降低 Tushare 等数据源频率压力。
- `.env` 不要提交到 GitHub。
- CLI `config` 只显示是否存在 key，不显示完整 key。
- JQData 也可不用手写 `.env`，通过 `python -m astock_agent_system.cli datasource configure-jqdata` 隐藏输入后保存到 Git 忽略的 `data/runtime/settings.override.json`。
- iFinD / 同花顺 QuantAPI 同理，使用 `python -m astock_agent_system.cli datasource configure-ifind` 隐藏输入 access token / refresh token；不要把 token 粘贴进 PowerShell 参数、文档或提交。
- iWencai / SkillHub 使用 `python -m astock_agent_system.cli datasource configure-iwencai` 隐藏输入 API key；查询公告信源用：

```powershell
python -m astock_agent_system.cli datasource iwencai-status --format json
python -m astock_agent_system.cli datasource iwencai-search --stock-code 600519 --query "公告" --format json
```

如果输出 `SkillHub CLI is not installed or not on PATH` 或 `IWENCAI_API_KEY is not configured`，说明公告信源尚未接通；这不会影响行情 provider chain，但新闻/公告证据块会缺少 iWencai 结果。官方安装器下载成功后，优先执行以下命令安装技能；若希望技能目录落在仓库的 Git 忽略运行态目录，可使用第二条：

```powershell
iwencai-skillhub-cli install announcement-search
iwencai-skillhub-cli --dir data/runtime/skillhub/skills install announcement-search --force
```

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

### 6.1 Provider chain 与本地缓存关系

在线模式的数据读取顺序是：

1. 进程内内存缓存（同一轮运行内避免重复取同一股票）。
2. 本地 SQLite 市场库 `data/market_local/market.sqlite`（由 `datasource sync-local` 批量同步，Git 忽略）。
3. 本地文件缓存 `data/market_cache/`。
4. 配置的 provider chain，例如 `tushare -> baostock -> akshare`。
5. 离线样例兜底。

缓存 TTL：

| 数据类型 | 默认 TTL | 说明 |
| --- | --- | --- |
| history | 7 天 | 用于历史 K 线，减少重复调用 Tushare 历史行情接口。 |
| quote | 5 分钟 | 用于当前报价，保持短周期新鲜度。 |
| financial | 1 天 | 用于估值/财务快照，日内无需反复拉取。 |

该缓存不是替代实时接口，而是外部 API 的本地加速层；缓存过期后会重新走 provider chain。缓存文件属于运行时数据，不应提交到 Git。

SQLite 本地库用于 Tushare 式“先批量下载、再本地查询”的工作流，和 TTL 文件缓存不同：它是显式由用户运行 `datasource sync-local` 写入的本地数据仓库。可用以下环境变量控制：

```powershell
$env:ASTOCK_MARKET_LOCAL_READ="false"   # 临时关闭本地库读取
$env:ASTOCK_MARKET_LOCAL_DB="D:\\market-data\\astock.sqlite"  # 指定自定义库路径
```

### 6.2 在线 smoke 命令

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

`datasource test` 是逐源 smoke 命令，运行时会绕过共享文件缓存 `data/market_cache/`，避免缓存命中把失败 provider 误判为成功；它只用来判断当前 provider 自身是否真实可用。

### 6.3 本地 SQLite “撸数据”

如果你有 Tushare / JQData / iFinD 等额度，建议先用小批量命令把常用股票数据同步到本地 SQLite，减少后续 Agent 运行时的外部 API 压力：

```powershell
python -m astock_agent_system.cli datasource sync-local --sources tushare,baostock,akshare --max-stocks 200 --days 365 --checks universe,history,quote,financial --format json
```

iFinD / 同花顺 QuantAPI 的安全配置与同步示例：

```powershell
python -m astock_agent_system.cli datasource configure-ifind
python -m astock_agent_system.cli datasource sync-local --sources tushare,ifind,baostock --max-stocks 200 --days 365 --checks universe,history,quote,financial --format json
```

调试阶段建议先小批量：

```powershell
python -m astock_agent_system.cli datasource sync-local --sources baostock --max-stocks 5 --days 30 --checks universe,history,quote,financial --format json
```

同步结果会写入 `data/market_local/market.sqlite`，该目录已被 `.gitignore` 忽略。同步命令不会通过参数接收 token，也不会把 `offline`、`cache`、`file_cache` 或 `local_market` 当作真实 provider 成功来源写库。

## 6.4 CLI 客观数据可观察性

为了避免只看到“评分”和“BUY/REJECT”结论，CLI 现在开始提供面向终端的客观数据渲染基础：

- `cli_data_viz.py` 可渲染 ASCII K 线、MA/RSI 等技术指标、财务指标表、公司/报价快照和新闻/舆情摘要。
- `TradeDecision.explanation_data` 会记录本次决策建议展示哪些证据块，例如 `kline`、`financial`、`sentiment`、`risk`。
- `MasterAgent` 会发射更细粒度的协作事件：`technical_analysis_*`、`fundamental_analysis_*`、`sentiment_analysis_*`、`debate_*`、`risk_analysis_*`、`portfolio_decision_*`，终端可以直接看到 `DataAgent -> TechnicalAnalyst -> FundamentalAnalyst -> SentimentAnalyst -> DebateRoom -> RiskManager -> PortfolioManager` 的执行链。
- `agent start` 的默认流式输出已展示公司/行情、ASCII K 线、技术指标、财务估值、数据源调用链、Agent 明细和 PortfolioManager 建议展示的证据块；后续仍需继续补新闻/公告 provider、连续运行累计收益/持仓/下一轮时间看板。

推荐用本地默认在线模型运行一轮可观察性 smoke：

```powershell
python -m astock_agent_system.cli agent start --max-count 1 --days 12 --fresh-start --no-persist --timeout-seconds 120
```

若只是确认渲染链路、不消耗在线模型或外部行情额度，可以临时使用诊断模式：

```powershell
python -m astock_agent_system.cli agent start --offline --max-count 1 --days 5 --fresh-start --no-persist --no-learning --timeout-seconds 30
```

离线诊断模式会跳过在线 LLM 复核，直接使用规则决策兜底，避免本地仍配置 `LLM_DEFAULT_MODEL` 时因为外部网关重试导致 smoke 命令超时。

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
