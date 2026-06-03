# A股 LLM 多 Agent 自动投资系统文档

欢迎阅读本项目的在线文档。本系统面向 A 股模拟盘研究验证，会动态筛选股票，让多个 LLM/规则账户分别管理独立虚拟资金，并在观测看板中展示排行榜、持仓、盈亏、候选股票、舆情和风险摘要。

!!! warning "模拟盘声明"
    当前系统只做模拟盘和研究验证，不会真实下单，也不构成任何投资建议。

## 快速入口

- [交付总结](DELIVERY_SUMMARY.md)：当前可用能力、最短运行路径、验证状态和外部服务状态。
- [使用者手册](USER_GUIDE.md)：安装环境、配置 `.env`、一键启动、自动投资和看板使用。
- [在线运行手册](ONLINE_RUNBOOK.md)：在线数据源、LLM 网关、MongoDB/Redis 和 smoke 顺序。
- [开发者手册](DEVELOPER_GUIDE.md)：架构、模块边界、测试和开发约定。
- [GitHub 发布说明](GITHUB_PUBLISHING.md)：Git/GitHub、Pages 文档站和自动部署说明。
- [持久化开发计划](trellis-plan.md)：本轮交付计划、完成状态和后续增强方向。

## 最短体验路径

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12
.\start.bat -Mode dashboard
```

在线 LLM smoke：

```powershell
.\start.bat -Mode bench
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
```

## 文档站维护

本页面由 MkDocs Material 构建。推送到 `main` 后，GitHub Actions 会自动构建并部署到 GitHub Pages。

本地预览：

```powershell
python -m pip install -e ".[docs]"
.\start.bat -Mode docs
```
