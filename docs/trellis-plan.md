# 持久化开发计划

更新时间：2026-06-03

本计划记录当前交付批次的目标、完成状态和后续增强方向。所有配置示例均使用占位符，不包含真实密钥。

## 1. 总目标

将项目交付为一个可直接本地使用、可在线接入、可公开托管文档的 A 股 LLM 多 Agent 模拟盘自动投资系统。

交付边界：

- 当前只做模拟盘，不接入真实下单。
- 每个 LLM/规则模型拥有独立虚拟账户。
- 系统支持自动投资轮次、止损检查、持仓和排行榜观测。
- 离线流程必须可用，在线流程必须可诊断。
- 真实 API key、Tushare token、Webhook 和 `.env` 不得入库。

## 2. 已完成任务

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| 替换 LLM 网关并验证在线流程 | 已完成 | `.env` 本地切换到可用 OpenAI-compatible 网关；`bench --list-models` 和 `gpt-5.4-mini` 单模型 smoke 通过；在线自动投资通过并触发同日幂等保护。 |
| 封装一键启动和调试入口 | 已完成 | 新增 `start.ps1` 和 `start.bat`，支持 `status`、`storage`、`offline`、`online`、`bench`、`dashboard`、`scheduler`、`docs`。 |
| 搭建 GitHub Pages 文档站和自动部署 | 已完成 | 新增 MkDocs Material 文档站和 `.github/workflows/docs.yml`；仓库已转为 Public；Pages workflow 模式已启用。 |
| 创建 Cursor Hook 与项目 Skill 固化规范 | 已调整 | 新增项目 Skill 和可选 guard 脚本；按用户要求关闭自动 Shell 审批 Hook，避免命令反复人工批准。 |
| 更新持久化计划、文档与交付总结 | 已完成 | 本文件、交付总结、README、使用者/开发者/在线运行文档已同步更新。 |
| 验证、提交并推送本轮交付 | 已完成 | 测试、文档构建、密钥扫描、GitHub Pages 状态检查均通过；提交 `023d4ad` 已推送到 `main`，Pages workflow 已成功部署。 |

## 3. 推荐一键运行路径

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

## 4. 当前在线状态

- LLM base URL 需要使用带 `/v1` 的 OpenAI-compatible 地址。
- 模型列表接口已验证可用。
- `gpt-5.4-mini` 已通过 JSON smoke。
- 部分模型可能因分组、额度或渠道限制不可用；这属于网关账户状态，不是本地代码错误。
- 推荐在 `SCHEDULER_MODELS` 中保留 `rule-baseline`，并只加入 bench 通过的 LLM 模型。

## 5. 当前需要用户维护的信息

本项目目前不再需要额外申请信息才能本地运行。用户只需要在本地 `.env` 中维护：

1. Tushare token。
2. LLM gateway base URL 和 API key。
3. 如需邮件/IM 推送，后续补充 SMTP 或 webhook 配置。

以上信息不得写入 Git，也不得出现在文档示例中。

## 6. 质量门禁

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

## 7. 后续增强方向

这些不是当前交付阻塞项：

- 收益曲线、止损时间线、自动投资事件流。
- 多日模型排行榜和长期回放。
- 更真实的撮合、滑点和成交模型。
- 邮件/IM 推送配置界面。
- FastAPI/React 独立 Dashboard。
- 半自动或实盘交易前的人工确认、权限隔离、审计日志和熔断机制。
