# CLI流式智能体运行器 - 实施计划

更新时间：2026-06-09

## 项目背景

TUI/GUI开发遇到连接和交互复杂度问题，需要先用简单的Python CLI把Agent运行的完整流程打通，实时展示：
- 输入事件（股票筛选、数据获取）
- 思考过程（各Agent评分、LLM复核）  
- 工具调用（数据查询、技术分析）
- 决策输出（买入/卖出/持有）
- 盈亏统计（持仓、收益率、排行榜）

## 命令设计

```bash
# 启动智能体（选择模型后开始运行）
python -m astock_agent_system.cli agent start [--model MODEL] [--offline] [--verbose] [--max-count N] [--days N]

# 停止运行中的智能体
python -m astock_agent_system.cli agent stop [--model MODEL]

# 显示当前状态
python -m astock_agent_system.cli agent status [--model MODEL] [--format {text|json}]

# 查看历史记录
python -m astock_agent_system.cli agent history [--model MODEL] [--limit N]

# 列出可用模型
python -m astock_agent_system.cli agent list-models

# 运行benchmark（多模型对比）
python -m astock_agent_system.cli agent benchmark [--models MODEL1,MODEL2] [--offline]
```

## 实施进度

### Phase 1: 事件系统基础 ✅ (部分完成)

**已完成**：
- ✅ 创建事件定义 (`AgentEvent`, `EventType`)
- ✅ 创建事件发射器 (`AgentEventEmitter`)
- ✅ 创建控制台订阅器 (`ConsoleSubscriber`)
- ✅ 在`MultiAgentOrchestrator`中集成`event_emitter`参数

**待完成**：
- ⏳ 在关键执行点发射事件（筛选、分析、决策、交易）
- ⏳ 创建简单验证脚本

### Phase 2-8: 后续阶段

由于当前对话即将结束，建议下一位AI接手时按以下优先级继续：

1. **Phase 2: CLI命令骨架** - 扩展`cli.py`，添加`agent`子命令组
2. **Phase 3: Rich流式渲染** - 用Rich美化输出，支持颜色、动画、进度条
3. **Phase 4-5: 状态查询和Benchmark**
4. **Phase 6-7: 配置共享和API化**
5. **Phase 8: 分支合并到main**

## 当前代码位置

- **事件系统**：`src/astock_agent_system/events/`
  - `emitter.py` - 事件发射器
  - `subscriber.py` - 事件订阅器
  - `__init__.py` - 模块导出

- **已集成**：`src/astock_agent_system/orchestrator/multi_agent_orchestrator.py`
  - 构造函数接受`event_emitter`参数
  - `run_competition`中发射`agent_start`/`agent_complete`事件

## 下一步建议

由于开发过程发现完整实现需要较多工作量，建议采用**渐进式策略**：

### 选项A：继续完整实现（推荐用于充足时间）

按Phase 1-8完整实施，最终得到功能完整的CLI工具和API。

### 选项B：MVP快速验证（推荐用于快速测试）

简化方案，快速验证核心思路：

1. 创建最小CLI命令：
   ```python
   # src/astock_agent_system/cli_streaming.py
   def cmd_agent_start_simple():
       emitter = AgentEventEmitter()
       emitter.subscribe(ConsoleSubscriber(verbose=True))
       orchestrator = MultiAgentOrchestrator(event_emitter=emitter)
       orchestrator.run_competition(models=["rule-baseline"], max_count=1)
   ```

2. 运行验证：
   ```bash
   python -m astock_agent_system.cli_streaming
   ```

3. 看到事件流输出后，再决定是否继续完整实现

## 技术要点

### 事件类型

```python
EventType = Literal[
    "run_start", "run_complete", "run_error",
    "stage_start", "stage_complete",
    "agent_start", "agent_step", "agent_complete", "agent_error",
    "decision_made", "trade_executed", "metric_updated",
    "llm_request", "llm_response",
    "data_fetched", "progress_update",
]
```

### Rich输出设计

- **颜色方案**：成功=绿色，警告=黄色，失败=红色，信息=青色
- **动画元素**：旋转图标（⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏）、动态计时、进度条
- **层级结构**：阶段标题（大号粗体）→ Agent名称（中号粗体）→ 详细信息（普通缩进）

### 与现有代码集成

- 复用`MultiAgentOrchestrator`、`MasterAgent`、`VirtualAccount`
- 事件发射不影响现有功能（可选参数，默认空发射器）
- CLI和TUI共享配置文件 (`data/runtime/settings.override.json`)

## 分支合并计划

完成CLI开发后，将tauri-rewrite合并到main：

1. 运行完整验证：`.\start.bat -Mode delivery-check`
2. 更新所有相关文档
3. 合并：`git checkout main && git merge tauri-rewrite`
4. 推送：`git push origin main`
5. 更新Trellis handoff文档

## 参考资料

- Rich文档：https://rich.readthedocs.io/
- 现有TUI实现：`apps/tui/`
- 后端API契约：`apps/backend/app.py`
- 配置系统：`src/astock_agent_system/config.py`

## 状态总结

- **当前分支**：`tauri-rewrite`
- **Phase 1进度**：事件系统基础框架完成，待集成到更多执行点
- **下一优先级**：创建MVP验证或继续Phase 2 CLI命令骨架
- **预计工作量**：完整实现约20-24小时，MVP验证约2-4小时
