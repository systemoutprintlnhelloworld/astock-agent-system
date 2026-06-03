# GitHub 发布说明

本项目可以用 Git 管理并托管到 GitHub。发布前请先确认 `.env`、日志、报告和运行数据不会被提交。

## 1. 初始化 Git

如果项目还不是 Git 仓库：

```powershell
git init
git status --short
git check-ignore .env
```

`git check-ignore .env` 应输出 `.env`。如果没有输出，请先检查 `.gitignore`。

## 2. 发布前检查

```powershell
python -m pytest
python -m astock_agent_system.cli bench --help
python -m astock_agent_system.cli scheduler run-auto-investment --offline --max-count 1 --days 12
git status --short
```

禁止提交：

- `.env`
- API key / token
- 虚拟环境目录
- `reports/`
- `logs/`
- `data/runtime/`

## 3. 创建 GitHub 仓库

方式一：使用 GitHub CLI：

```powershell
gh auth login
gh repo create astock-agent-system --private --source . --remote origin
```

方式二：在 GitHub 网页新建仓库，然后添加远程：

```powershell
git remote add origin https://github.com/<your-user>/<your-repo>.git
```

## 4. 首次提交和推送

只有确认没有密钥后再提交：

```powershell
git add README.md PROGRESS_REPORT.md docs .gitignore pyproject.toml requirements.txt docker-compose.yml config data src tests
git status --short
git commit -m "Add A-share multi-agent paper trading MVP"
git branch -M main
git push -u origin main
```

如果你希望仓库公开，请先再次检查文档和提交内容不含真实密钥。

## 5. GitHub 文档托管

推荐直接使用仓库 Markdown 文档：

- 根目录 `README.md` 作为项目首页。
- `docs/README.md` 作为文档索引。
- `docs/USER_GUIDE.md` 面向使用者。
- `docs/ONLINE_RUNBOOK.md` 面向在线运行。
- `docs/DEVELOPER_GUIDE.md` 面向开发者。

如果要开启 GitHub Pages：

1. 进入仓库 Settings。
2. 打开 Pages。
3. Source 选择 `Deploy from a branch`。
4. Branch 选择 `main`，目录选择 `/docs`。

## 6. 维护建议

- 每次增加在线运行能力时，同步更新 `docs/ONLINE_RUNBOOK.md`。
- 每次增加模块或接口时，同步更新 `docs/DEVELOPER_GUIDE.md`。
- 每次修复用户使用路径时，同步更新 `README.md` 和 `docs/USER_GUIDE.md`。

