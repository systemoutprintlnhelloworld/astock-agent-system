# 数据源 Provider 接入说明

更新时间：2026-06-07

本文说明 `DataAgent` 如何接入 A 股和参考市场数据源。当前系统仍只做模拟盘；数据源只影响分析输入，不会触发真实下单。

## 1. Provider chain

在线模式下，`DataAgent` 会按 `DATA_PROVIDER_CHAIN` 或 `config/config.yaml` 的 `data.provider_chain` 依次尝试数据源，最后降级到 `data/samples/stocks.json` 离线样例。

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
| AData | 否 | 股票池、历史K线、报价 | 无 | 第三方包 API 差异较大，作为手动可选源。 |
| OpenBB | 否 | 历史K线、报价 | 通常无 | 更适合全球市场/宏观/港美股参考，依赖较重。 |
| yfinance | 否 | 历史K线、报价 | 无 | 适合海外/港股或 Yahoo 映射代码参考；A 股覆盖不稳定。 |
| Alpha Vantage | 否 | 历史K线、报价 | `ALPHA_VANTAGE_API_KEY` | 全球参考源，免费额度和 A 股覆盖有限；A 股后缀映射仅 best-effort，失败会继续降级。 |
| JQData / 聚宽 | 否 | 股票池、历史K线、报价 | `JQDATA_USERNAME` / `JQDATA_PASSWORD` | 需要用户本地授权账号。 |
| AAStock | 否 | 港股新闻参考 | 无 | 当前不做未授权网页抓取，不直接适配 A 股行情模型。 |
| 同花顺 Skill | 否 | 人工研究流程 / 合规插件候选 | 无 | 当前不做未授权抓取，也不接入真实交易。 |

## 3. 安全与降级规则

- 真实 token、API key、JQData 密码只允许放在本地 `.env` 或 shell 环境中。
- `/api/config` 只返回 `has_*` 布尔值，不返回密钥原文。
- `/api/data/providers` 返回 provider chain、能力、缺失凭证和最近尝试结果，便于 GUI/TUI 诊断。
- 任一 provider 初始化、限流、字段变化或网络失败时，`DataAgent` 继续尝试下一个 provider。
- 在线 provider 的 `universe/history/financial/quote` 调用受 `DATA_PROVIDER_TIMEOUT_SECONDS` 硬超时保护，默认 15 秒；超时后会记录 error、进入本轮 cooldown，并继续降级，避免 CLI 或后端长时间卡住。
- Baostock 登录时第三方库可能打印 `login success!`；适配器已捕获 stdout，避免污染 `datasource test --format json` 输出。
- AkShare 依赖公开网页源，可能出现 empty、远端断连或超时；这些会作为诊断结果返回，不代表离线 fallback 成功就是 AkShare 成功。
- 离线样例始终是最后兜底，保证无密钥环境可运行。

## 4. 开发约定

新增 provider 时：

1. 在 `src/astock_agent_system/data/providers/` 下新增适配器。
2. 尽量实现 `get_universe`、`get_history`、`get_quote`，如可行再实现 `get_financial`。
3. 在 `src/astock_agent_system/data/data_agent.py` 的 `PROVIDER_CATALOG` 注册能力、凭证字段和限制。
4. 保持懒加载和异常保护，不把第三方依赖变成必装依赖。
5. 增加单元测试验证 provider chain、脱敏和 offline fallback。

## 5. 诊断入口

启动后端后可检查：

```powershell
Invoke-RestMethod http://127.0.0.1:18080/api/data/providers
```

也可以不启动后端直接用 CLI 做逐源 smoke：

```powershell
python -m astock_agent_system.cli datasource test --sources baostock,akshare --stock-code 600519 --days 5 --checks history --timeout-seconds 10 --format json
```

`datasource test` 的结果只按目标 provider 本身的尝试判断成功与否；即使离线样例兜底拿到了数据，也不会把该 provider 误标为 `ok`。

返回结果会包含：

- `provider_chain`：规范化后的在线降级顺序。
- `catalog`：每个数据源的能力、是否配置、是否缺少凭证、是否有适配器。
- `attempts`：本进程最近的 provider 尝试记录。

这些信息可直接供 GUI/TUI 展示，帮助判断某轮分析实际用了哪个数据源。
