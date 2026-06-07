---
name: astock-trellis-handoff
description: Guides Trellis-style handoff for the AStock Agent system. Use when preparing or continuing a new AI conversation, writing Phase 0 grill-me, Phase 1 PRD/design/implement docs, syncing handoff state, or preserving project workflow for this repository.
---

# AStock Trellis Handoff

## Instructions

Use this workflow whenever a conversation is handing off work, resuming work from Trellis docs, or changing the delivery plan for this repository.

## Required read order

Before editing code or plans, read these files in order:

1. `AGENTS.md`
2. `.cursor/skills/astock-delivery-workflow/SKILL.md`
3. `DOCUMENTATION_MAP.md`
4. `docs/trellis/HANDOFF.md`
5. `docs/trellis/PHASE0_GRILLME.md`
6. `docs/trellis/PRD.md`
7. `docs/trellis/DESIGN.md`
8. `docs/trellis/IMPLEMENT.md`
9. `docs/trellis-plan.md`
10. `docs/modernization-plan.md`

## Handoff workflow

1. Inspect state with `git status --short --branch` and `git diff -- .`.
2. Use context-weaver/codebase retrieval before planning or editing involved code symbols.
3. Confirm the core product boundary:
   - Benchmark mode only; `N=1` is still Benchmark mode.
   - Each selected model drives an independent full 8-Agent system and independent `VirtualAccount`.
   - Current product is paper trading only; do not silently add real order placement.
   - Final user delivery is Tauri `.exe` / NSIS installer; `start.bat` is a dev/validation path.
4. Keep Phase 0 grill-me questions in `docs/trellis/PHASE0_GRILLME.md`.
5. Keep Phase 1 product/design/implementation state in `docs/trellis/PRD.md`, `docs/trellis/DESIGN.md`, and `docs/trellis/IMPLEMENT.md`.
6. Keep the new-conversation entry point in `docs/trellis/HANDOFF.md`.
7. Update `DOCUMENTATION_MAP.md` whenever a new persistent handoff or plan document is added.

## External and local knowledge

- Use smart-search for current web research only after `smart-search doctor --format json` is healthy. If it fails, record the failed command and do not claim fresh external evidence.
- Use find-skills before installing third-party skills; prefer skills with reputable source and high install count. Be cautious with skills under 100 installs.
- Use create-skill rules for project skills. Store repository skills under `.cursor/skills/<skill-name>/SKILL.md`; never create them under `~/.cursor/skills-cursor/`.
- If a user-feedback or memory tool is available, use it only for explicit blockers or decisions; otherwise write the feedback need in `docs/trellis/HANDOFF.md`.

## Validation and Git close-out

Run the subset relevant to the change, defaulting to:

```powershell
python -m pytest tests/test_backend_api.py
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run build:desktop
.\start.bat -Mode delivery-check
```

Before the final commit, inspect staged/untracked changes and recent commits. Commit only after validation and secret checks. The project `post-commit` hook pushes the current branch to `origin`; if push fails, keep the local commit and report the exact retry command.

## Required user-provided information

No extra information is required for offline/local desktop validation. Online mode requires only local, uncommitted `.env` values:

- Tushare token
- OpenAI-compatible LLM base URL and API key
- Optional SMTP/webhook credentials if notification features are enabled later

Never print or commit those values.
