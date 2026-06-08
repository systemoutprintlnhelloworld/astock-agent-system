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
- ↑↓ 键导航，Enter 确认
- 数据模式支持下拉选择（offline/online）
- LLM 请求档位支持下拉选择
- 密钥字段不回显
- 完成后显示 Rich 表格汇总（密钥显示为 `[已设置]`）
- 确认保存时使用 InquirerPy confirm

**测试点**：
- [ ] 配置向导启动成功
- [ ] 下拉菜单交互正常
- [ ] 密钥输入不回显
- [ ] Rich 表格渲染正常
- [ ] 配置保存成功

### 2. 命令补全测试

```powershell
python -m apps.tui --skip-wizard
```

在 `astock>` 提示符下测试：

**测试点**：
- [ ] 输入 `/` 按 Tab → 显示所有命令
- [ ] 输入 `/st` 按 Tab → 补全为 `/start` 或 `/status`
- [ ] 输入 `/start ` 按 Tab → 显示 `--offline`, `--models` 等参数
- [ ] 输入 `/config ` 按 Tab → 显示 `show`, `test-llm`
- [ ] 输入 `/dashboard ` 按 Tab → 显示所有面板名称
- [ ] 按 ↑ → 显示上一条命令
- [ ] 按 ↓ → 显示下一条命令
- [ ] Ctrl+R → 启动历史搜索

### 3. Rich 输出美化测试

在 TUI 中运行命令：

```bash
/status
/models
/providers
/dashboard rankings
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
