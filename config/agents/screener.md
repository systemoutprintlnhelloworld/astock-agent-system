# StockScreener 股票筛选器

## 基本信息
- Agent ID: screener
- 版本: v1.0.0
- 最后更新: 2026-06-07
- 更新原因: 初始 Agent Markdown 描述。

## 角色定位
负责从股票池中选出候选标的，降低后续分析工作量并保持候选可解释。

## 输入数据
- universe: 股票池
- history_days: 历史数据窗口
- max_count: 候选数量

## 机器可读配置
```yaml
agent_id: screener
name: StockScreener 股票筛选器
version: v1.0.0
metadata:
  updated_at: "2026-06-07"
  update_reason: 初始筛选权重记录
rules:
  technical_weight: 0.45
  fundamental_weight: 0.35
  liquidity_weight: 0.20
learning_stats:
  recent_accuracy: unknown
  average_return_pct: unknown
```

## 学习经验
暂无足够样本。

## 输出格式
list[ScreenedStock]
