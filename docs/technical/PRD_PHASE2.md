# 持续学习与事件驱动系统 PRD

**文档版本**：v1.0  
**创建时间**：2026-06-05  
**目标版本**：v2.0 (Phase 2 增强)

---

## 1. 产品目标

在现有 A 股 LLM 多 Agent 模拟盘系统基础上，增加以下核心能力：

1. **持续学习系统**：Agent 系统能从历史交易中积累经验，改进决策质量
2. **事件驱动机制**：支持实时响应市场事件（新闻、公告、交易时间等）
3. **Agent 工具与知识库**：明确每个 Agent 的独有工具和知识库连接
4. **增强用户体验**：ChatGPT-like 日志可视化、防呆设计、自动模型列表获取
5. **开发规范强化**：Git Hooks 自动化提交和质量检查

---

## 2. 核心功能设计

### 2.1 持续学习系统

#### 2.1.1 记忆存储架构

参考 TradingGroup 的 Self-Reflection 和 FinMem 的分层记忆设计：

```
┌─────────────────────────────────────────────────────────┐
│               Agent Memory System                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Layer 1: 短期记忆 (Working Memory)                     │
│  ├─ 存储位置：Redis (TTL=1天)                          │
│  ├─ 内容：当日交易决策、实时市场状态                    │
│  └─ 用途：当日决策上下文                                │
│                                                         │
│  Layer 2: 中期记忆 (Episodic Memory)                    │
│  ├─ 存储位置：MongoDB.agent_memories                   │
│  ├─ 内容：成功/失败案例、决策推理链、盈亏结果           │
│  ├─ 索引：stock_code + decision_date + outcome         │
│  └─ 用途：检索相似历史案例                              │
│                                                         │
│  Layer 3: 长期记忆 (Semantic Memory)                    │
│  ├─ 存储位置：MongoDB.agent_learnings                  │
│  ├─ 内容：总结的经验教训、策略调整规则                  │
│  ├─ 更新频率：每周总结                                  │
│  └─ 用途：系统级策略优化                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### 2.1.2 经验积累流程

**触发时机**：每次交易结束后（T+1 卖出或止损）

**流程**：
```
1. 提取案例
   ├─ 买入决策：时间、价格、理由、Agent推理链
   ├─ 卖出决策：时间、价格、理由（正常卖出 or 止损）
   └─ 交易结果：盈亏金额、盈亏比例、持仓天数

2. 评估案例
   ├─ 如果盈利 > 5%：标记为 "successful"
   ├─ 如果亏损 > 3%：标记为 "failed"
   └─ 其他：标记为 "neutral"

3. 存储记忆
   ├─ MongoDB.agent_memories 插入案例
   └─ Redis 更新短期统计

4. 触发反思（可选）
   ├─ 如果连续3次失败：触发策略调整
   └─ 如果连续5次成功：总结成功模式
```

#### 2.1.3 记忆检索机制

**场景**：Agent 分析某只股票时，检索相似历史案例

**检索逻辑**：
```python
def retrieve_similar_cases(stock_code: str, current_signals: dict) -> list[Case]:
    # 1. 精确匹配：同一只股票的历史案例
    exact_cases = db.agent_memories.find({
        "stock_code": stock_code,
        "outcome": {"$in": ["successful", "failed"]}
    }).sort("decision_date", -1).limit(5)
    
    # 2. 模糊匹配：相似信号的其他股票案例
    similar_cases = db.agent_memories.find({
        "technical_signal": current_signals["technical"],
        "sentiment_score": {"$gte": current_signals["sentiment"] - 0.1,
                            "$lte": current_signals["sentiment"] + 0.1}
    }).sort("outcome", -1).limit(3)
    
    return list(exact_cases) + list(similar_cases)
```

---

### 2.2 事件驱动系统

#### 2.2.1 事件类型定义

| 事件类型 | 优先级 | 触发方式 | 数据源 | Phase |
|---------|--------|---------|--------|-------|
| **定时事件** | 中 | 定时轮询 | APScheduler | Phase 1 ✅ |
| **交易所公告** | 高 | 定时轮询 | Tushare公告接口 | Phase 2 |
| **重大新闻** | 高 | 定时轮询 | AkShare新闻 + smart-search | Phase 2 |
| **价格异动** | 高 | 实时监控 | WebSocket行情流 | Phase 3 |
| **监管事件** | 极高 | 定时轮询 | 证监会公告 | Phase 3 |

#### 2.2.2 Phase 2 实现：定时轮询模式

**架构**：
```
┌─────────────────────────────────────────────────────────┐
│              Event Polling Service                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  News Poller (每30分钟)                                 │
│  ├─ AkShare 股票新闻接口                                │
│  ├─ smart-search CLI（候选股票）                        │
│  └─ 输出：NewsEvent                                     │
│                                                         │
│  Announcement Poller (每1小时)                          │
│  ├─ Tushare 公告接口                                    │
│  ├─ 过滤：财报、停牌、重组、处罚                         │
│  └─ 输出：AnnouncementEvent                             │
│                                                         │
│  Event Filter                                           │
│  ├─ 只保留影响当前持仓或候选股票的事件                   │
│  └─ 去重：避免重复处理同一事件                           │
│                                                         │
│  Event Router                                           │
│  ├─ 重大事件 → 立即触发决策流程                          │
│  ├─ 普通事件 → 加入队列，下次定时运行时处理              │
│  └─ 次要事件 → 只记录日志                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### 2.2.3 事件可视化

**前端展示**：在 modern-ui 中增加"事件时间线" tab

```
┌─────────────────────────────────────────────────────────┐
│  事件时间线                        [实时] [今天] [本周]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🔴 15:30  重大事件                                     │
│  贵州茅台(600519) 发布2024年年报，净利润增长15%         │
│  → Agent反应：TechnicalAnalyst 建议持有，风险可控       │
│  → 决策：继续持有                                        │
│                                                         │
│  🟡 14:20  普通事件                                     │
│  招商银行(600036) 发布停牌公告，筹划重大资产重组        │
│  → Agent反应：RiskManager 建议观望                      │
│  → 决策：暂不操作                                        │
│                                                         │
│  🟢 10:00  定时事件                                     │
│  系统自动触发每日选股流程                                │
│  → 筛选出 5 只候选股票                                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### 2.3 Agent 工具与知识库

#### 2.3.1 工具分配表

| Agent | 工具 (Tools) | 知识库 (Knowledge Base) | Skill化 |
|-------|-------------|------------------------|---------|
| **DataAgent** | `fetch_history()`, `fetch_quote()`, `fetch_financial()` | Redis缓存 + Tushare/AkShare | ✅ `.cursor/skills/data-fetch/` |
| **StockScreener** | `filter_by_liquidity()`, `rank_by_score()` | 股票元数据（名称、行业、市值） | ✅ `.cursor/skills/stock-screening/` |
| **TechnicalAnalyst** | `calculate_rsi()`, `calculate_macd()`, `detect_pattern()` | 技术指标公式库（Markdown文档） | ✅ `.cursor/skills/technical-analysis/` |
| **FundamentalAnalyst** | `fetch_financial_report()`, `calculate_ratios()` | 无（直接读取DataAgent数据） | ✅ `.cursor/skills/fundamental-analysis/` |
| **SentimentAnalyst** | `fetch_news()`, `analyze_sentiment()` | 无（调用smart-search CLI） | ✅ `.cursor/skills/sentiment-analysis/` |
| **RiskManager** | `calculate_var()`, `check_position_limit()` | 风控规则库（config.yaml） | ✅ `.cursor/skills/risk-management/` |
| **PortfolioManager** | `optimize_portfolio()`, `calculate_position_size()` | 投资组合理论（Markdown文档） | ✅ `.cursor/skills/portfolio-optimization/` |
| **DebateRoom** | 无 | Agent记忆库（检索历史辩论） | ❌ |
| **MasterAgent** | `coordinate_agents()`, `aggregate_signals()` | 无 | ❌ |

#### 2.3.2 Skill 固化示例

**示例 1：技术分析 Skill**

文件位置：`.cursor/skills/technical-analysis/SKILL.md`

```markdown
---
name: technical-analysis
description: 计算股票技术指标（RSI、MACD、布林带等）
---

# Technical Analysis Skill

## Usage

```python
from cursor_skills import load_skill

skill = load_skill("technical-analysis")
result = skill.run({
    "stock_code": "600519",
    "bars": [...],  # K线数据
    "indicators": ["rsi", "macd", "bollinger"]
})
```

## Implementation

```python
def calculate_rsi(closes: list[float], period: int = 14) -> float:
    ...

def calculate_macd(closes: list[float]) -> dict:
    ...
```
```

---
```
### 2.4 ChatGPT-like 日志可视化

#### 2.4.1 展示粒度

**三层折叠设计**：

```
Level 1 (默认展示)：
┌────────────────────────────────────────────────────┐
│ 🤖 TechnicalAnalyst  15:30:05  [已完成]            │
│ 建议：买入  置信度：75%                             │
│ [展开详情 ▼]                                       │
└────────────────────────────────────────────────────┘

Level 2 (点击展开)：
┌────────────────────────────────────────────────────┐
│ 🤖 TechnicalAnalyst  15:30:05  [已完成]            │
│ 建议：买入  置信度：75%                             │
│ [收起 ▲]                                           │
│                                                    │
│ 💭 推理过程：                                       │
│ 1. RSI=32，处于超卖区间                            │
│ 2. MACD金叉，短期趋势向上                          │
│ 3. 成交量放大，资金流入                            │
│                                                    │
│ 🔧 工具调用：                                       │
│ - calculate_rsi(stock='600519', period=14) → 32   │
│ - calculate_macd(stock='600519') → {"signal": "golden_cross"} │
│                                                    │
│ [展开完整 CoT ▼]                                   │
└────────────────────────────────────────────────────┘

Level 3 (再次展开)：
┌────────────────────────────────────────────────────┐
│ 🤖 TechnicalAnalyst  15:30:05  [已完成]            │
│ 建议：买入  置信度：75%                             │
│ [收起 ▲]                                           │
│                                                    │
│ 💭 推理过程：                                       │
│ 1. RSI=32，处于超卖区间                            │
│ 2. MACD金叉，短期趋势向上                          │
│ 3. 成交量放大，资金流入                            │
│                                                    │
│ 🔧 工具调用：                                       │
│ - calculate_rsi(stock='600519', period=14) → 32   │
│ - calculate_macd(stock='600519') → {"signal": "golden_cross"} │
│                                                    │
│ 🧠 完整 CoT（DeepSeek-R1 思考过程）：              │
│ <think>                                            │
│ 让我分析一下这只股票的技术面...                     │
│ 首先计算RSI指标...                                 │
│ RSI=32说明股票处于超卖状态...                      │
│ 接下来看MACD...                                    │
│ </think>                                           │
│                                                    │
│ [收起 CoT ▲]                                       │
└────────────────────────────────────────────────────┘
```

#### 2.4.2 时间线展示

**垂直时间线 + 流程图双视图**：

- **流程视图**：React Flow 节点图（已实现）
- **时间线视图**（新增）：类似 ChatGPT 的对话历史

---

### 2.5 防呆设计与自动模型列表

#### 2.5.1 LLM 配置防呆

**检查流程**：

```
用户输入 Base URL 和 API Key
  ↓
1. 格式检查
   ├─ Base URL 必须以 http:// 或 https:// 开头
   ├─ API Key 不能为空
   └─ 如果格式错误 → 显示错误提示

2. 连通性检查
   ├─ 发送 GET /v1/models 请求
   ├─ 如果超时 → "无法连接到 API，请检查网络或 Base URL"
   └─ 如果 401 → "API Key 无效，请检查"

3. 功能检查
   ├─ 调用 /v1/chat/completions 测试
   ├─ 检查是否支持 function calling
   └─ 如果不支持 → "该 API 不支持工具调用，建议使用 OpenAI 兼容 API"

4. 自动获取模型列表
   ├─ 解析 /v1/models 响应
   ├─ 提取 model.id 字段
   └─ 显示在下拉框中供用户选择
```

#### 2.5.2 前端实现

```typescript
async function testLLMConnection(baseUrl: string, apiKey: string) {
  setTesting(true);
  setTestResult(null);
  
  try {
    // 1. 格式检查
    if (!baseUrl.startsWith("http")) {
      throw new Error("Base URL 必须以 http:// 或 https:// 开头");
    }
    
    // 2. 获取模型列表
    const response = await fetch(`${baseUrl}/models`, {
      headers: { "Authorization": `Bearer ${apiKey}` }
    });
    
    if (response.status === 401) {
      throw new Error("API Key 无效");
    }
    
    const data = await response.json();
    const models = data.data.map(m => m.id);
    
    // 3. 测试一个模型
    const testModel = models[0];
    const testResponse = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: testModel,
        messages: [{"role": "user", "content": "test"}],
        max_tokens: 10
      })
    });
    
    if (!testResponse.ok) {
      throw new Error("API 调用失败");
    }
    
    setTestResult({ success: true, models });
    setAvailableModels(models);
    
  } catch (error) {
    setTestResult({ success: false, error: error.message });
  } finally {
    setTesting(false);
  }
}
```

---

### 2.6 Git Hooks 自动化

#### 2.6.1 pre-commit Hook

文件位置：`.husky/pre-commit`

```bash
#!/bin/sh
. "$(dirname "$0")/_/husky.sh"

echo "🔍 Running pre-commit checks..."

# 1. Secrets 检查
echo "  ├─ Checking for secrets..."
if grep -r "sk-[a-zA-Z0-9]\{48\}" src/ apps/ 2>/dev/null; then
  echo "  ❌ Found potential API keys! Please remove them."
  exit 1
fi

if grep -r "TUSHARE_TOKEN.*=.*[a-z0-9]\{32\}" src/ apps/ 2>/dev/null; then
  echo "  ❌ Found Tushare token! Please use .env instead."
  exit 1
fi

# 2. 格式检查（Python）
echo "  ├─ Checking Python format..."
python -m black --check src/ 2>/dev/null || {
  echo "  ⚠️  Python code needs formatting. Run: python -m black src/"
  echo "  Auto-fixing..."
  python -m black src/
  git add src/
}

# 3. 格式检查（前端）
if [ -d "apps/frontend" ]; then
  echo "  ├─ Checking frontend format..."
  cd apps/frontend && npm run lint:fix 2>/dev/null || true
  cd ../..
fi

# 4. 测试（可选）
# echo "  ├─ Running tests..."
# python -m pytest --tb=short || exit 1

echo "  └─ ✅ All checks passed!"
```

#### 2.6.2 post-commit Hook（自动推送）

文件位置：`.husky/post-commit`

```bash
#!/bin/sh
. "$(dirname "$0")/_/husky.sh"

echo "📤 Auto-pushing to remote..."

# 获取当前分支
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# 推送到远程
git push origin $BRANCH 2>/dev/null || {
  echo "  ⚠️  Push failed. You may need to pull first."
  exit 0
}

echo "  ✅ Pushed to $BRANCH"
```

---

## 3. 技术实现方案

### 3.1 数据库 Schema 设计

#### MongoDB Collections

**agent_memories**（中期记忆）

```javascript
{
  _id: ObjectId,
  agent_id: "rule-baseline",  // 哪个模型账户的记忆
  stock_code: "600519",
  stock_name: "贵州茅台",
  decision_date: "2026-06-05",
  buy_price: 1850.0,
  buy_reason: "技术面强势突破 + 基本面稳健",
  buy_agent_chain: {  // 完整推理链
    technical: {...},
    fundamental: {...},
    sentiment: {...}
  },
  sell_date: "2026-06-10",
  sell_price: 1920.0,
  sell_reason: "达到目标盈利",
  pnl: 70.0,
  pnl_pct: 0.0378,
  holding_days: 5,
  outcome: "successful",  // successful | failed | neutral
  created_at: ISODate("2026-06-10T15:30:00Z")
}
```

**agent_learnings**（长期记忆）

```javascript
{
  _id: ObjectId,
  agent_id: "rule-baseline",
  learning_type: "pattern",  // pattern | strategy | risk
  summary: "在RSI<30且MACD金叉时买入，胜率高达70%",
  evidence_count: 15,  // 支持该经验的案例数量
  last_updated: ISODate("2026-06-05T00:00:00Z")
}
```

#### Redis Keys

```
# 短期记忆（当日）
agent:{agent_id}:today:decisions -> List[Decision]
agent:{agent_id}:today:stats -> Hash{win_count, loss_count, total_pnl}

# 缓存
stock:{stock_code}:quote -> JSON (TTL=5min)
stock:{stock_code}:history -> JSON (TTL=1day)
```

---

### 3.2 API 端点设计

#### 新增端点

```
POST /api/events/poll
  - 手动触发事件轮询
  - 返回：新事件列表

GET /api/events/timeline
  - 获取事件时间线
  - 参数：date_from, date_to, event_types
  - 返回：events[]

GET /api/agents/{agent_id}/memory
  - 获取 Agent 的记忆
  - 参数：stock_code, outcome
  - 返回：memories[]

POST /api/config/test-llm
  - 测试 LLM 连接
  - 请求：{ base_url, api_key }
  - 返回：{ success, models[], error }

GET /api/agents/tools
  - 获取所有 Agent 的工具列表
  - 返回：{ agent_tools: {...} }
```

---

## 4. 实施计划

### Phase 1：基础设施（当前迭代）

- [x] 调研 TradingAgents、FinMem、LangGraph 等项目
- [ ] 设计 MongoDB schema 和 Redis keys
- [ ] 实现记忆存储和检索基础类
- [ ] 配置 Git Hooks（pre-commit + post-commit）

### Phase 2：持续学习系统

- [ ] 实现案例评估和存储逻辑
- [ ] 在 PortfolioManager 中集成记忆检索
- [ ] 实现每周总结 Cron 任务
- [ ] 前端展示"历史案例"面板

### Phase 3：事件驱动系统

- [ ] 实现新闻轮询器（AkShare + smart-search）
- [ ] 实现公告轮询器（Tushare）
- [ ] 实现事件路由和过滤
- [ ] 前端展示"事件时间线"

### Phase 4：用户体验增强

- [ ] 实现 ChatGPT-like 日志三层折叠
- [ ] 实现 LLM 配置防呆检查
- [ ] 实现自动模型列表获取
- [ ] 固化 Agent 工具为 Skills

---

## 5. 验收标准

### 5.1 持续学习系统

- [ ] 系统能自动记录每笔交易的完整决策链
- [ ] Agent 在分析股票时能检索到相似历史案例
- [ ] 系统能生成每周经验总结报告

### 5.2 事件驱动系统

- [ ] 系统能每30分钟检查一次新闻事件
- [ ] 重大事件能立即触发决策流程
- [ ] 前端能实时显示事件时间线

### 5.3 用户体验

- [ ] 日志支持三层折叠展开
- [ ] LLM 配置能自动验证并获取模型列表
- [ ] Git commit 自动触发检查和推送

---

## 6. 风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 记忆检索性能 | 高 | MongoDB 创建索引 + Redis 缓存热数据 |
| 事件轮询频率限制 | 中 | 实现指数退避 + 缓存去重 |
| Git Hook 失败阻塞提交 | 中 | 提供 `--no-verify` 绕过选项 |
| 前端日志数据量过大 | 中 | 虚拟滚动 + 懒加载 |

---

## 7. 后续增强方向

- [ ] 支持向量数据库（Milvus）做语义检索
- [ ] 支持 LLM fine-tune（TradingGroup 的 data-synthesis pipeline）
- [ ] 支持实时 WebSocket 行情流
- [ ] 支持多币种（港股、美股）
