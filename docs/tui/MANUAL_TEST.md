# TUI 手动测试指南

更新时间：2026-06-09

## 测试环境要求

- Windows Terminal / PowerShell / CMD（真实终端，不是脚本环境）
- 后端已启动：`.\start.bat -Mode backend -Port 18080`

## 测试步骤

### 1. 配置向导交互测试

```powershell
python -m apps.tui
```

**预期效果**：
- 显示 Rich 样式的配置向导面板
- 使用 InquirerPy 交互式表单
- ↑↓ 键导航，空格选择/取消，Enter 确认
- 数据模式支持单选（offline/online）
- 数据源 provider chain 支持多选，不再手打逗号列表
- 默认 LLM 模型从后端模型列表模糊选择
- 比赛模型不在初始化向导中填写，改为运行前用 `/models select` 或 `/models set` 选择
- LLM 请求档位支持下拉选择
- 密钥字段不回显
- 完成后显示 Rich 表格汇总（密钥显示为 `[已设置]`）
- 确认保存时使用 InquirerPy confirm

**测试点**：
- [ ] 配置向导启动成功
- [ ] 下拉菜单交互正常
- [ ] provider chain 可用空格多选并用 Enter 确认
- [ ] 默认模型可从后端模型列表模糊过滤选择
- [ ] 初始化流程不会要求填写比赛模型列表
- [ ] 密钥输入不回显
- [ ] Rich 表格渲染正常
- [ ] 配置保存成功

### 2. 命令补全测试

```powershell
python -m apps.tui --skip-wizard
```

在 `astock>` 提示符下测试：

**测试点**：
- [ ] 输入 `/` → 立即在输入框下方显示所有命令和说明，不需要先按 Tab
- [ ] 输入 `/d` → 候选列表过滤到 `/dashboard` 等匹配项，并显示说明
- [ ] 输入 `/start ` → 显示 `--offline`, `--models` 等参数和说明
- [ ] 输入 `/config ` → 显示 `show`, `test-llm`
- [ ] 输入 `/dashboard ` → 显示 `trading`, `run`, `rankings`, `decisions`, `status` 等面板名称
- [ ] 输入 `/models set g` → 显示后端模型列表中的匹配模型
- [ ] 按 ↑ → 显示上一条命令
- [ ] 按 ↓ → 显示下一条命令
- [ ] Ctrl+R → 启动历史搜索

### 3. Rich 输出美化测试

在 TUI 中运行命令：

```bash
/status
/models
/models select
/providers
/dashboard
/dashboard rankings
/start --offline --max-count 2 --days 12
/run
```

**预期效果**：
- Rich 样式的彩色输出
- 附件路径用 `[cyan]` 显示
- 成功消息用 `[green]` 显示
- 警告消息用 `[yellow]` 显示
- 错误消息用 `[red]` 显示

**测试点**：
- [ ] 彩色输出正常
- [ ] 表格/面板渲染正常
- [ ] 中文显示无乱码
- [ ] `/dashboard` 默认显示交易看板，而不是状态总览
- [ ] `/start` 提交后立即显示运行观测视图，包含 run_id、状态、排行、持仓/交易和决策日志
- [ ] `/run` 可以刷新当前/最近一次运行观测视图
- [ ] 每次关键命令后主界面清屏重绘，旧配置摘要和旧命令输出不会继续堆叠遮挡输入

### 3.1 运行观测和交易看板测试

在后端已启动的真实终端中运行：

```powershell
python -m apps.tui --skip-wizard
```

依次执行：

```bash
/models list
/models select
/dashboard
/start --offline --max-count 2 --days 12
/run
/dashboard run
/dashboard status
```

**预期效果**：
- `/models list` 从后端刷新模型列表；`/models select` 打开多选列表，空格选择/取消，Enter 确认
- `/dashboard` 默认进入“交易看板”，展示候选、持仓、交易和盈亏相关信息
- `/start` 不只打印 JSON，而是切到“运行观测”视图
- `/run` 和 `/dashboard run` 可以重新查看 run 状态、排行榜、持仓/交易和决策原因
- `/dashboard status` 才显示后端连接、上下文和 todo 状态

### 4. 历史持久化测试

1. 启动 TUI 并运行几条命令
2. 输入 `/exit` 退出
3. 再次启动 TUI
4. 按 ↑ 键查看历史

**预期效果**：
- 历史命令保存在 `data/runtime/tui_history.txt`
- 重启后历史依然可用

**测试点**：
- [ ] 历史文件创建
- [ ] 历史记录持久化
- [ ] 重启后历史可访问

## 已知限制

1. **InquirerPy/prompt-toolkit 需要真实终端**：不能在 PowerShell 脚本中通过管道模拟输入，必须手动交互测试
2. **Windows Terminal 推荐**：对彩色输出和交互式组件支持最好
3. **Git Bash 可能有兼容性问题**：建议使用 PowerShell 或 CMD

## 自动化测试覆盖

以下模块有自动化测试：
- `test_wizard_interactive.py`：配置向导数据结构和 Rich 渲染
- `test_prompt_toolkit.py`：命令补全逻辑

以下必须手动测试：
- InquirerPy 交互式表单
- prompt-toolkit 历史和补全的真实终端交互
- Rich 彩色输出的实际显示效果
