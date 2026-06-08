# 使用者手册

本手册面向第一次运行系统的使用者。当前系统是模拟盘自动投资系统：它会自动筛选股票、让多个 LLM/规则账户分别管理虚拟资金、记录模拟交易和止损检查，并在 Streamlit 观测看板里展示结果。

> 当前不会真实下单，也不构成投资建议。请只用于学习、研究和模拟盘验证。

在线文档站：https://systemoutprintlnhelloworld.github.io/astock-agent-system/

## 1. 安装环境

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[all]"
python -m astock_agent_system.cli --help
```

如果只想先离线体验，也可以不配置任何在线密钥。

## 2. 准备本地配置

复制示例配置：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`。不要把 `.env` 上传到 GitHub。

最小离线配置：

```env
DATA_MODE=offline
SMART_SEARCH_ENABLED=false
SCHEDULER_MODELS=rule-baseline
```

在线运行需要补充：

```env
DATA_MODE=online
TUSHARE_TOKEN=your-tushare-token
LLM_BASE_URL=https://your-gateway.example/v1
LLM_API_KEY=your-api-key
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini
```

## 3. 启动 MongoDB 和 Redis

模拟盘排行榜、持仓快照、交易记录需要 MongoDB；缓存需要 Redis。

```powershell
docker compose up -d
python -m astock_agent_system.cli storage status --strict
```

看到 MongoDB 和 Redis 都是 `connection: ok` 后，再继续运行自动投资。

## 4. 离线验证主流程

如果你还没配置在线数据和 LLM，先跑离线流程：

```powershell
python -m astock_agent_system.cli config
python -m astock_agent_system.cli run-daily --offline --max-count 3 --days 24
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12
```

离线模式会使用 `data/samples/stocks.json`，适合确认安装、界面和模拟盘逻辑能跑通。

也可以使用一键入口：

```powershell
.\start.bat -Mode status
.\start.bat -Mode offline -MaxCount 1 -Days 12
```

## 5. 检查 LLM 模型

配置 `LLM_BASE_URL` 和 `LLM_API_KEY` 后，先查看模型列表：

```powershell
python -m astock_agent_system.cli bench --list-models
```

再选一个便宜或轻量模型做单模型测试：

```powershell
python -m astock_agent_system.cli bench --models "gpt-5.4-mini" --limit 1
```

等价的一键入口：

```powershell
.\start.bat -Mode bench
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
```

如果返回 `status: ok`，说明模型调用可用。若返回 `partial` 或 `error`，请看输出里的 `next_steps`。

## 6. 在线运行自动投资

在线模式不加 `--offline`：

```powershell
python -m astock_agent_system.cli scheduler run-auto-investment --models "rule-baseline,gpt-5.4-mini" --max-count 3 --days 24
```

等价的一键入口：

```powershell
.\start.bat -Mode online -Models "rule-baseline,gpt-5.4-mini" -MaxCount 3 -Days 24
```

说明：

- `rule-baseline` 是规则基线账户，不依赖 LLM。
- 每个 LLM 模型会拥有独立虚拟账户。
- 同一交易日重复运行时，系统会读取已有快照并跳过重复交易，避免同一天重复买入。
- 结果会写入 MongoDB，Streamlit 看板可以读取。

## 7. 启动 Streamlit 观测看板

```powershell
streamlit run src/astock_agent_system/ui/streamlit_app.py
```

等价的一键入口：

```powershell
.\start.bat -Mode dashboard
```

打开后重点看“观测看板”：

- 模型账户排行榜：哪个模型的虚拟账户收益更好。
- 当前持仓：股票代码、股数、当前价、浮动盈亏。
- 执行状态：当天是否已经执行，是否因幂等保护跳过。
- 潜力股票：候选股票、动作、系统把握、舆情评分、风控评分。

## 8. 启动现代控制台

当前已经提供首版 Next.js 现代控制台，可直接联动 FastAPI 后端查看流程图、实时事件流、可折叠决策日志、股票看板、排行榜和长期曲线：

```powershell
.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080
```

启动后打开：

- `http://127.0.0.1:3000`：现代控制台首页。

新版控制台已经改成标签页布局，建议按这个顺序使用：

- `总览`：先确认后端连接、最近轮次和模型排行榜预览。
- `流程`：观察多 Agent 流程图、节点状态和动画箭头。
- `表现`：查看权益曲线、长期收益和模型排行榜。
- `事件`：查看系统事件、数据源状态、新闻/公告输入如何进入 Agent 输入流；可点击手动轮询事件。
- `日志`：看可折叠决策卡和实时事件流。
- `股票`：切换当前持仓、候选股票和交易记录。
- `智能体`：查看每个 Agent 的工具、数据源、技能，以及按模型账户隔离的历史记忆入口。
- `设置`：通过左侧目录快速跳转到数据源、LLM、组合、风控和调度配置。

如果你是第一次上手，建议先看 `总览` 页里的：

- `开箱检查清单`：确认后端、WebSocket、Tushare Token、API Key 和比赛模型是否已经准备好。
- `连接诊断` / `连接判定`：查看当前配置后端 URL、已解析后端 URL、WebSocket URL、HTTP health 状态、WS 状态、最近错误、候选端口探测结果和下一步排障建议。
- `首次启动向导`：按“数据源 -> LLM -> 保存配置 -> 启动离线轮次”的顺序一步步完成首轮验证。

如果前端或后端端口已经被其他程序占用，或者同一个 `apps/frontend` 目录下已经有旧的 Next.js dev 进程在运行，`start.bat -Mode modern-ui` 现在会：

1. 在命令行里显示占用该端口的 PID、进程名、路径和命令行。
2. 询问你是否要终止该进程。
3. 在确认后自动释放端口，再继续拉起后端和前端。

现代控制台默认使用 Next.js 的 webpack dev server，以避开 Next 16 Turbopack 在 Windows 本地缓存损坏时可能出现的 `range start index ... out of range` panic。如果你看到错误日志路径来自其他项目，例如 `项目1-审稿agent系统\frontend\.next-gui`，说明当前浏览器访问的不是本项目的 modern UI，而是另一个项目占用了前端端口；请在启动脚本提示时确认终止该进程，或换一个 `-Port`。

此外，一键启动会先等待后端健康检查通过，再启动前端，避免出现“前端先打开但后端还没接上”的情况。

如果页面仍显示 WebSocket 未连接或无法获取后端数据，请先打开 `总览 -> 连接诊断`：

- `HTTP 健康检查` 为 `ok` 但 `WebSocket 状态` 未连接：优先检查安全软件、代理或浏览器是否拦截 `ws://127.0.0.1:<port>/ws/events`。
- `候选后端探测` 显示 `非 AStock 后端`：说明该端口有其他服务响应，但 `/api/health` 不是本项目后端；请停止旧项目或用 `NEXT_PUBLIC_BACKEND_URL` 指向正确端口后重启前端。
- `候选后端探测` 显示网络错误或超时：请确认 `.\start.bat -Mode backend -Port 18080` 或 `.\start.bat -Mode modern-ui -Port 3000 -BackendPort 18080` 仍在运行。
- `最近错误` 会显示 HTTP 状态、错误类型和最近候选 URL，方便区分“后端没启动”“端口被旧项目占用”“WebSocket 被拦截”。

如果只想单独检查后端接口，也可以单独启动：

```powershell
.\start.bat -Mode backend -Port 18080
```

启动后可访问：

- `http://127.0.0.1:18080/api/health`：健康检查。
- `http://127.0.0.1:18080/api/config`：脱敏后的当前配置。
- `http://127.0.0.1:18080/api/data/providers`：provider chain、适配能力和缺失凭证诊断。
- `http://127.0.0.1:18080/api/agents/flow`：前端流程图节点和动画边。
- `http://127.0.0.1:18080/api/agents/descriptors`：Agent Markdown 描述符列表。
- `http://127.0.0.1:18080/api/agents/learning/status`：Agent Markdown 学习进度。
- `http://127.0.0.1:18080/api/agents/learning/suggestions`：最近一次人工审查学习建议。
- `http://127.0.0.1:18080/api/events/timeline`：事件时间线。
- `http://127.0.0.1:18080/api/agents/tools`：Agent 工具、数据源和技能清单。
- `http://127.0.0.1:18080/api/decisions`：结构化决策日志。
- `http://127.0.0.1:18080/api/stocks/board`：持仓、候选股和交易记录。
- `http://127.0.0.1:18080/api/metrics/rankings`：模型排行榜。
- `ws://127.0.0.1:18080/ws/events`：实时事件 WebSocket。

也可以在现代控制台的 `设置 -> LLM` 中点击“检测 LLM 配置”，系统会检查当前表单里的网关、API Key 状态并尝试获取模型列表。检测响应不会回显真实 API Key。

注意：这里仍是模拟盘适配层，不会真实下单；返回配置时只显示 `has_api_key`、`has_tushare_token` 等布尔状态，不返回真实密钥。

## 9. 启动终端 TUI 客户端

如果现代 GUI 在本机调试困难，优先使用 TUI 验证同一套后端能力：

```powershell
.\start.bat -Mode tui -BackendPort 18080
```

这个入口会先检查或启动 FastAPI 后端，再在当前终端打开 `python -m apps.tui`。TUI 与 GUI 共用接口：配置、模型列表、自动投资、决策日志、股票看板、排行榜、Agent Markdown 学习和数据源诊断都来自 `apps/backend`。

首次进入时会出现初始化配置向导。配置保存到本地运行时文件：

```text
data/runtime/settings.override.json
```

该目录已被 `.gitignore` 忽略，不会随 Git 提交。向导中的 API Key、Tushare Token、JQData 密码等密钥不会在摘要中回显。

常用命令：

```text
/help                                      # 查看命令
/status                                    # 后端、任务、上下文和权限状态
/models                                    # 刷新模型列表
/models set rule-baseline,gpt-5.4-mini     # 选择模型账户
/workflow offline                          # 选择工作流；auto/daily 不能与其他类型多选
/start --offline --max-count 1 --days 12   # 后台提交一次模拟盘轮次
/providers                                 # 查看 provider chain、适配能力和缺失凭证
/dashboard rankings                        # 查看模型排行榜
/dashboard stocks                          # 查看持仓、候选和交易
/dashboard decisions                       # 查看可折叠式决策日志文本
/agent learning stats                      # 查看 Agent Markdown 学习进度
/agent learning suggestions                # 查看最近一次人工审查学习建议
/compact                                   # 手动压缩本地 TUI 对话上下文
/attachments show                          # 预览拖入终端的非敏感文本文件
/permission ask                            # 设置本地交互权限提示模式
/sandbox read-only                         # 设置本地 TUI 沙盒提示状态
/exit                                      # 退出 TUI，不强制中断后端任务
```

默认 `/start` 调用 `/api/auto-investment/background`，后端会立即返回 `run_id`，模拟盘任务继续在后端进程中执行。即使终端关闭，只要后端进程仍在，任务仍会继续；重新进入 TUI 后用 `/status` 或 `/dashboard rankings` 查看结果。

拖拽文件到终端时，TUI 会识别绝对路径。对 `.env`、`credentials.json`、文件名含 `secret/token/password` 等疑似敏感文件，`/attachments show` 会拒绝预览，避免把密钥打印到终端。

## 10. 桌面版预览和打包验证

最终目标是双击 Tauri 打包出的桌面 `.exe`，由桌面壳自动启动 Python FastAPI sidecar 并加载 Next.js 静态页面。优先使用全自动流程：

```powershell
# 自动安装 Python / npm 依赖、构建 sidecar、构建静态前端、运行质量门禁，并在需要时安装 Rust/Cargo 与 Windows C++ 构建工具后打包桌面安装包
.\start.bat -Mode desktop-release -AutoInstallRust
```

桌面打包不再依赖 Google Fonts 在线拉取，前端使用系统字体兜底，因此在受限网络或离线网络中也不会因为字体下载失败而中断 Tauri `beforeBuildCommand`。

打包后的桌面壳会优先在 `127.0.0.1:18080..18100` 范围内查找或启动后端；旧的 `8000..8020` 只用于兼容复用历史启动的健康 AStock 后端。这样即使常见端口 `8000` 被其他项目占用，也不会阻塞新启动的内置 sidecar。前端 HTTP 和 WebSocket 连接会探测同样范围。

如果你只想验证除最终 `.exe` 编译以外的所有步骤，可以运行：

```powershell
.\start.bat -Mode desktop-release -SkipDesktopBuild
```

如果只想跑提交前质量门禁，可以运行：

```powershell
.\start.bat -Mode delivery-check
```

分步骤检验仍然可用：

```powershell
# 检查 Node/npm/Python/Cargo 和 sidecar 状态
.\start.bat -Mode desktop-doctor

# 构建 Python 后端 sidecar；此步骤不需要 Cargo
.\start.bat -Mode desktop-sidecar

# 构建桌面壳使用的静态前端；此步骤不需要 Cargo
npm --prefix apps/frontend run build:desktop

# 安装 Tauri CLI 包，并在 Rust/Cargo 可用后启动或打包桌面壳
Push-Location apps/desktop; npm install; Pop-Location
.\start.bat -Mode desktop-dev
.\start.bat -Mode desktop-build
```

如果 `desktop-doctor` 显示 `MISSING: cargo` 或 Windows C++ 构建工具缺失，可以直接运行 `desktop-release -AutoInstallRust` 让脚本自动安装 Rust/Cargo 与 Visual Studio C++ Build Tools；也可以手动安装 Rust/Cargo（推荐 <https://rustup.rs/>）和 MSVC C++ Build Tools，再执行 `desktop-dev` 或 `desktop-build`。没有 Cargo 或 MSVC 时，仍然可以用 `modern-ui` 验证产品功能，用 `desktop-release -SkipDesktopBuild` 验证除最终 `.exe` 编译外的完整链路。

`desktop-build` 成功后，Windows 安装包会出现在：

```text
apps/desktop/src-tauri/target/release/bundle/nsis/
```

## 11. 启动长期调度器

确认 `.env` 的调度配置：

```env
SCHEDULER_DAILY_RUN_TIME=15:05
STOP_LOSS_INTERVAL_MINUTES=5
SCHEDULER_MODELS=rule-baseline,gpt-5.4-mini
```

启动：

```powershell
python -m astock_agent_system.cli scheduler start
```

调度器会在交易日指定时间运行自动投资轮次，并按间隔检查止损。

## 12. 常见问题

### bench 能列出模型，但单模型测试失败

常见原因：模型无权限、网关限流、模型不支持当前 profile。建议：

```powershell
python -m astock_agent_system.cli bench --models "your-model-id" --limit 1
```

并尝试：

```env
LLM_REQUEST_PROFILE=auto
LLM_MAX_TOKENS=128
```

### Docker 连接失败

先确认 Docker Desktop 已启动，再运行：

```powershell
docker compose up -d
python -m astock_agent_system.cli storage status --strict
```

### 看板没有 LLM 元素

先确认 LLM 配置和 bench：

```powershell
python -m astock_agent_system.cli config
python -m astock_agent_system.cli bench --list-models
```

然后在看板的“LLM / 模型”页获取模型列表，或在“观测看板”运行一次自动投资轮次。
