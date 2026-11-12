# NEXUS AI: Autonomous Enterprise delivery plan

Status: **planning and incremental implementation**. Only the 0.1 development scaffold is running on Lunex loopback; it has **no OAuth** and must not be publicly exposed.

## Release gates

- **0.1 Secure Foundation**: secure OAuth 2.1 Authorization Code + PKCE with supported client registration, audience-bound tokens, protected MCP endpoints, session/CSRF protection, RBAC, audit, PostgreSQL migrations, CI, actual ChatGPT handshake. Current scaffold is NOT release-ready.
- **0.2 Autonomous Organization**: AI Director, agent registry, task decomposition, specialist roles, typed work contracts, budgets, isolated execution and human escalation.
- **0.3 Cognitive Memory**: per-project knowledge, provenance, retention, search, edit/delete controls, access boundaries and export.
- **0.4 Mission Control**: durable queue, workers, retries, idempotency, checkpoints, schedules, cancellation, approval pauses, resource budgets.
- **0.5 Universal Tool Hub**: least-privilege adapters for GitHub/Codex, Godot, Blender, SSH/Linux, Docker, browser; read-only first, per-tool policy, separate project working copies.
- **1.0 Autonomous Enterprise**: full Russian web dashboard, Android responsive design, operator roles, observability, backups and restore drills, security review, disaster recovery, performance and end-to-end tests.

## Safety rules

1. Lunex is a shared production host. Do not restart or modify unrelated projects, containers, reverse proxy, ports, or firewalls.
2. Keep development service bound to 127.0.0.1 until authenticated, audited and explicitly approved for exposure.
3. Default-deny policies, immutable action arguments on approval, one-time grants, auditable execution.
4. No secrets in public GitHub; no execution of untrusted agent text as shell.
5. Read-only access to original games and projects; edits in isolated copies/branches with backups and explicit approval.
6. Hard CPU, memory, disk, time and concurrency limits; no local heavyweight LLM by default.
7. Each milestone requires executable tests and evidence; never claim untested integration as complete.

## Current implementation gap

Only status/capabilities MCP tools, FastAPI health/status, starter PostgreSQL schema, React diagnostic dashboard, Compose and CI workflow exist. OAuth, permissions, agents, memory, missions, tool execution and full audit are NOT implemented.

## Immediate engineering tasks

1. Make CI green and add protocol-level MCP tests.
2. Integrate vetted OAuth authorization server, enforce authorization at MCP gateway and dashboard.
3. Introduce versioned DB migrations, user/project/role models and append-only audit service.
4. Add approval workflow with action digest, expiry and one-time consumption.
5. Test actual ChatGPT connection before enabling public HTTPS.
