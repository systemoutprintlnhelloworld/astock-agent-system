# 文档索引

本目录用于 GitHub 托管时展示项目文档。所有示例都使用占位符，不包含真实密钥。

在线文档站目标地址：https://systemoutprintlnhelloworld.github.io/astock-agent-system/

文档站使用 MkDocs Material 构建，并由 GitHub Actions 在 `main` 分支更新时自动部署到 GitHub Pages。

## 面向使用者

- [交付总结](DELIVERY_SUMMARY.md)：当前可用能力、最短运行路径、验证状态和外部服务状态。
- [使用者手册](USER_GUIDE.md)：安装、配置、启动看板、运行自动投资轮次。
- [在线运行手册](ONLINE_RUNBOOK.md)：在线数据、LLM bench、MongoDB/Redis、调度器 smoke 顺序。

## 面向开发者

- [开发者手册](DEVELOPER_GUIDE.md)：项目架构、模块边界、测试、开发约定。
- [GitHub 发布说明](GITHUB_PUBLISHING.md)：Git 初始化、远程仓库、推送、文档托管。
- [持久化开发计划](trellis-plan.md)：本轮交付计划、完成状态和后续增强方向。
- [现代化重构计划](modernization-plan.md)：Tauri/Next/FastAPI/WebSocket 重构目标、接口边界和验证门禁。

## 推荐阅读顺序

1. 想快速知道当前是否可交付：先读 [交付总结](DELIVERY_SUMMARY.md)。
2. 第一次使用：读 [使用者手册](USER_GUIDE.md)。
3. 要接入真实 Tushare / LLM：读 [在线运行手册](ONLINE_RUNBOOK.md)。
4. 要继续开发：读 [开发者手册](DEVELOPER_GUIDE.md)。
5. 要发布到 GitHub：读 [GitHub 发布说明](GITHUB_PUBLISHING.md)。
6. 要了解本轮交付范围：读 [持久化开发计划](trellis-plan.md)。
7. 要了解现代化桌面 UI 重构：读 [现代化重构计划](modernization-plan.md)。
