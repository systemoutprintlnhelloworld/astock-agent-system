# TUI 改造总结

更新时间：2026-06-09

## 已完成的改造

### 1. 交互式配置向导 ✓

**文件**：`apps/tui/config_wizard.py`, `apps/tui/app.py`

**改进**：
- 使用 **InquirerPy** 提供交互式表单（↑↓ 导航，Enter 确认）
- 数据模式和 LLM 请求档位使用下拉菜单选择
- 数据源 provider chain 使用 checkbox 多选（空格选择/取消，Enter 确认），不再要求用户手写逗号列表
- 默认 LLM 模型优先来自后端模型列表，并通过 fuzzy 过滤选择
- 比赛模型已移出初始化向导，改为运行前通过 `/models select`、`/models set` 或 `/start --models` 选择
- 密钥字段使用 `inquirer.secret()` 不回显
- 使用 **Rich Table** 渲染配置摘要（密钥显示为 `[已设置]`）
- 确认保存使用 `inquirer.confirm()`
- 支持 Ctrl+C 中断向导
- 向导会先展示当前已生效配置；非密钥字段回填上次保存值，密钥字段只显示状态
- 只有 provider chain 中被选中的数据源才会继续询问对应凭证，未选源直接跳过

**测试**：
- `test_wizard_interactive.py`：验证数据结构和 Rich 渲染 ✓
- 真实终端手动测试：`python -m apps.tui`

### 2. Prompt-toolkit 命令补全和历史 ✓

**文件**：`apps/tui/prompt.py`, `apps/tui/app.py`

**改进**：
- 使用 **prompt-toolkit** 提供输入即显式的 slash command palette
- 输入 `/` 后直接显示候选命令和说明，继续输入会过滤候选，不再依赖先按 Tab 才发现命令
- 自定义 `SlashCommandCompleter` 支持嵌套补全（命令 → 子命令 → 参数 → 后端模型名）
- 支持历史记录（↑↓ 导航，Ctrl+R 搜索）
- 历史持久化到 `data/runtime/tui_history.txt`
- **降级方案**：非 TTY 环境自动回退到普通 input()

**补全覆盖**：
- 根命令：`/help`, `/status`, `/config`, `/models`, `/workflow`, `/start`, `/dashboard`, `/agent` 等
- 子命令：`/config show|test-llm`, `/dashboard trading|run|rankings|decisions|providers|status` 等
- 参数：`/start --offline|--models|--max-count|--days|--foreground`
- 模型：`/models set ...` 和 `/start --models ...` 会补全后端刷新到的模型列表

**测试**：
- `test_prompt_toolkit.py`：验证补全逻辑 ✓
- 真实终端手动测试：`python -m apps.tui --skip-wizard`

### 3. Rich 输出美化 ✓

**文件**：`apps/tui/app.py`, `apps/tui/config_wizard.py`

**改进**：
- 使用 **Rich Console** 替代 print()
- 彩色输出：`[cyan]` 附件，`[green]` 成功，`[yellow]` 警告，`[red]` 错误
- Rich Table 渲染配置摘要
- Rich Panel 渲染向导欢迎面板
- 保持现有文本分栏布局（20/80）

### 4. 模型列表自动获取 ✓

**文件**：`apps/tui/commands/slash.py`

**现状**：已实现，`/models list` 命令从后端刷新模型列表并缓存到 TUI 状态；`/models select` 提供 InquirerPy checkbox 多选；`/models selected` 查看当前比赛模型。比赛模型只影响本轮并行 Agent/虚拟账户，不写入初始化配置。

### 5. 交易看板和运行观测 ✓

**文件**：`apps/tui/app.py`, `apps/tui/commands/slash.py`, `apps/tui/widgets/dashboard.py`

**改进**：
- `/dashboard` 默认显示“交易看板”，`/dashboard status` 才显示连接和上下文状态
- 新增 `/run` 和 `/dashboard run`，用于查看当前/最近一次运行观测
- `/start` 提交后台任务后自动切换到运行观测视图，不再只打印 run_id JSON
- 运行观测聚合 run 状态、模型排行榜、股票/持仓/交易看板和决策日志
- 每次关键命令后清屏重绘 20/80 主布局，减少历史输出和旧配置摘要堆叠
- 状态栏靠近输入区显示，便于长程运行中随时确认连接、模型和上下文状态

## 待完成的改造

### 1. 注册全局命令路径加固

**目标**：用户可以在任意目录稳定运行 `astock-tui` 启动 TUI。

**当前状态**：`pyproject.toml` 已注册 `astock-tui` entry point，仓库根目录也提供 `astock-tui.bat`。后续可继续加固 Windows 用户脚本目录不在 PATH、以及从任意目录启动时自动定位项目根目录的问题。

**当前入口**：
```toml
# pyproject.toml
[project.scripts]
astock-agent = "astock_agent_system.cli:main"
astock-tui = "apps.tui.app:run_tui"
```

### 2. 更新文档

**需要更新**：
- [x] `docs/tui/MANUAL_TEST.md`：手动测试指南
- [x] `docs/tui/TUI_UX_REDESIGN_PLAN.md`：本轮 TUI UX / 可观察性计划
- [x] `docs/trellis/IMPLEMENT.md`：更新实现状态
- [x] `DOCUMENTATION_MAP.md`：添加 TUI 文档索引
- [ ] `README.md`：添加 TUI 使用说明

## 技术决策记录

### InquirerPy vs Textual

**选择**：InquirerPy + prompt-toolkit
**原因**：
- InquirerPy 提供开箱即用的表单组件
- prompt-toolkit 提供成熟的补全和历史机制
- 比 Textual 轻量，无需全屏 TUI 框架
- 与项目"轻量终端客户端"定位一致

### Rich vs Click

**选择**：Rich
**原因**：
- Rich 提供更丰富的格式化输出（表格、面板、进度条）
- 与 InquirerPy 配合更好
- Click 主要用于 CLI 参数解析，已有 argparse

### 降级策略

**设计**：try-except 捕获 prompt-toolkit 创建失败，回退到 input()
**原因**：
- 管道/脚本环境无法创建 PromptSession
- 保证 TUI 在任何环境都能启动
- 真实终端获得完整体验，测试环境仍可用

## 手动测试清单

详见 `docs/tui/MANUAL_TEST.md`

### 快速验证

```powershell
# 1. 配置向导
python -m apps.tui

# 2. 命令补全和历史
python -m apps.tui --skip-wizard
# 然后输入 / 测试命令面板，↑↓ 测试历史

# 3. 交易看板和运行观测
python -m apps.tui --skip-wizard
/dashboard
/models list
/models select
/start --offline --max-count 2 --days 12
/run
/providers
```

## 下一步

1. 加固 `astock-tui` 任意目录启动体验
2. 增加后台任务进度轮询/实时刷新
3. 添加更多 Rich 组件（进度条、实时刷新、运行时间线）
4. 优化运行观测中的决策理由折叠和模型对比视图
5. 添加多语言支持
