# Phase 1 - PRD：AStock 现代化桌面 Benchmark 系统

更新时间：2026-06-07

本文档是 Trellis Phase 1 的产品需求文件。当前有效计划入口仍是 `docs/trellis-plan.md` 和 `docs/modernization-plan.md`；本文用于让下一位 AI 快速理解“为什么做、做给谁、验收什么”。

## 1. 产品定位

AStock 是 A 股 LLM 多 Agent 模拟盘 Benchmark 系统。用户选择一个或多个模型，每个模型驱动一套完整独立的 Agent 投资系统，通过虚拟账户收益、回撤、交易次数和持仓表现比较模型作为投资 Agent 驱动器的效果。

## 2. 用户画像

| 用户 | 目标 | 痛点 |
| --- | --- | --- |
| 项目所有者 / 研究者 | 验证不同 LLM 驱动投资 Agent 的表现 | 开发过程黑箱、文档分散、难判断当前做到哪一步 |
| 普通体验用户 | 双击桌面应用完成配置和观察 | 不懂命令行、端口冲突、连接状态看不懂 |
| 后续 AI / 开发者 | 接手继续开发 GUI、事件、记忆、桌面交付 | 不知道有效计划、最新代码状态、验证命令和安全红线 |

## 3. 核心需求

### 3.1 Benchmark 运行

- 用户配置模型列表。
- 每个模型独立运行完整 Agent 链路。
- 每个模型有独立 `VirtualAccount`、持仓、交易、PnL、记忆作用域。
- 排行榜按收益、回撤、胜率、交易次数展示。

### 3.2 透明化 Agent 执行

- React Flow 展示 Agent 流程图。
- 事件时间线展示交易时间、系统事件、新闻/公告输入。
- 决策日志支持摘要 + 折叠详情。
- 工具、数据源、技能、记忆案例可查询。

### 3.3 桌面交付

- 推荐最终用户使用 Tauri `.exe` 或 NSIS 安装包。
- `start.bat` / `start.ps1` 保留为开发、验证、调试入口。
- 后端默认端口段为 `18080..18100`，兼容旧 `8000..8020` 健康 AStock 后端。
- Next dev 预览默认使用 webpack，Turbopack 仅用于复现问题。

### 3.4 开发可交接

- Trellis 文档必须分为 Phase 0 grill-me、Phase 1 PRD/design/implement、handoff。
- 每次代码/桌面/脚本/配置/hooks 变更必须同步文档。
- 每次开发结束必须验证、commit、push。

## 4. 非目标

- 不接入真实下单。
- 不在 UI、日志、文档、Git 中泄露真实 API Key、Tushare token、Webhook、`.env`。
- 不把 N=1 设计成单独产品模式。
- 不在下一轮优先引入复杂知识库或大型重构业务核心。

## 5. 验收标准

| 方向 | 当前标准 |
| --- | --- |
| 离线可用 | `.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker` 可跑通。 |
| 现代 UI | `.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080` 可启动，并在端口冲突时打印进程信息确认处理。 |
| 桌面交付 | `desktop-sidecar`、`build:desktop`、`desktop-build` / `desktop-release` 可生成可运行产物。 |
| 质量门禁 | `.\start.bat -Mode delivery-check` 通过。 |
| 文档交接 | `DOCUMENTATION_MAP.md` 能指向有效计划、handoff、技术文档。 |
| Git 闭环 | 本轮 commit 推送到 `origin/tauri-rewrite`。 |

## 6. 当前阻塞 / 需用户维护的信息

本地开发和离线验证无新增申请项。在线运行仍需用户在本地 `.env` 中维护：

1. Tushare token。
2. LLM gateway base URL 和 API key。
3. 可选 SMTP/Webhook。

不得把这些信息交给下一位 AI 文档化或提交。
