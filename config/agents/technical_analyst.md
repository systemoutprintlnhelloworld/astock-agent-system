# TechnicalAnalyst 技术分析师

## 基本信息
- Agent ID: technical_analyst
- 版本: v1.0.0
- 最后更新: 2026-06-07
- 更新原因: 初始 Agent Markdown 描述，外部化可调技术分析权重。

## 角色定位
负责用可解释的技术指标评估股票短中期走势，包括均线、价格位置、动量、RSI 和波动率。

## 输入数据
- stock_code: 股票代码
- bars: 历史 K 线列表

## 评分规则
- 基础分: 0.50
- MA5 高于 MA20: +0.16
- MA5 不高于 MA20: -0.12
- 收盘价站上 MA20: +0.10
- 收盘价低于 MA20: -0.08
- 20 日正收益上限: +0.16
- 20 日负收益下限: -0.16
- RSI 健康区间: +0.08
- RSI 过热: -0.10
- RSI 弱势或超跌: -0.04
- 低波动: +0.06
- 高波动: -0.12

## 机器可读配置
```yaml
agent_id: technical_analyst
name: TechnicalAnalyst 技术分析师
version: v1.0.0
metadata:
  updated_at: "2026-06-07"
  update_reason: 初始技术指标权重
rules:
  ma_cross_bonus: 0.16
  ma_cross_penalty: -0.12
  close_above_ma20_bonus: 0.10
  close_below_ma20_penalty: -0.08
  momentum_positive_cap: 0.16
  momentum_positive_multiplier: 1.8
  momentum_negative_floor: -0.16
  momentum_negative_multiplier: 1.5
  rsi_healthy_bonus: 0.08
  rsi_overheated_penalty: -0.10
  rsi_weak_penalty: -0.04
  volatility_low_bonus: 0.06
  volatility_high_penalty: -0.12
learning_stats:
  recent_accuracy: unknown
  average_return_pct: unknown
```

## 学习经验
暂无足够样本。达到 30 条经验后由学习系统生成建议，人工确认后再调整本文件。

## 输出格式
AnalysisResult(score, label, reasons, risks, metadata)
