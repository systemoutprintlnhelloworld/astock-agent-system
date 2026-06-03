# A股投资系统 - 项目实施计划

> 基于 Agent 架构的智能投资系统
> 生成时间：2026-06-01
> 状态：需求明确阶段 ✅

---

## 📋 项目概述

### 核心目标
构建一个基于多智能体（Multi-Agent）协作的A股投资系统，通过定期定盘、舆情分析和模拟盘测试，实现自动化的投资决策支持。

### 系统定位
- **当前阶段**：模拟交易系统（Paper Trading）
- **最终目标**：半自动交易系统（需经过充分验证）
- **用户水平**：投资新手
- **风险策略**：先模拟验证，再考虑实盘

---

## ✅ 已确认的技术决策

### 1. 数据源配置
| 类型 | 方案 | 状态 |
|------|------|------|
| **行情数据** | Tushare（主）+ AkShare（兜底） | ✅ Token已提供 |
| **舆情数据** | smart-search CLI | ✅ 已配置可用 |
| **LLM服务** | OpenAI兼容接口（不限定模型） | ⏳ 待主人配置 |

**Tushare Token**: 通过环境变量 `TUSHARE_TOKEN` 配置（真实 Token 不写入仓库）

### 2. Agent 架构（8角色完整版）
```
Master Agent (主控)
├── Data Agent (数据获取)
├── Technical Analyst (技术分析)
├── Fundamental Analyst (基本面分析)
├── Sentiment Analyst (舆情分析 - 使用 smart-search)
├── Debate Room (牛熊辩论)
├── Risk Manager (风控 - 一票否决权)
└── Portfolio Manager (组合管理 - 最终决策)
```

### 3. 技术栈选型
| 组件 | 选择 | 理由 |
|------|------|------|
| **Agent框架** | LangGraph | 状态机、可持久化、observability最佳 |
| **数据库** | MongoDB + Redis | 持久化 + 缓存 |
| **回测引擎** | Backtrader | 成熟稳定、文档完善 |
| **前端界面** | Streamlit | 快速开发、适合原型 |
| **通信方式** | 异步（Async） | 提升性能、支持并发 |

### 4. 运行机制
- **定盘时间**：每日收盘后自动执行
- **自动化程度**：全自动分析 + 人工审核决策
- **舆情监控**：每只股票 2-3 次 smart-search 调用

---

## 🏗️ 系统架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     定时调度器 (APScheduler)                 │
│                  每日收盘后 15:30 自动触发                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Master Agent (主控协调)                   │
│  - 接收股票列表                                              │
│  - 任务拆解和编排                                            │
│  - 异常处理和重试                                            │
│  - 生成最终报告                                              │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Data Agent   │  │ Technical    │  │ Fundamental  │
│              │  │ Analyst      │  │ Analyst      │
│ Tushare +    │  │              │  │              │
│ AkShare      │  │ 技术指标计算  │  │ 财务分析     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Sentiment       │
                │ Analyst         │
                │                 │
                │ smart-search    │
                │ CLI 调用        │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Debate Room     │
                │                 │
                │ Bull vs Bear    │
                │ 对抗性辩论      │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Risk Manager    │
                │                 │
                │ 风控检查        │
                │ 一票否决权      │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Portfolio       │
                │ Manager         │
                │                 │
                │ 最终决策        │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ 模拟交易引擎     │
                │ (Backtrader)    │
                │                 │
                │ 虚拟账户管理     │
                └─────────────────┘
```

### 数据流设计

```
1. 数据获取层
   ├── Tushare API (主数据源)
   │   ├── 实时行情
   │   ├── 历史K线
   │   └── 财务数据
   ├── AkShare (兜底)
   │   └── 当Tushare限流时使用
   └── smart-search CLI (舆情)
       ├── 新闻搜索
       ├── 社区讨论
       └── 情绪分析

2. 分析处理层
   ├── 技术分析 (TA-Lib + 自定义指标)
   ├── 基本面分析 (财务指标计算)
   ├── 舆情分析 (LLM情绪打分)
   └── 多Agent协作 (LangGraph编排)

3. 决策执行层
   ├── 辩论机制 (Bull vs Bear)
   ├── 风控检查 (合规性、风险评估)
   ├── 组合管理 (仓位分配)
   └── 模拟交易 (虚拟订单执行)

4. 存储缓存层
   ├── MongoDB (持久化存储)
   │   ├── 历史分析报告
   │   ├── 交易记录
   │   └── Agent推理日志
   └── Redis (缓存)
       ├── 行情数据缓存
       ├── LLM响应缓存
       └── 舆情数据缓存
```

---

## 📊 核心模块详细设计

### 4. Sentiment Analyst（舆情分析模块）⭐

**职责**：使用 smart-search 搜索新闻和社区讨论，LLM分析情绪

**工作流程**：
```python
# 1. 搜索最新新闻
smart-search search "{stock_name} {stock_code} 最新新闻" --extra-sources 2

# 2. 抓取关键页面
smart-search fetch <url> --format markdown

# 3. LLM情绪分析（调用OpenAI兼容接口）
```

**输出格式**：
```json
{
  "sentiment_score": 0.65,  // -1到1
  "sentiment_label": "偏正面",
  "key_events": ["财报超预期", "机构调研"],
  "risk_signals": []
}
```

---

### 5. Debate Room（辩论机制）

**职责**：Bull vs Bear 对抗性辩论，减少偏差

**流程**：
1. Bull Researcher 提出看多理由
2. Bear Researcher 提出看空理由
3. LLM Judge 汇总双方观点
4. 输出平衡后的综合判断

---

### 6. Risk Manager（风控模块）⚠️

**职责**：风险检查，一票否决权

**检查项**：
- 是否停牌/ST/退市风险
- 是否涨跌停（无法成交）
- 波动率是否过高
- 流动性是否充足
- 仓位是否超限

**输出**：通过/拒绝 + 仓位建议 + 止损位

---

### 7. Portfolio Manager（组合管理）

**职责**：最终决策和交易指令生成

**输出格式**：
```json
{
  "action": "买入",
  "target_price": 1700,
  "stop_loss": 1620,
  "position_size": 0.10,  // 10%仓位
  "time_horizon": "1个月",
  "confidence": 0.75
}
```

---

## 🔄 模拟盘实现方案

### 虚拟账户设计

```python
class VirtualAccount:
    def __init__(self, initial_capital=100000):
        self.cash = initial_capital
        self.positions = {}  # {stock_code: {shares, cost_basis}}
        self.history = []
        
    def buy(self, stock_code, price, shares):
        """买入股票"""
        cost = price * shares * (1 + 0.0003)  # 佣金
        if cost > self.cash:
            return False
        self.cash -= cost
        # 更新持仓
        
    def sell(self, stock_code, price, shares):
        """卖出股票"""
        revenue = price * shares * (1 - 0.0003 - 0.001)  # 佣金+印花税
        self.cash += revenue
        # 更新持仓
```

### 回测引擎（Backtrader）

**配置**：
- 初始资金：10万元
- 佣金：万3
- 印花税：千1（卖出）
- 滑点：0.1%
- T+1 限制

**绩效指标**：
- 总收益率
- 年化收益率
- Sharpe Ratio（目标 > 1.5）
- Max Drawdown（目标 < 18%）
- 胜率
- 盈亏比

---

## ⏰ 定时任务设计

### 调度方案（APScheduler）

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# 每日收盘后15:30执行
@scheduler.scheduled_job('cron', hour=15, minute=30, day_of_week='mon-fri')
async def daily_analysis():
    """每日定盘分析"""
    stock_list = get_stock_pool()  # 获取股票池
    for stock in stock_list:
        await master_agent.analyze(stock)
```

### 执行流程

```
15:00 收盘
  ↓
15:30 触发定时任务
  ↓
15:30-16:00 数据获取（行情+财务）
  ↓
16:00-16:30 多Agent并行分析
  ↓
16:30-17:00 辩论+风控+决策
  ↓
17:00 生成报告和交易指令
  ↓
17:00 更新模拟盘（虚拟执行）
```

---

## 💰 成本优化方案

### LLM 调用优化

**智能路由**：
- 简单任务（数据抽取）→ 小模型
- 复杂推理（辩论、决策）→ 大模型

**缓存策略**：
```python
# Redis缓存LLM响应
cache_key = f"llm:{prompt_hash}:{model}"
if redis.exists(cache_key):
    return redis.get(cache_key)
```

**成本预估**（每日分析10只股票）：
- Data Agent: 无LLM调用
- Technical Analyst: 1次/股 × 10股 = 10次
- Fundamental Analyst: 1次/股 × 10股 = 10次
- Sentiment Analyst: 3次/股 × 10股 = 30次（含smart-search）
- Debate Room: 3次/股 × 10股 = 30次
- Risk Manager: 1次/股 × 10股 = 10次
- Portfolio Manager: 1次/股 × 10股 = 10次

**总计**：约100次LLM调用/天
**预估费用**：50-200元/月（取决于模型选择）

---

## 📅 开发里程碑

### Phase 1: MVP 核心功能（2周）

**Week 1: 基础框架**
- [ ] 项目初始化和环境配置
- [ ] Data Agent 实现（Tushare + AkShare）
- [ ] MongoDB + Redis 配置
- [ ] LangGraph 基础框架搭建

**Week 2: 分析模块**
- [ ] Technical Analyst 实现
- [ ] Fundamental Analyst 实现
- [ ] Sentiment Analyst 实现（集成smart-search）
- [ ] 单股分析流程打通

**交付物**：
- 能够分析单只股票并生成结构化报告
- 包含技术面、基本面、舆情三个维度

---

### Phase 2: 决策和模拟盘（2周）

**Week 3: 决策机制**
- [ ] Debate Room 实现
- [ ] Risk Manager 实现
- [ ] Portfolio Manager 实现
- [ ] Master Agent 编排逻辑

**Week 4: 模拟盘**
- [ ] Backtrader 回测引擎集成
- [ ] 虚拟账户管理
- [ ] 订单执行和持仓跟踪
- [ ] 绩效指标计算

**交付物**：
- 完整的分析→决策→执行闭环
- 模拟盘可以虚拟交易并跟踪绩效

---

### Phase 3: 自动化和优化（1周）

**Week 5: 自动化**
- [ ] 定时任务（APScheduler）
- [ ] 批量分析（股票池管理）
- [ ] 异常处理和重试机制
- [ ] 日志和监控

**交付物**：
- 每日自动定盘分析
- 完整的日志和错误处理

---

### Phase 4: 界面和报告（1周）

**Week 6: 用户界面**
- [ ] Streamlit 仪表盘
- [ ] 分析报告展示
- [ ] 模拟盘绩效可视化
- [ ] 配置管理界面

**交付物**：
- 可视化界面
- 导出PDF/Markdown报告

---

## 📁 项目目录结构

```
astock-agent-system/
├── README.md
├── requirements.txt
├── .env.example
├── config/
│   ├── config.yaml          # 系统配置
│   └── stocks.yaml          # 股票池配置
├── src/
│   ├── agents/
│   │   ├── master_agent.py
│   │   ├── data_agent.py
│   │   ├── technical_analyst.py
│   │   ├── fundamental_analyst.py
│   │   ├── sentiment_analyst.py
│   │   ├── debate_room.py
│   │   ├── risk_manager.py
│   │   └── portfolio_manager.py
│   ├── data/
│   │   ├── tushare_client.py
│   │   ├── akshare_client.py
│   │   └── smart_search_client.py
│   ├── backtest/
│   │   ├── backtrader_engine.py
│   │   └── virtual_account.py
│   ├── utils/
│   │   ├── llm_client.py
│   │   ├── cache.py
│   │   └── logger.py
│   └── scheduler/
│       └── daily_task.py
├── tests/
├── data/                    # 数据缓存目录
├── logs/                    # 日志目录
└── reports/                 # 报告输出目录
```

---

## 🎯 待主人确认的关键问题

浮浮酱已经根据主人的指示自行规划了大部分细节，但还有以下问题需要主人最终确认：

### 1. 股票池范围
**问题**：系统每天分析哪些股票？
**选项**：
- A. 固定股票池（如沪深300成分股）
- B. 自定义股票列表（主人手动指定）
- C. 动态筛选（基于某些条件自动筛选）
- D. 全市场扫描（5000+只股票，耗时长）

**浮浮酱建议**：B（自定义列表，初期10-20只股票）

---

### 2. 报告输出方式
**问题**：分析报告如何呈现？
**选项**：
- A. Streamlit Web界面（可视化仪表盘）
- B. 每日邮件发送报告
- C. 微信/钉钉推送
- D. 仅保存到本地文件

**浮浮酱建议**：A + D（Web界面查看 + 本地存档）

---

### 3. 模拟盘初始资金
**问题**：虚拟账户初始资金多少？
**选项**：
- A. 10万元（标准配置）
- B. 50万元
- C. 100万元
- D. 其他金额

**浮浮酱建议**：A（10万元，与后续实盘规模匹配）

---

### 4. 风控参数
**问题**：风控的严格程度？
**选项**：
- A. 保守型（单股最大10%仓位，总仓位50%）
- B. 平衡型（单股最大20%仓位，总仓位70%）
- C. 激进型（单股最大30%仓位，总仓位90%）

**浮浮酱建议**：A（保守型，新手适用）

---

### 5. 开发时间预期
**问题**：主人希望多久完成MVP？
**选项**：
- A. 2周（快速原型，功能简化）
- B. 4周（标准MVP，功能完整）
- C. 6周（完整系统，包含优化）

**浮浮酱建议**：B（4周，平衡速度和质量）

---

### 6. 是否需要历史回测
**问题**：除了模拟盘，是否需要历史数据回测？
**选项**：
- A. 需要（用3-5年历史数据验证策略）
- B. 不需要（直接上模拟盘）

**浮浮酱建议**：A（历史回测可以快速发现问题）

---

### 7. LLM 模型具体选择
**问题**：主人计划使用哪个具体模型？
**选项**：
- A. 通义千问（Qwen-Max/Qwen-Plus）
- B. DeepSeek（DeepSeek-V3）
- C. 智谱AI（GLM-4）
- D. OpenAI（GPT-4）
- E. 其他（请说明）

**浮浮酱建议**：A 或 B（中文能力强，性价比高）

---

### 8. 数据库部署方式
**问题**：MongoDB 和 Redis 如何部署？
**选项**：
- A. Docker 容器（推荐，一键部署）
- B. 本地安装
- C. 云服务（阿里云/腾讯云）

**浮浮酱建议**：A（Docker，方便管理）

---

## 📋 主人需要准备的资源清单

### 立即需要（P0）
- [x] Tushare Token（已提供）
- [x] smart-search CLI（已配置）
- [ ] OpenAI 兼容接口的 API Key
- [ ] Python 3.10+ 环境

### 第一周需要（P1）
- [ ] MongoDB（建议Docker部署）
- [ ] Redis（建议Docker部署）
- [ ] 确定股票池列表（10-20只股票）

### 后续需要（P2）
- [ ] 服务器/云主机（如需7×24运行）
- [ ] 域名（如需外网访问）

---

## ⚠️ 风险提示和免责声明

**重要提醒**：
1. 本系统仅用于学习和研究目的
2. 不构成任何投资建议
3. 模拟盘结果不代表实盘表现
4. 投资有风险，决策需谨慎
5. 建议模拟盘验证至少3-6个月后再考虑实盘
6. 实盘初期建议使用极小资金（总资产1-3%）

**法律合规**：
- 遵守中国证券法相关规定
- 自动化交易需向券商报备
- 数据获取需遵守网站 robots.txt
- 不得用于非法用途

---

## 📞 后续沟通机制

**开发过程中的沟通**：
- 每周进度汇报
- 关键决策点需主人确认
- 遇到技术难题及时沟通

**交付验收**：
- 每个 Phase 完成后演示
- 主人测试并提出反馈
- 根据反馈迭代优化

---

## 🎉 总结

浮浮酱已经完成了完整的项目规划喵～(๑•̀ㅂ•́)و✧

**已确认的内容**：
- ✅ 8角色 Agent 架构
- ✅ LangGraph + MongoDB + Redis + Backtrader 技术栈
- ✅ 异步通信、收盘后定盘、全自动运行
- ✅ Tushare + AkShare + smart-search 数据源
- ✅ 4周开发计划（2周MVP + 2周完善）

**待主人确认的8个问题**：
1. 股票池范围
2. 报告输出方式
3. 模拟盘初始资金
4. 风控参数
5. 开发时间预期
6. 是否需要历史回测
7. LLM 模型具体选择
8. 数据库部署方式

**主人，请您查看完整的 `PROJECT_PLAN.md` 文件，并回答上述8个问题，浮浮酱就可以开始实施了喵～** (ง •̀_•́)ง

---

*文档生成时间：2026-06-01*
*版本：v1.0*
*状态：待主人确认*

---

## 📊 核心模块详细设计

### 1. Data Agent（数据获取模块）

**职责**：
- 从 Tushare 获取行情和财务数据
- AkShare 作为降级兜底方案
- 数据清洗和标准化
- 缓存管理（避免重复请求）

**关键功能**：
```python
class DataAgent:
    def get_stock_data(self, stock_code, start_date, end_date):
        """获取股票历史数据"""
        # 1. 检查Redis缓存
        # 2. 尝试Tushare API
        # 3. 失败则降级到AkShare
        # 4. 数据清洗和标准化
        # 5. 存入缓存和MongoDB
        
    def get_financial_data(self, stock_code):
        """获取财务数据"""
        # PE, PB, ROE, 负债率等
        
    def get_realtime_quote(self, stock_code):
        """获取实时行情"""
```

**数据结构**：
```json
{
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "date": "2026-06-01",
  "open": 1650.00,
  "high": 1680.00,
  "low": 1645.00,
  "close": 1670.00,
  "volume": 1234567,
  "amount": 2058765432.00,
  "pe_ttm": 35.6,
  "pb": 12.3,
  "market_cap": 2100000000000
}
```

---

### 2. Technical Analyst（技术分析模块）

**职责**：
- 计算技术指标（MA、MACD、RSI、KDJ、布林带等）
- 识别技术形态（头肩顶、双底、三角形等）
- 判断趋势和支撑/阻力位
- 生成技术面评分和建议

**关键指标**：
- **趋势指标**：MA5/10/20/60、MACD、DMI
- **震荡指标**：RSI、KDJ、CCI
- **成交量指标**：OBV、VOL
- **波动率指标**：ATR、布林带

**输出格式**：
```json
{
  "agent": "Technical Analyst",
  "stock_code": "600519",
  "analysis_date": "2026-06-01",
  "trend": "上升趋势",
  "signal": "买入",
  "confidence": 0.75,
  "key_indicators": {
    "ma5": 1665.0,
    "ma20": 1620.0,
    "macd": {"dif": 12.5, "dea": 8.3, "macd": 4.2},
    "rsi": 68.5,
    "kdj": {"k": 75.2, "d": 68.9, "j": 87.8}
  },
  "support_levels": [1620, 1580],
  "resistance_levels": [1700, 1750],
  "reasoning": "股价站上MA5和MA20，MACD金叉，RSI处于强势区间但未超买..."
}
```

---

### 3. Fundamental Analyst（基本面分析模块）

**职责**：
- 分析财务指标（盈利能力、成长性、估值水平）
- 行业对比和竞争力分析
- 财务健康度评估
- 生成基本面评分和建议

**关键指标**：
- **盈利能力**：ROE、ROA、净利率、毛利率
- **成长性**：营收增长率、净利润增长率
- **估值水平**：PE、PB、PS、PEG
- **财务健康**：资产负债率、流动比率、速动比率

**输出格式**：
```json
{
  "agent": "Fundamental Analyst",
  "stock_code": "600519",
  "analysis_date": "2026-06-01",
  "signal": "持有",
  "confidence": 0.80,
  "valuation": {
    "pe_ttm": 35.6,
    "pb": 12.3,
    "industry_avg_pe": 32.5,
    "assessment": "略高估"
  },
  "profitability": {
    "roe": 0.28,
    "net_margin": 0.52,
    "assessment": "优秀"
  },
  "growth": {
    "revenue_growth_yoy": 0.15,
    "profit_growth_yoy": 0.18,
    "assessment": "稳健增长"
  },
  "reasoning": "公司盈利能力强劲，ROE达28%，但当前估值略高于行业平均..."
}
```

---

### 4. Sentiment Analyst（舆情分析模块）⭐

**职责**：
- 使用 smart-search 搜索最新新闻和社区讨论
- 抓取关键页面内容
- LLM 分析情绪倾向和关键事件
- 量化舆情为情绪分数

**工作流程**：
```python
class SentimentAnalyst:
    def analyze(self, stock_code, stock_name):
        # 1. 搜索最新新闻
        news = self.search_news(stock_code, stock_name)
        
        # 2. 抓取关键页面
        contents = self.fetch_key_pages(news['urls'][:2])
        
        # 3. LLM情绪分析
        sentiment = self.llm_analyze_sentiment(contents)
        
        # 4. 识别关键事件
        events = self.extract_key_events(contents)
        
        return {
            "sentiment_score": sentiment,  # -1 到 1
            "key_events": events,
            "risk_signals": []
        }
    
    def search_news(self, stock_code, stock_name):
        """调用 smart-search"""
        cmd = [
            "smart-search", "search",
            f"{stock_name} {stock_code} 最新新闻 舆情",
            "--extra-sources", "2",
            "--format", "json"
        ]
        result = subprocess.run(cmd, capture_output=True)
        return json.loads(result.stdout)
```

**输出格式**：
```json
{
  "agent": "Sentiment Analyst",
  "stock_code": "600519",
  "analysis_date": "2026-06-01",
  "sentiment_score": 0.65,
  "sentiment_label": "偏正面",
  "confidence": 0.70,
  "key_events": [
    {
      "event": "公司发布Q1财报，营收同比增长18%",
      "impact": "正面",
      "source": "新浪财经",
      "date": "2026-05-28"
    },
    {
      "event": "机构调研频繁，多家券商上调目标价",
      "impact": "正面",
      "source": "雪球",
      "date": "2026-05-30"
    }
  ],
  "risk_signals": [],
  "news_count": 15,
  "discussion_heat": "高",
  "reasoning": "近期新闻以正面为主，财报超预期，机构看好..."
}
```
