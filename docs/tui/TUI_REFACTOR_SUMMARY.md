# TUI 改造总结

更新时间：2026-06-09

## 已完成的改造

### 1. 交互式配置向导 ✓

**文件**：`apps/tui/config_wizard.py`, `apps/tui/app.py`

**改进**：
- 使用 **InquirerPy** 提供交互式表单（↑↓ 导航，Enter 确认）
- 数据模式和 LLM 请求档位使用下拉菜单选择
- 密钥字段使用 `inquirer.secret()` 不回显
- 使用 **Rich Table** 渲染配置摘要（密钥显示为 `[已设置]`）
- 确认保存使用 `inquirer.confirm()`
- 支持 Ctrl+C 中断向导

**测试**：
- `test_wizard_interactive.py`：验证数据结构和 Rich 渲染 ✓
- 真实终端手动测试：`python -m apps.tui`

### 2. Prompt-toolkit 命令补全和历史 ✓

**文件**：`apps/tui/prompt.py`, `apps/tui/app.py`

**改进**：
- 使用 **prompt-toolkit** 提供 Tab 补全
- 自定义 `SlashCommandCompleter` 支持嵌套补全（命令 → 子命令 → 参数）
- 支持历史记录（↑↓ 导航，Ctrl+R 搜索）
- 历史持久化到 `data/runtime/tui_history.txt`
- **降级方案**：非 TTY 环境自动回退到普通 input()

**补全覆盖**：
- 根命令：`/help`, `/status`, `/config`, `/models`, `/workflow`, `/start`, `/dashboard`, `/agent` 等
- 子命令：`/config show|test-llm`, `/dashboard overview|providers|rankings` 等
- 参数：`/start --offline|--models|--max-count|--days|--foreground`

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

**现状**：已实现，`/models` 命令从 `/api/models` 获取模型列表

## 待完成的改造

### 1. 注册全局命令

**目标**：用户可以在任意目录运行 `astock-tui` 启动 TUI

**实现**：
```toml
# pyproject.toml
[project.scripts]
astock-agent = "astock_agent_system.cli:main"
astock-tui = "apps.tui.app:run_tui"  # 新增
```

### 2. 更新文档

**需要更新**：
- [x] `docs/tui/MANUAL_TEST.md`：手动测试指南
- [ ] `README.md`：添加 TUI 使用说明
- [ ] `docs/trellis/IMPLEMENT.md`：更新实现状态
- [ ] `DOCUMENTATION_MAP.md`：添加 TUI 文档索引

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
# 然后按 Tab 测试补全，↑↓ 测试历史

# 3. Rich 输出
python -m apps.tui --skip-wizard
/status
/models
/providers
```

## 下一步

1. 注册全局 `astock-tui` 命令
2. 更新项目文档
3. 添加更多 Rich 组件（进度条、实时刷新）
4. 实现后台任务进度可视化
5. 添加多语言支持
