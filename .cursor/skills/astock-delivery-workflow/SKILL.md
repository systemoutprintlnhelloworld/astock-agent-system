---
name: astock-delivery-workflow
description: Guides delivery work for the A-share LLM multi-agent paper-trading system. Use when changing this project, preparing releases, updating docs, validating online/offline runs, or handling secrets, GitHub Pages, hooks, and one-click scripts.
---

# AStock Delivery Workflow

## Instructions

Use this workflow when developing or delivering this repository:

0. Follow the persistent Trellis-style development contract.
   - When the user says “请继续” or asks for continuous development, keep working until the project is deliverable unless credentials, paid quota, deployment access, destructive-operation approval, or product/architecture decisions are required.
   - Persist plans, research, decisions, validation, and handoff state in `docs/trellis/`, `docs/trellis-plan.md`, `docs/DELIVERY_SUMMARY.md`, or another tracked project document.
   - Use smart-search for external/official/current knowledge and fast-context (`fast_context_search`) for local code and architecture search. Do not use ContextWeaver, ACE, ace-tool, augment-context-engine, or codebase-retrieval as the primary retrieval route.
   - Use grill-me for requirement interrogation when ambiguity can change direction. Use find-skills before adopting new skills and create-skill/skill creator to solidify repeatable workflows.
   - Use cunzhi/feedback tooling for blockers and user decisions; keep hooks enforcing safety, documentation sync, validation, and secret hygiene.

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
   - Keep `docs/trellis-plan.md` and `docs/trellis/*` aligned with the current delivery plan and handoff state.
   - For Trellis or handoff changes, update `docs/trellis/HANDOFF.md`, `docs/trellis/PHASE0_GRILLME.md`, `docs/trellis/PRD.md`, `docs/trellis/DESIGN.md`, or `docs/trellis/IMPLEMENT.md` as appropriate.
   - Code, desktop, startup-script, config, `.husky`, or `.cursor/hooks` changes must be paired with at least one affected developer/user-facing documentation update.
5. Use Git carefully.
   - Inspect `git status`, `git diff`, and recent commits before committing.
   - Do not amend or force push unless explicitly requested.
   - Commit only after validation and secret checks pass.
   - End-of-work commit and push are mandatory for this project. The `post-commit` hook pushes the current branch to `origin`; if push fails because of network/TLS, keep the local commit and report the exact retry command.
6. Keep automation unblocked.
   - Do not enable project-level shell approval gates unless the user explicitly asks.
   - The project-level Cursor `stop` hook is intentionally enabled to enforce close-out checks without interrupting each shell command.
   - If a guard is used, prefer automatic `allow` or `deny`; avoid `ask` responses that slow down normal development.

## Recommended validation set

Run the subset relevant to the change:

```powershell
python -m pytest
python -m astock_agent_system.cli storage status --strict
.\start.bat -Mode status
npm --prefix apps/frontend run lint
.\start.bat -Mode bench -BenchModel "gpt-5.4-mini"
.\start.bat -Mode offline -MaxCount 1 -Days 12 -NoDocker
python -m mkdocs build --strict
.\start.bat -Mode delivery-check
git status --short
```

For desktop delivery changes, additionally verify the relevant subset:

```powershell
.\start.bat -Mode desktop-doctor
.\start.bat -Mode desktop-sidecar
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode desktop-release -AutoInstallRust
.\start.bat -Mode delivery-check
```

For GitHub Pages, confirm repository visibility and Pages status with `gh repo view` and `gh api repos/<owner>/<repo>/pages`.
