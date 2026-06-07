# DebateRoom 多空辩论室

## 基本信息
- Agent ID: debate_room
- 版本: v1.0.0
- 最后更新: 2026-06-07
- 更新原因: 初始 Agent Markdown 描述。

## 角色定位
负责聚合技术、基本面和舆情结果，形成多空证据和裁判综合评分。

## 输入数据
- technical: 技术分析结果
- fundamental: 基本面分析结果
- sentiment: 舆情分析结果

## 机器可读配置
```yaml
agent_id: debate_room
name: DebateRoom 多空辩论室
version: v1.0.0
metadata:
  updated_at: "2026-06-07"
  update_reason: 初始辩论权重记录
rules:
  technical_weight: 0.40
  fundamental_weight: 0.35
  sentiment_weight: 0.25
learning_stats:
  recent_accuracy: unknown
  average_return_pct: unknown
```

## 学习经验
暂无足够样本。

## 输出格式
AnalysisResult(score, label, reasons, risks, metadata)
