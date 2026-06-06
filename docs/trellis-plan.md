# 持久化开发计划

更新时间：2026-06-06

本计划记录当前交付批次的目标、完成状态和后续增强方向。所有配置示例均使用占位符，不包含真实密钥。

> 当前有效计划：本文件与 [现代化重构计划](modernization-plan.md)。工作区中没有 `a股llm系统现代化重构_efa1eeac.plan.md` 文件；该名称来自历史/外部计划引用，不是当前仓库内可执行的 Trellis 计划文件。

当前 Trellis 任务状态：任务系统中没有 pending / in_progress 任务；本轮现代化重构相关事项已落到本文档、`docs/modernization-plan.md`、`docs/technical/PRD_PHASE2.md` 和代码提交中。

## 1. 总目标

将项目交付为一个可直接本地使用、可在线接入、可公开托管文档的 A 股 LLM 多 Agent 模拟盘自动投资系统。

交付边界：

- 当前只做模拟盘，不接入真实下单。
- 每个 LLM/规则模型拥有独立虚拟账户。
- 系统支持自动投资轮次、止损检查、持仓和排行榜观测。
- 离线流程必须可用，在线流程必须可诊断。
- 真实 API key、Tushare token、Webhook 和 `.env` 不得入库。

## 2. 当前现代化重构批次

当前开发分支：`tauri-rewrite`。

本轮目标是把现有 Python CLI + Streamlit MVP 渐进升级为用户可一键启动的现代化桌面产品：Tauri 2.0 负责桌面壳和后续便携版，Next.js/React/TypeScript/Shadcn/Tailwind/Lucide 负责现代 UI，FastAPI + WebSocket 负责后端适配和实时事件，现有 `src/astock_agent_system` 继续作为业务核心。

本轮不删除已有 CLI、离线流程、在线 bench、调度器和 Streamlit 调试看板；它们继续作为回归验证和 fallback。现代化产品层优先实现：

- UI 配置中心和首次启动向导。
- 实时 Agent 流程图，包含节点状态和流动箭头。
- 可折叠决策日志，展示决策、动作、理由、风险和交易结果。
- 股票看板、模型排行榜、长期权益曲线和回撤指标。
- 动态保存配置和配置更新事件；进行中的任务只热加载安全参数，交易关键参数默认下一轮生效。

更详细的架构、接口边界、事件协议、风险和验证门禁见 [现代化重构计划](modernization-plan.md)。

## 3. 已完成任务

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| 替换 LLM 网关并验证在线流程 | 已完成 | `.env` 本地切换到可用 OpenAI-compatible 网关；`bench --list-models` 和 `gpt-5.4-mini` 单模型 smoke 通过；在线自动投资通过并触发同日幂等保护。 |
| 封装一键启动和调试入口 | 已完成 | 新增 `start.ps1` 和 `start.bat`，支持 `status`、`storage`、`offline`、`online`、`bench`、`dashboard`、`backend`、`frontend`、`modern-ui`、`scheduler`、`docs`。 |
| 搭建 GitHub Pages 文档站和自动部署 | 已完成 | 新增 MkDocs Material 文档站和 `.github/workflows/docs.yml`；仓库已转为 Public；Pages workflow 模式已启用。 |
| 创建 Cursor Hook 与项目 Skill 固化规范 | 已调整 | 新增项目 Skill 和可选 guard 脚本；按用户要求关闭自动 Shell 审批 Hook，避免命令反复人工批准。 |
| 更新持久化计划、文档与交付总结 | 已完成 | 本文件、交付总结、README、使用者/开发者/在线运行文档已同步更新。 |
| 验证、提交并推送本轮交付 | 已完成 | 测试、文档构建、密钥扫描、GitHub Pages 状态检查均通过；提交 `023d4ad` 已推送到 `main`，Pages workflow 已成功部署。 |
| 现代化重构计划与分支准备 | 已完成 | 已创建 `tauri-rewrite` 开发分支；新增 `docs/modernization-plan.md`，用于约束 Tauri/Next/FastAPI/WebSocket 重构方向；MkDocs strict build 与密钥扫描通过。 |
| FastAPI 后端适配层骨架 | 已完成首版 | 已新增 `apps/backend`，提供健康检查、脱敏配置、模型 bench、自动投资触发、React Flow 初始图、运行时配置保存、股票/决策/指标接口和 WebSocket 事件流。 |
| Next.js 现代化前端控制台首版 | 已完成 | 已将默认 create-next-app 页面替换为现代化控制台，包含 React Flow 流程图、设置中心、实时事件流、可折叠决策日志、股票看板、模型排行榜和 Recharts 长期曲线。 |
| Benchmark 架构修正 | 已完成 | 产品层统一为 Benchmark 模式：用户选择 N 个模型，每个模型驱动独立 8-Agent 系统和独立 `VirtualAccount`；不再区分“单 LLM / 多 LLM 模式”。 |
| Phase 2 透明化最小接口 | 已完成 | 已新增事件时间线、Agent 记忆只读查询、LLM 配置检测和 Agent 工具清单接口，并接入 modern-ui 的事件/智能体/设置页签。 |
| Git 结束流程自动推送 | 已完成 | `post-commit` 默认推送当前分支到 GitHub `origin`；如需临时跳过，可设置 `SKIP_AUTO_PUSH=1`。 |

## 4. 推荐一键运行路径

安装：

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
```

离线体验：

```powershell
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12
.\start.bat -Mode dashboard
.\start.bat -Mode backend -Port 8000
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 8000
```

在线 smoke：

```powershell
.\start.bat -Mode bench
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
.\start.bat -Mode online -Models "rule-baseline,gpt-5.4-mini" -MaxCount 3 -Days 24
```

文档预览：

```powershell
python -m pip install -e ".[docs]"
.\start.bat -Mode docs
```

当前产品测试顺序：

```powershell
# 1. 基础健康检查
.\start.bat -Mode status

# 2. 无密钥离线闭环，验证调度、Agent、模拟盘、持仓/排行榜数据
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker

# 3. 启动现代化 UI，浏览器访问 http://127.0.0.1:3000
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 8000

# 4. 在 UI 内重点验证
# - 总览：健康状态、候选股票、下一步操作
# - 流程：React Flow 节点状态和实时事件
# - 事件：事件时间线和手动轮询
# - 智能体：Agent 工具清单和按模型隔离记忆
# - 设置：LLM 配置检测、模型列表、防呆提示
```

## 5. 当前在线状态

- LLM base URL 需要使用带 `/v1` 的 OpenAI-compatible 地址。
- 模型列表接口已验证可用。
- `gpt-5.4-mini` 已通过 JSON smoke。
- 部分模型可能因分组、额度或渠道限制不可用；这属于网关账户状态，不是本地代码错误。
- 推荐在 `SCHEDULER_MODELS` 中保留 `rule-baseline`，并只加入 bench 通过的 LLM 模型。

## 6. 当前需要用户维护的信息

本项目目前不再需要额外申请信息才能本地运行。用户只需要在本地 `.env` 中维护：

1. Tushare token。
2. LLM gateway base URL 和 API key。
3. 如需邮件/IM 推送，后续补充 SMTP 或 webhook 配置。

以上信息不得写入 Git，也不得出现在文档示例中。

## 7. 质量门禁

本轮已运行并通过：

```powershell
python -m pytest
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
python -m mkdocs build --strict
git status --short
```

同时已执行密钥扫描，确认真实 key、token、`.env`、日志和运行产物没有进入 Git 暂存区。GitHub Actions `Deploy documentation` 工作流已成功完成，在线文档站可访问。

## 8. Phase 2 当前完成状态

本节只记录当前有效交付状态，不再把未来设想写成未完成 to-do，避免和 Trellis 任务系统混淆。

| 方向 | 当前状态 | 已落地位置 | 后续增强方向 |
| --- | --- | --- | --- |
| 持续学习系统 | 已完成最小可交付 | `src/astock_agent_system/agent_memory.py`、`GET /api/agents/{agent_id}/memory`、modern-ui 智能体页签 | 增加案例评分、周总结、PortfolioManager 主动检索 |
| 事件驱动系统 | 已完成最小可交付 | `src/astock_agent_system/event_timeline.py`、`/api/events/timeline`、`/api/events/poll`、modern-ui 事件页签 | 接入真实 AkShare 新闻、Tushare 公告和重大事件实时路由 |
| Agent 工具与知识库 | 已完成清单化展示 | `GET /api/agents/tools`、modern-ui 智能体页签、`docs/technical/PRD_PHASE2.md` | 将反复工作固化为更多项目 Skills，记录工具调用明细 |
| 用户体验增强 | 已完成主要入口 | tab 化 UI、设置目录跳转、LLM 配置检测、自动模型列表读取、事件时间线 | 深化 ChatGPT-like 三层折叠日志和虚拟滚动 |
| 开发规范强化 | 已完成当前门禁 | `.husky/pre-commit`、`.husky/post-commit`、`.husky/post-merge` | 如需更严格门禁，再增加 commit-msg 或格式化检查 |

未来增强项不作为当前交付阻塞项；进入新一轮开发前，应通过 Trellis 新建任务并在本文件中同步为新的“当前执行计划”。

---

## 9. 风险与依赖

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 记忆检索性能 | 高 | MongoDB 创建索引 + Redis 缓存热数据 |
| 事件轮询频率限制 | 中 | 实现指数退避 + 缓存去重 |
| Git Hook 失败阻塞提交 | 中 | 提供 `--no-verify` 绕过选项 |
| 前端日志数据量过大 | 中 | 虚拟滚动 + 懒加载 |
| LLM API 费用 | 中 | 支持离线模式 + rule-baseline 基准 |

---

## 10. 相关文档

- [技术 PRD (Phase 2)](technical/PRD_PHASE2.md) - 持续学习与事件驱动系统详细设计
- [同类项目对比](technical/COMPARISON.md) - TradingAgents、TradingGroup 等项目对比
- [系统架构](technical/ARCHITECTURE.md) - 整体架构和 Agent 协作
- [流程与时序](technical/FLOWS.md) - 启动流程和自动投资流程
- [设计决策](technical/DESIGN_DECISIONS.md) - UI选型和透明化实现
- [需求映射](technical/USER_NEEDS_MAPPING.md) - 用户场景到代码位置的映射
