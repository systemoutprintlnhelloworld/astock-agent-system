---
name: astock-delivery-workflow
description: Guides delivery work for the A-share LLM multi-agent paper-trading system. Use when changing this project, preparing releases, updating docs, validating online/offline runs, or handling secrets, GitHub Pages, hooks, and one-click scripts.
---

# AStock Delivery Workflow

## Instructions

Use this workflow when developing or delivering this repository:

1. Protect secrets first.
   - Never print or commit real API keys, Tushare tokens, webhook URLs, or `.env`.
   - Use `.env.example` and docs placeholders only.
   - Run a focused secret scan before commits.
2. Keep the system directly usable.
   - Prefer `start.bat` / `start.ps1` for user-facing run paths.
   - Maintain offline smoke paths so the project works without online services.
   - Keep online paths explicit and diagnosable through JSON CLI output.
3. Validate without adding throwaway test scripts.
   - Use existing CLI, pytest, docs build, GitHub CLI, and shell commands.
   - Do not run compile commands unless the user explicitly asks.
4. Update docs with every delivery change.
   - Update `README.md`, `docs/USER_GUIDE.md`, `docs/ONLINE_RUNBOOK.md`, `docs/DEVELOPER_GUIDE.md`, `docs/GITHUB_PUBLISHING.md`, and `docs/DELIVERY_SUMMARY.md` when relevant.
   - Keep `docs/trellis-plan.md` aligned with the current delivery plan.
5. Use Git carefully.
   - Inspect `git status`, `git diff`, and recent commits before committing.
   - Do not amend or force push unless explicitly requested.
   - Commit only after validation and secret checks pass.
6. Keep automation unblocked.
   - Do not enable project-level shell approval gates unless the user explicitly asks.
   - If a guard is used, prefer automatic `allow` or `deny`; avoid `ask` responses that slow down normal development.

## Recommended validation set

Run the subset relevant to the change:

```powershell
python -m pytest
python -m astock_agent_system.cli storage status --strict
.\start.bat -Mode status
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
python -m mkdocs build --strict
git status --short
```

For GitHub Pages, confirm repository visibility and Pages status with `gh repo view` and `gh api repos/<owner>/<repo>/pages`.
