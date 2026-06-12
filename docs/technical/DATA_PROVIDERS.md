# 数据源 Provider 接入说明

更新时间：2026-06-11

本文说明 `DataAgent` 如何接入 A 股和参考市场数据源。当前系统仍只做模拟盘；数据源只影响分析输入，不会触发真实下单。

## 1. Provider chain

在线模式下，`DataAgent` 会按 `DATA_PROVIDER_CHAIN` 或 `config/config.yaml` 的 `data.provider_chain` 依次尝试数据源，最后降级到 `data/samples/stocks.json` 离线样例。

### 2026-06-12 iFinD / iWencai update

- iFinD / 同花顺 QuantAPI HTTP provider 使用官方 HTTP base URL `https://quantapi.51ifind.com/api/v1`。
- A 股日线历史行情走 THS_HQ HTTP 服务 `cmd_history_quotation`，请求字段为 `codes`、`indicators`、`startdate`、`enddate`、`functionpara`，不再把历史行情误走 `date_sequence`。
- 实时报价走 THS_RQ HTTP 服务 `real_time_quotation`，失败时再回退到最近历史行情构造保守 quote。
- token 通过环境变量或 `data/runtime/settings.override.json` 读取，运行日志会脱敏 `access_token` / `refresh_token`。
- iWencai SkillHub 当前作为公告/问财技能层配置项接入：`IWENCAI_BASE_URL`、`IWENCAI_API_KEY`、`IWENCAI_SKILLHUB_CLI`。CLI 提供 `datasource iwencai-status`、`datasource configure-iwencai` 和 `datasource iwencai-search`；后者会尝试本机 SkillHub 的 `announcement-search` 技能，并在缺 CLI/key/技能时返回结构化 `skipped/error` 诊断。官方安装器生成的命令名是 `iwencai-skillhub-cli`；Windows 若只装在 WSL，状态页会以 `skillhub_bridge=wsl` 标明桥接；外部 CLI/WSL 探测统一使用容错解码，避免非 UTF-8 安装输出触发 `UnicodeDecodeError`。
- 若 SkillHub CLI 未安装，诊断会显示 `skillhub_found=false` 并提示安装 `announcement-search`；这不是行情 provider chain 的成功源，不会伪装成已接通行情。项目本地技能目录建议使用 Git 忽略的 `data/runtime/skillhub/skills`。

默认链路：

```text
Tushare -> Baostock -> AkShare -> offline samples
```

示例 `.env`：

```env
DATA_MODE=online
DATA_PROVIDER_CHAIN=tushare,baostock,akshare
TUSHARE_TOKEN=your-tushare-token
```

可选参考源可手动加入链路，例如：

```env
DATA_PROVIDER_CHAIN=tushare,baostock,akshare,yfinance,alpha-vantage
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
```

## 2. 当前适配状态

| 来源 | 默认链路 | 能力 | 凭证 | 适配判断 |
| --- | --- | --- | --- | --- |
| Tushare Pro | 是 | 股票池、历史K线、财务、报价 | `TUSHARE_TOKEN` | A 股主数据源。 |
| Baostock | 是 | 股票池、历史K线、报价、保守财务占位 | 无 | 免费 A 股历史行情补充源；财务指标不足，`financial` 只生成 PE/PB/ROE 为 0 的保守占位。 |
| AkShare | 是 | 股票池、历史K线、财务、报价 | 无 | 免费综合兜底源；网页字段可能变化。 |
| AData | 否 | 股票池、历史K线、报价 | 无 | 第三方包 API 差异较大，当前环境下可用但部分行情接口可能返回空；更适合作为手动可选/参考源。 |
| OpenBB | 否 | 历史K线、报价 | 通常无 | 更适合全球市场/宏观/港美股参考，依赖较重。 |
| yfinance | 否 | 历史K线、报价 | 无 | 适合海外/港股或 Yahoo 映射代码参考；A 股覆盖不稳定。 |
| Alpha Vantage | 否 | 历史K线、报价 | `ALPHA_VANTAGE_API_KEY` | 全球参考源，免费额度和 A 股覆盖有限；A 股后缀映射仅 best-effort，失败会继续降级。 |
| JQData / 聚宽 | 否 | 股票池、历史K线、报价、保守财务占位 | `JQDATA_USERNAME` / `JQDATA_PASSWORD` | 需要用户本地授权账号。 |
| iFinD / 同花顺 QuantAPI | 否 | 历史K线、报价 | `IFIND_ACCESS_TOKEN` / `IFIND_BASE_URL` | 推荐通过 `datasource configure-ifind` 隐藏输入保存；HTTP 路线当前优先覆盖 history/quote，权限不足时继续降级。 |
| AAStock | 否 | 港股新闻参考 | 无 | 当前不做未授权网页抓取，不直接适配 A 股行情模型。 |
| 同花顺 Skill | 否 | 人工研究流程 / 合规插件候选 | 无 | 当前不做未授权抓取，也不接入真实交易。 |

## 3. 本地 SQLite “撸数据”首版

本轮新增 `src/astock_agent_system/data/local_store.py`，提供 SQLite-backed 本地市场数据仓库。默认路径：

```text
data/market_local/market.sqlite
```

该目录已加入 `.gitignore`，只作为用户本机运行态数据，不提交到仓库。

在线模式下 `DataAgent` 的读取顺序变为：

1. 进程内内存缓存。
2. 本地 SQLite 市场库（`datasource sync-local` 写入）。
3. 本地文件缓存 `data/market_cache/`。
4. provider chain。
5. 离线样例兜底。

同步命令示例：

```powershell
python -m astock_agent_system.cli datasource sync-local --sources tushare,baostock,akshare --max-stocks 200 --days 365 --checks universe,history,quote,financial --format json
python -m astock_agent_system.cli datasource local-status --format text
```

交互式 CLI 的“本地数据同步”二级页也提供“查看本地市场数据状态”，会展示 SQLite 库存量、最近同步时间和最近同步记录。`sync-local` 支持 `--provider-strategy fill-gaps|all-providers`：前者用于日常补齐，后者用于确认每个 provider 是否真实参与。

安全边界：

- 同步时使用 `DataAgent(use_local_store=False)`，避免把旧本地库误当作新 provider 结果写回自己。
- 只在 provider 真正成功时写库；`offline`、`cache`、`file_cache`、`local_market` 不会被计为可同步来源。
- Tushare / JQData / iFinD 凭证仍必须来自本地 `.env` 或 Git 忽略的 `data/runtime/settings.override.json`。

## 4. 安全与降级规则

- 真实 token、API key、JQData 密码只允许放在本地 `.env` 或 shell 环境中。
- `/api/config` 只返回 `has_*` 布尔值，不返回密钥原文。
- `/api/data/providers` 返回 provider chain、能力、缺失凭证和最近尝试结果，便于 GUI/TUI 诊断。
- `datasource status` 也会显示 `dependency_installed`，帮助区分“未安装”“缺凭证”和“外部服务空返回”。
- 任一 provider 初始化、限流、字段变化或网络失败时，`DataAgent` 继续尝试下一个 provider。
- 在线 provider 的 `universe/history/financial/quote` 调用受 `DATA_PROVIDER_TIMEOUT_SECONDS` 硬超时保护，默认 15 秒；超时后会记录 error、进入本轮 cooldown，并继续降级，避免 CLI 或后端长时间卡住。
- iFinD / 同花顺 QuantAPI 可通过 `IFIND_BASE_URL` 覆盖 HTTP base URL，默认 `https://quantapi.51ifind.com/api/v1`。诊断会尝试 `600519`、`000001`、`600036` 以及 `600519.SH`、`SH600519`、`600519.SS` 等常见格式；若矩阵全失败，优先按中文诊断排查 token 权限、接口开通、base URL 和网络超时，而不是只怀疑单只股票代码不存在。
- Baostock 登录时第三方库可能打印 `login success!`；适配器已捕获 stdout，避免污染 `datasource test --format json` 输出。
- AkShare 依赖公开网页源，可能出现 empty、远端断连或超时；这些会作为诊断结果返回，不代表离线 fallback 成功就是 AkShare 成功。
- AData 2.9.5 在当前环境下可安装，但 `stock.market.get_market()` / `list_market_current()` 仍可能返回空表；如需要更稳定的可选源，可先把它视为参考源，再根据本机网络条件或代理进行调整。
- 离线样例始终是最后兜底，保证无密钥环境可运行。

## 5. 外部项目调研结论

本轮用 smart-search 对高星/活跃 A 股量化项目做了快速调研，证据保存在 `docs/trellis/research_a_share_sources.json`、`docs/trellis/research_akshare.md`、`docs/trellis/research_qlib.md`、`docs/trellis/research_vnpy.md` 和 `docs/trellis/research_adata.md`。

- `akfamily/akshare`、`waditu/tushare`、`1nchaos/adata` 更偏数据源/数据工具；它们很多接口来自公开网页或平台授权，运行时受网络、反爬、字段变化和额度影响。
- `microsoft/qlib`、`vnpy/vnpy` 更偏研究/交易框架，通常需要先把数据接入本地数据目录或数据库；不是把公网实时网页接口直接当作唯一运行依赖。
- 因此本项目不应把某个公网源一次断连解读成“系统全坏”，而应保留 provider catalog、逐源 smoke、hard timeout、source cooldown、本地样例兜底和后续本地缓存/数据库化路线。

## 6. 开发约定

新增 provider 时：

1. 在 `src/astock_agent_system/data/providers/` 下新增适配器。
2. 尽量实现 `get_universe`、`get_history`、`get_quote`，如可行再实现 `get_financial`。
3. 在 `src/astock_agent_system/data/data_agent.py` 的 `PROVIDER_CATALOG` 注册能力、凭证字段和限制。
4. 保持懒加载和异常保护，不把第三方依赖变成必装依赖。
5. 增加单元测试验证 provider chain、脱敏和 offline fallback。

对于 JQData 本地凭证，推荐使用 CLI：

```powershell
python -m astock_agent_system.cli datasource configure-jqdata
```

该命令会通过隐藏输入把用户名/密码写入 `data/runtime/settings.override.json`，不会回显密码，也不会把密钥提交到 Git。

## 7. 诊断入口

启动后端后可检查：

```powershell
Invoke-RestMethod http://127.0.0.1:18080/api/data/providers
```

也可以不启动后端直接用 CLI 做逐源 smoke：

```powershell
python -m astock_agent_system.cli datasource test --sources baostock,akshare --stock-code 600519 --days 5 --checks history --timeout-seconds 10 --format json
python -m astock_agent_system.cli datasource test --sources ifind --stock-code 600519 --days 5 --checks history,quote --timeout-seconds 12 --format text
```

`datasource test` 的结果只按目标 provider 本身的尝试判断成功与否；即使离线样例兜底拿到了数据，也不会把该 provider 误标为 `ok`。

返回结果会包含：

- `provider_chain`：规范化后的在线降级顺序。
- `catalog`：每个数据源的能力、是否配置、是否缺少凭证、是否有适配器。
- `attempts`：本进程最近的 provider 尝试记录。

这些信息可直接供 GUI/TUI 展示，帮助判断某轮分析实际用了哪个数据源。

## 8. 同花顺 iWencai / SkillHub 边界

用户若本机已有 iWencai SkillHub，可按官方方式安装 `announcement-search` 等技能，并把 `IWENCAI_BASE_URL`、`IWENCAI_API_KEY` 放在本地 shell profile、工具自身配置或 Git 忽略的 `data/runtime/settings.override.json` 中。仓库内只记录占位符和使用边界：

```powershell
# 示例占位，不要提交真实 key
$env:IWENCAI_BASE_URL="https://openapi.iwencai.com"
$env:IWENCAI_API_KEY="your-iwencai-api-key"
```

当前 `ths_skill` 在 provider catalog 中仍是“人工研究流程 / 合规插件候选”，不进入行情 provider chain，也不替代 iFinD QuantAPI 的 `history/quote` HTTP 适配器。代码中 `IwencaiSkillHub` 是公告/研究信源 adapter，只在本机 SkillHub CLI 和 `IWENCAI_API_KEY` 可用时调用 `announcement-search`；失败时必须返回 `skipped` / `error` 和 next steps，不能把失败当作行情 provider 成功。

可验证命令：

```powershell
python -m astock_agent_system.cli datasource iwencai-status --format json
python -m astock_agent_system.cli datasource iwencai-search --stock-code 600519 --query "公告" --format json
```

若本机官方安装器下载返回 403 或 curl 56，则先保留诊断状态，待网络/权限恢复后再安装 SkillHub 并执行：

```powershell
iwencai-skillhub-cli install announcement-search
iwencai-skillhub-cli --dir data/runtime/skillhub/skills install announcement-search --force
```
