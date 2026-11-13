# Project audit and roadmap: 2026-11-13

## Audit of `main` (commit 48352d6)

**Architecture.** FastAPI (`backend/nexus/main.py`) serves the session API, a hand-written OAuth 2.1 code + PKCE server, and a FastMCP Streamable HTTP app at `/mcp` behind a fail-closed bearer guard that sets a request-local principal (`mcp:read` / `mcp:write`, owner only). PostgreSQL holds identity, OAuth, Mission Control and Meshy data. Godot work crosses a trust boundary through a file queue: the API container may only deposit JSON requests; a separate host worker (`scripts/`) validates them, copies the project and runs Godot and the Android export inside bubblewrap. Originals are mounted read-only. A React dashboard provides login, consent, Mission Control, builds and the approval page.

**Working capabilities.** 55 MCP tools: Godot inspection, single-file SHA-pinned change preview and isolated validation, debug APK build with signed five-minute download links, project onboarding and wizard, GitHub read-only, Meshy with paid-dispatch confirmation, a rule-based director (`autonomous_director`, `director_workflows`) and owner-approved requests (`director_requests`).

**Findings.**

| # | Finding | Resolution |
|---|---|---|
| 1 | CI on `main` is red: `test_game_wizard.py` imports from `/scripts`, which exists only in the container. | Fixed (`backend/tests/conftest.py`). |
| 2 | `GET /api/director/requests/{id}` raised `PermissionError` for an approved, queued build: the live-status reader needs an MCP principal that a browser session does not have. The "refresh build status" and APK buttons on the approval page could not work. | Fixed with a regression test. |
| 3 | Host worker: the Godot error regex was double-escaped (`\\s` in a raw string) and never matched, so validation passed on exit code alone even with script parse errors. | Fixed for patched copies; see Director doc. |
| 4 | `nexus_capabilities` listed 42 of 55 tools. | Now derived from the registry. |
| 5 | Director workflows were single-step: no chaining from change validation to build, no multi-file changes, no error history, agents were labels only. | Addressed by Director 0.6. |
| 6 | README and `ENTERPRISE_ROADMAP.md` still describe the 0.1 scaffold ("OAuth not implemented"). | README updated; the roadmap file is left as the historical plan. |
| 7 | Version strings disagree (`0.1.4-dev` app, `0.1.6-dev` status). | Left unchanged: cosmetic, and the deployed status string may be monitored. |

## Roadmap

| Stage | Scope | State |
|---|---|---|
| 0 | Green baseline: CI fix, audit | done |
| 1 | Change sets, verification gate, error journal | done |
| 2 | Pipelines with automatic transitions, agents, retry/cancel, tick worker; host worker multi-file patches | done |
| 3 | Approval-flow integration, MCP tools, dashboard API | done |
| 4 | Dashboard console and diff review on the approval page | done |
| 5 | Deploy to Lunex and run each pipeline against the real toolchain and a live ChatGPT session | **owner action, not done** |
| 6 | Link pipelines to Mission Control tasks; retention for file state; optional in-process schedule (`NEXUS_DIRECTOR_TICK_SECONDS`, off by default) | done |
| 7 | File creation/deletion in change sets; per-project change enablement decided by the owner in the dashboard | done |
| 8 | Reviewed "adopt change" path into a Git branch of the game (never the live directory) | needs design and owner approval |
| 9 | Optional LLM planner behind the same approval gate | needs provider, budget and security decisions |
