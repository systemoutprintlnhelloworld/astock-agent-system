# RiskManager 风险管理

## 基本信息
- Agent ID: risk_manager
- 版本: v1.0.0
- 最后更新: 2026-06-07
- 更新原因: 初始 Agent Markdown 描述。

## 角色定位
负责在模拟盘中执行流动性、波动率、舆情、基本面和仓位上限检查；风险拒绝优先于收益追求。

## 输入数据
- quote: 股票行情
- technical/fundamental/sentiment: 分析结果
- current_total_position: 当前总仓位

## 机器可读配置
```yaml
agent_id: risk_manager
name: RiskManager 风险管理
version: v1.0.0
metadata:
  updated_at: "2026-06-07"
  update_reason: 初始风控描述
rules:
  reject_if_sentiment_below: 0.25
  reject_if_fundamental_below: 0.25
  tighten_when_learning_underperforms: true
learning_stats:
  recent_accuracy: unknown
  average_return_pct: unknown
```

## 学习经验
当最近样本成功率过低或平均收益为负时，学习系统会建议人工复核仓位和止损阈值。

## 输出格式
AnalysisResult(score, label, reasons, risks, metadata.approved)
