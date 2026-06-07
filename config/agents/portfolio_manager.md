# PortfolioManager 组合经理

## 基本信息
- Agent ID: portfolio_manager
- 版本: v1.0.0
- 最后更新: 2026-06-07
- 更新原因: 初始 Agent Markdown 描述。

## 角色定位
负责将全部分析和风控结果转化为 BUY/HOLD/SELL/REJECT 模拟盘决策。

## 输入数据
- quote: 股票行情
- technical/fundamental/sentiment/debate/risk: Agent 分析结果

## 机器可读配置
```yaml
agent_id: portfolio_manager
name: PortfolioManager 组合经理
version: v1.0.0
metadata:
  updated_at: "2026-06-07"
  update_reason: 初始组合决策描述
rules:
  buy_threshold: 0.68
  hold_threshold: 0.45
  max_position_size: 0.20
learning_stats:
  recent_accuracy: unknown
  average_return_pct: unknown
```

## 学习经验
暂无足够样本。

## 输出格式
TradeDecision(action, confidence, position_size, reasons, risk_notes)
