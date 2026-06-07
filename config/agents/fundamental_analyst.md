# FundamentalAnalyst 基本面分析师

## 基本信息
- Agent ID: fundamental_analyst
- 版本: v1.0.0
- 最后更新: 2026-06-07
- 更新原因: 初始 Agent Markdown 描述。

## 角色定位
负责评估估值、盈利质量、成长性和资产负债风险，提供中长期基本面评分。

## 输入数据
- financial: FinancialSnapshot 财务快照

## 评分规则
当前代码中的基本面阈值仍为主实现；本文件先记录规则和后续学习建议入口。

## 机器可读配置
```yaml
agent_id: fundamental_analyst
name: FundamentalAnalyst 基本面分析师
version: v1.0.0
metadata:
  updated_at: "2026-06-07"
  update_reason: 初始基本面描述
rules:
  pe_low_bonus: 0.12
  roe_quality_bonus: 0.12
  growth_bonus: 0.12
  debt_high_penalty: -0.12
learning_stats:
  recent_accuracy: unknown
  average_return_pct: unknown
```

## 学习经验
暂无足够样本。

## 输出格式
AnalysisResult(score, label, reasons, risks, metadata)
