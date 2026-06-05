# 架构理解修正任务

**创建时间**：2026-06-06  
**状态**：需要修正文档中的错误说法

---

## ✅ 正确理解

### 系统只有一种运行模式：Benchmark 模式

**核心理念**：
- ❌ **错误**：系统有"单LLM模式"和"多LLM模式"两种模式需要切换
- ✅ **正确**：系统只有 **Benchmark 模式**，用户选择 N 个模型（N ≥ 1）

**用户操作**：
```
1. 用户启动系统
2. 选择模型列表：[rule-baseline, gpt-4o, claude-3.5]
3. 系统并行运行 3 个独立的 Agent 系统
   - 每个模型 = 1 个完整的 8 Agent 系统
   - 每个模型 = 1 个独立的 VirtualAccount
4. 最后生成 Benchmark 排行榜
```

**N = 1 的情况**：
- 用户只选 `["rule-baseline"]`
- 系统运行 1 个 Agent 系统
- 也是 Benchmark 模式，只是只有 1 个账户
- **不是"单LLM模式"**，没有所谓的"模式切换"

---

## 🔧 需要修正的文档

### 1. `docs/technical/ARCHITECTURE.md`

**需要删除的章节**：
- 第 3 章：`## 3. 单LLM vs 多LLM架构`
  - 3.1 架构对比
  - 3.2 单LLM模式流程
  - 3.3 多LLM模式流程
  - 3.4 如何切换

**需要替换为**：
```markdown
## 3. Benchmark 架构

系统只有一种运行模式：Benchmark 模式。

### 3.1 核心理念
- 用户选择 N 个模型（N ≥ 1）
- 系统并行运行 N 个独立的 Agent 系统
- 每个模型驱动一个完整的 8 Agent + VirtualAccount

### 3.2 架构图
（展示 MultiAgentOrchestrator 如何管理多个独立系统）

### 3.3 代码实现
（展示 orchestrator.run_competition() 的核心逻辑）

### 3.4 持仓恢复机制
（展示如何从 MongoDB 恢复每个账户的持仓）
```

**文件位置**：`D:\研究生\项目\项目2-A股LLM投资系统\docs\technical\ARCHITECTURE.md` 第 210-280 行

---

### 2. `docs/technical/DESIGN_DECISIONS.md`

**需要删除的章节**：
- 第 5 章：`## 5. 单LLM vs 多LLM 架构切换`
  - 5.1 为什么需要两种模式
  - 5.2 切换方式

**需要替换为**：
```markdown
## 5. Benchmark 模式设计

系统只有一种运行模式：Benchmark 模式。

### 5.1 为什么只有一种模式

- 简化用户理解：不需要学习"模式切换"
- 统一代码路径：所有运行都走 MultiAgentOrchestrator
- N = 1 时自动退化为单个系统，无需特殊处理

### 5.2 用户如何选择模型

**modern-ui**：
用户在设置页选择模型列表，点击"启动运行"

**CLI**：
```bash
python -m astock_agent_system.cli scheduler run-auto-investment \
  --models "rule-baseline,gpt-4o" \
  --max-count 5
```
```

**文件位置**：`D:\研究生\项目\项目2-A股LLM投资系统\docs\technical\DESIGN_DECISIONS.md` 第 371-400 行

---

### 3. `docs/technical/FLOWS.md`

**需要检查和修正的内容**：
- 删除所有"单LLM模式"相关描述
- 改为"用户选择 N 个模型"
- 强调"每个模型 = 一个独立的 Agent 系统"

---

### 4. `README.md` 和 `USER_GUIDE.md`

**需要检查和修正的内容**：
- 删除"单LLM vs 多LLM"相关说法
- 改为"选择模型进行 Benchmark"
- 用户友好的语言：不要说"模式"，说"选择几个模型"

---

## 🚀 Tauri 打包说明

### 当前状态（临时方案）

```
用户运行：start.bat -Mode modern-ui
  ↓
1. 启动 FastAPI 后端（Python）
2. 启动 Next.js 前端（Node.js）
3. 打开浏览器
```

**问题**：
- 需要手动运行 bat 文件
- 需要安装 Python 和 Node.js
- 不是真正的桌面 App

---

### 目标状态（Tauri）

```
用户双击：astock-agent-system.exe
  ↓
Tauri 主进程启动（Rust）
  ↓
  ├─ Sidecar: 启动嵌入式 Python FastAPI
  │   └─ 不依赖系统 Python
  │
  └─ WebView: 加载 Next.js 静态文件
      └─ 已打包，不需要 Node.js
  ↓
显示桌面窗口
```

**优势**：
- ✅ 用户只需双击 `.exe`
- ✅ 无需安装 Python / Node.js
- ✅ 单个文件，真正的桌面 App
- ✅ 跨平台：Windows / macOS / Linux

---

## 📝 下一步操作

### 方式 1：手动修改（推荐）

1. 打开 `docs/technical/ARCHITECTURE.md`
2. 找到第 210 行左右的 `## 3. 单LLM vs 多LLM架构`
3. 删除整个第 3 章
4. 复制本文档中"需要替换为"的内容粘贴上去
5. 对 DESIGN_DECISIONS.md 做同样操作
6. 提交并推送

### 方式 2：使用查找替换（批量）

使用 VS Code 的全局查找替换：
- 查找：`单LLM模式`
- 替换：`Benchmark 模式（N=1时）`
- 查找：`多LLM模式`
- 替换：`Benchmark 模式`
- 查找：`单LLM vs 多LLM`
- 替换：`Benchmark`

---

## ✅ 新增的 Git Hook

**文件**：`.husky/post-merge`

**功能**：
- 在 `git pull` 或 `git merge` 后自动运行
- 检查代码文件是否有变更
- 如果有，提醒检查文档是否需要更新

**示例输出**：
```
📚 Checking documentation consistency...
  ⚠️  Code files changed, please check if documentation needs update:
    - src/astock_agent_system/orchestrator/multi_agent_orchestrator.py
    - apps/backend/app.py

  📖 Documentation checklist:
    - docs/technical/ARCHITECTURE.md (if architecture changed)
    - docs/technical/FLOWS.md (if flows changed)
    - docs/technical/USER_NEEDS_MAPPING.md (if API changed)
    - docs/USER_GUIDE.md (if user-facing features changed)

  ✅ Check complete!
```

---

## 📊 已完成的工作

1. ✅ 创建了 `.husky/post-merge` hook
2. ✅ 识别了需要修正的文档位置
3. ✅ 准备了正确的内容替换方案
4. ✅ 提交了初步修正（包含 post-merge hook）

---

## 🎯 待办事项

- [ ] 手动修正 `ARCHITECTURE.md` 第 3 章
- [ ] 手动修正 `DESIGN_DECISIONS.md` 第 5 章
- [ ] 检查 `FLOWS.md` 并修正相关说法
- [ ] 检查 `README.md` 和 `USER_GUIDE.md`
- [ ] 提交最终修正：`git commit -m "fix: remove single-LLM vs multi-LLM mode concept"`
- [ ] 推送到远程
