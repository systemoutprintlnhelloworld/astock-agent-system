# 用户需求映射文档

更新时间：2026-06-05

本文档面向核心开发者，梳理用户操作场景 → 功能设计 → 代码位置的映射关系。

---

## 1. 用户角色定义

### 1.1 角色分类

| 角色 | 特征 | 主要需求 | 技术水平 |
|------|------|---------|---------|
| **小白用户** | 第一次使用，不懂命令行 | 一键启动、可视化配置、透明看懂过程 | 低 |
| **量化研究者** | 有量化经验，想对比LLM | 多模型对比、排行榜、回测数据导出 | 中 |
| **开发者** | 想扩展Agent或接入新数据源 | 架构文档、API文档、代码示例 | 高 |

---

## 2. 小白用户场景

### 2.1 场景：首次启动

**用户需求**：
- 不知道怎么配置
- 不知道从哪里开始

**功能设计**：
1. 一键启动脚本 `start.bat`
2. 首次启动向导（UI中）
3. 开箱检查清单

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 启动脚本 | `start.bat` / `start.ps1` | `-Mode modern-ui` |
| 首次向导 | `apps/frontend/src/components/trading-dashboard.tsx` | `总览` tab |
| 健康检查 | `apps/backend/app.py` | `GET /api/health` |

**用户操作流程**：
```
1. 双击 start.bat
2. 等待启动（自动打开浏览器）
3. 看到总览页 → 开箱检查清单
4. 点击"设置" → 填写 Tushare Token / LLM API Key
5. 回到总览页 → 点击"启动离线轮次"
```

---

### 2.2 场景：配置 LLM

**用户需求**：
- 需要填写 API Key
- 不知道填什么格式

**功能设计**：
1. 设置页 → LLM配置区域
2. 表单验证（URL格式、Key非空）
3. 保存后立即测试连接

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 设置表单 | `apps/frontend/src/components/trading-dashboard.tsx` | `设置` tab → LLM部分 |
| 保存接口 | `apps/backend/app.py` | `POST /api/config/save` |
| 配置加载 | `src/astock_agent_system/config.py` | `load_settings()` |

**用户操作流程**：
```
1. 点击"设置" tab
2. 找到"LLM配置"区域
3. 填写 Base URL（例如：https://api.example.com/v1）
4. 填写 API Key
5. 点击"保存配置"
6. 看到提示："配置已保存并立即生效"
```

---

### 2.3 场景：启动运行

**用户需求**：
- 想看 Agent 在干什么
- 想知道为什么买这只股票

**功能设计**：
1. 总览页 → "启动离线轮次"按钮
2. 流程页 → React Flow 实时显示 Agent 节点状态
3. 日志页 → 可折叠决策卡片

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 启动按钮 | `apps/frontend/src/components/trading-dashboard.tsx` | `总览` tab |
| 运行接口 | `apps/backend/app.py` | `POST /api/run` |
| 流程图 | `apps/frontend/src/components/trading-dashboard.tsx` | `流程` tab + React Flow |
| 决策日志 | `apps/frontend/src/components/trading-dashboard.tsx` | `日志` tab + DecisionCard |
| WebSocket | `apps/backend/app.py` | `WebSocket /ws/events` |

**用户操作流程**：
```
1. 点击"启动离线轮次"
2. 切换到"流程" tab
   → 看到 StockScreener 节点变为 "running"
   → 看到 TechnicalAnalyst 节点变为 "running"
   → ...
3. 切换到"日志" tab
   → 看到决策卡片实时追加
   → 点击展开 → 看到详细理由、风险、评分
4. 切换到"股票" tab
   → 看到新增持仓
5. 切换到"性能" tab
   → 看到排行榜更新
```

---

### 2.4 场景：查看持仓

**用户需求**：
- 当前赚了还是亏了
- 哪些股票在持仓

**功能设计**：
1. 股票页 → 持仓 tab
2. 显示：股票代码、股票名称、成本价、当前价、浮动盈亏、持仓数量

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 持仓列表 | `apps/frontend/src/components/trading-dashboard.tsx` | `股票` tab → 持仓 |
| 数据接口 | `apps/backend/app.py` | `GET /api/stocks/board` |
| 数据适配 | `apps/backend/adapters.py` | `stock_board_from_result()` |

**数据流**：
```
MultiAgentOrchestrator.run_competition()
  → 返回 result (包含每个账户的 positions)
  → FastAPI: stock_board_from_result(result)
  → 返回 holdings 列表
  → 前端渲染持仓表格
```

---

### 2.5 场景：对比模型

**用户需求**：
- 哪个 LLM 模型表现更好
- 为什么这个模型收益更高

**功能设计**：
1. 性能页 → 排行榜 tab
2. 按收益率排序，显示：排名、模型名、权益、收益率、最大回撤、胜率、交易次数
3. 点击模型 → 显示详情（持仓、交易记录）

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 排行榜 | `apps/frontend/src/components/trading-dashboard.tsx` | `性能` tab → 排行榜 |
| 数据接口 | `apps/backend/app.py` | `GET /api/metrics/rankings` |
| 数据适配 | `apps/backend/adapters.py` | `rankings_from_result()` |

**数据流**：
```
MultiAgentOrchestrator.run_competition()
  → 按 total_return 排序
  → 返回 result['rankings']
  → FastAPI: rankings_from_result(result)
  → 前端渲染排行榜表格
```

---

## 3. 量化研究者场景

### 3.1 场景：多模型长期对比

**用户需求**：
- 对比 rule-baseline, gpt-4o, claude-3.5 三个模型的长期表现
- 查看权益曲线、回撤、胜率

**功能设计**：
1. 性能页 → 权益曲线 tab
2. 多条曲线对比（每个模型一条）
3. 显示最大回撤、夏普比率、卡尔玛比率

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 权益曲线 | `apps/frontend/src/components/trading-dashboard.tsx` | `性能` tab → 权益曲线 + Recharts |
| 数据接口 | `apps/backend/app.py` | `GET /api/metrics/equity` |
| 数据适配 | `apps/backend/adapters.py` | `equity_metrics_from_result()` |
| MongoDB查询 | `src/astock_agent_system/storage/mongo_client.py` | `get_equity_curve()` |

**数据流**：
```
MongoDB: position_snapshots 集合
  → 按 agent_id + date 排序
  → 提取 equity 字段
  → 返回时间序列数据
  → FastAPI: equity_metrics_from_result()
  → 前端 Recharts 渲染多条曲线
```

---

### 3.2 场景：导出回测数据

**用户需求**：
- 导出交易记录到 CSV
- 导出决策日志到 JSON

**功能设计**：
1. 股票页 → 交易 tab → "导出 CSV" 按钮
2. 日志页 → "导出 JSON" 按钮

**实现位置**：

| 组件 | 文件路径 | 关键函数/组件 |
|------|---------|--------------|
| 导出按钮 | `apps/frontend/src/components/trading-dashboard.tsx` | `股票` / `日志` tab |
| 导出逻辑 | 前端 JavaScript | `downloadCSV()` / `downloadJSON()` |

**实现示例**：

```typescript
function downloadCSV(data: TradeRow[], filename: string) {
  const csv = [
    "date,stock_code,side,price,shares,cash_after,realized_pnl",
    ...data.map(row => `${row.date},${row.stock_code},${row.side},${row.price},${row.shares},${row.cash_after},${row.realized_pnl || 0}`)
  ].join("\n");
  
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
}
```

---

## 4. 开发者场景

### 4.1 场景：扩展新 Agent

**用户需求**：
- 想增加一个 "MacroAnalyst"（宏观分析 Agent）

**功能设计**：
1. 新建 `src/astock_agent_system/agents/macro_analyst.py`
2. 在 `MasterAgent` 中调用
3. 在 `PortfolioManager` 中接收输入

**实现步骤**：

```python
# 1. 创建新 Agent
# src/astock_agent_system/agents/macro_analyst.py

class MacroAnalyst:
    def analyze(self, date: str) -> MacroReport:
        # 获取宏观数据（GDP、CPI、利率等）
        # 分析宏观环境
        return MacroReport(
            gdp_growth=...,
            cpi=...,
            interest_rate=...,
            macro_score=...,
            recommendation="紧缩" or "宽松"
        )

# 2. 在 MasterAgent 中调用
# src/astock_agent_system/agents/master_agent.py

class MasterAgent:
    def __init__(self, ...):
        self.macro_analyst = MacroAnalyst()
    
    def analyze_stock(self, stock_code: str) -> StockAnalysisReport:
        macro = self.macro_analyst.analyze(datetime.now().strftime("%Y-%m-%d"))
        # ... 传递给 PortfolioManager
        decision = self.portfolio_manager.decide(..., macro=macro)

# 3. 在 PortfolioManager 中接收
# src/astock_agent_system/agents/portfolio_manager.py

class PortfolioManager:
    def decide(self, ..., macro: MacroReport | None = None) -> DecisionReport:
        # 如果宏观环境紧缩，降低仓位
        if macro and macro.recommendation == "紧缩":
            position_size *= 0.5
```

---

### 4.2 场景：接入新数据源

**用户需求**：
- 想接入 Wind（万得）数据源

**功能设计**：
1. 新建 `src/astock_agent_system/data/providers/wind_provider.py`
2. 在 `DataAgent` 中增加降级逻辑

**实现步骤**：

```python
# 1. 创建新 Provider
# src/astock_agent_system/data/providers/wind_provider.py

class WindProvider:
    def __init__(self, token: str):
        self.token = token
    
    def get_history(self, stock_code: str, days: int) -> list[Bar]:
        # 调用 Wind API
        return [...]

# 2. 在 DataAgent 中增加降级
# src/astock_agent_system/data/data_agent.py

class DataAgent:
    def __init__(self, settings: Settings):
        self.wind = WindProvider(settings.data.wind_token) if settings.data.wind_token else None
        self.tushare = TushareProvider(...)
        self.akshare = AkShareProvider(...)
    
    def get_history(self, stock_code: str, days: int) -> list[Bar]:
        if self.settings.data.mode == "offline":
            return self._load_sample(stock_code)
        
        # 在线模式：Wind → Tushare → AkShare → 离线样例
        if self.wind:
            try:
                return self.wind.get_history(stock_code, days)
            except Exception:
                pass
        
        if self.tushare:
            try:
                return self.tushare.get_history(stock_code, days)
            except Exception:
                pass
        
        # ... 降级到 AkShare 和离线样例
```

---

## 5. 快速查找代码位置表

### 5.1 按功能查找

| 功能 | 代码位置 |
|------|---------|
| **启动脚本** | `start.bat` / `start.ps1` |
| **后端入口** | `apps/backend/app.py` |
| **前端入口** | `apps/frontend/src/components/trading-dashboard.tsx` |
| **8 Agent** | `src/astock_agent_system/agents/` |
| **MasterAgent** | `src/astock_agent_system/agents/master_agent.py` |
| **MultiAgentOrchestrator** | `src/astock_agent_system/orchestrator/multi_agent_orchestrator.py` |
| **VirtualAccount** | `src/astock_agent_system/backtest/virtual_account.py` |
| **DataAgent** | `src/astock_agent_system/data/data_agent.py` |
| **配置管理** | `src/astock_agent_system/config.py` |
| **MongoDB** | `src/astock_agent_system/storage/mongo_client.py` |
| **Redis** | `src/astock_agent_system/storage/redis_client.py` |
| **LLM Client** | `src/astock_agent_system/llm/client.py` |

### 5.2 按 API 查找

| API 端点 | 代码位置 | 职责 |
|---------|---------|------|
| `GET /api/health` | `apps/backend/app.py` | 健康检查 |
| `GET /api/config` | `apps/backend/app.py` | 读取脱敏配置 |
| `POST /api/config/save` | `apps/backend/app.py` | 保存配置 |
| `POST /api/run` | `apps/backend/app.py` | 启动自动投资 |
| `GET /api/agents/flow` | `apps/backend/app.py` | 返回 React Flow 节点/边 |
| `GET /api/decisions` | `apps/backend/app.py` | 返回决策日志 |
| `GET /api/stocks/board` | `apps/backend/app.py` | 返回持仓/候选/交易 |
| `GET /api/metrics/equity` | `apps/backend/app.py` | 返回权益曲线 |
| `GET /api/metrics/rankings` | `apps/backend/app.py` | 返回模型排行榜 |
| `WebSocket /ws/events` | `apps/backend/app.py` | 实时事件推送 |

### 5.3 按用户操作查找

| 用户操作 | 前端组件 | 后端接口 | 业务逻辑 |
|---------|---------|---------|---------|
| 启动运行 | `总览` tab → "启动离线轮次" | `POST /api/run` | `MultiAgentOrchestrator.run_competition()` |
| 查看流程图 | `流程` tab → React Flow | `GET /api/agents/flow` + WebSocket | Agent 执行 → 推送事件 |
| 查看决策 | `日志` tab → DecisionCard | `GET /api/decisions` + WebSocket | `PortfolioManager.decide()` |
| 查看持仓 | `股票` tab → 持仓 | `GET /api/stocks/board` | `VirtualAccount.positions_to_dict()` |
| 查看排行榜 | `性能` tab → 排行榜 | `GET /api/metrics/rankings` | `MultiAgentOrchestrator` 排序 |
| 保存配置 | `设置` tab → "保存配置" | `POST /api/config/save` | `save_runtime_overrides()` |

---

## 6. 下一步阅读

- [系统架构](ARCHITECTURE.md) - 理解整体架构和 Agent 协作
- [流程与时序](FLOWS.md) - 理解从启动到交易的完整流程
- [设计决策](DESIGN_DECISIONS.md) - 理解为什么这么设计
- [同类项目对比](COMPARISON.md) - 和 FinRL、AutoGPT 对比
