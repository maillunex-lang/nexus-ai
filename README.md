# NEXUS AI

MCP platform for supervised game-development automation: OAuth-protected MCP tools for ChatGPT, a Russian operator dashboard, isolated Godot validation and Android debug builds, and a rule-based autonomous Director.

**Do not expose a development instance to the public internet.** The internal bearer token is disabled whenever `NEXUS_OAUTH_ISSUER` is set.

## Included
- FastAPI session API and OAuth 2.1 authorization code + PKCE server (`mcp:read`, `mcp:write`, explicit consent)
- FastMCP Streamable HTTP at `/mcp/` behind a fail-closed bearer guard
- Godot inspection, SHA-pinned change validation in isolated copies, debug APK builds with short-lived signed links
- Autonomous Director: multi-stage pipelines with automatic transitions, multi-file change sets, verification gate, error journal, owner approval flow. See [Director 0.6](docs/AUTONOMOUS_DIRECTOR_0.6.md)
- React 19 / Vite dashboard: login, consent, Mission Control, builds, approvals, Director console
- PostgreSQL 16 schema scripts in `db/`; GitHub Actions for backend tests and frontend build

Current state, findings and next steps: [audit and roadmap](docs/AUDIT_AND_ROADMAP_2026-11-13.md).

## Local Docker start (not on production VPS)
1. Copy `.env.example` to `.env`.
2. Set a strong unique `POSTGRES_PASSWORD` and `NEXUS_MCP_INTERNAL_TOKEN` (48+ random characters). URI-special characters in the DB password require encoding.
3. Run `docker compose up --build -d`.
4. Open `http://127.0.0.1:4189` on the same machine.
5. Run `docker compose down` to stop services while retaining the DB volume.

**Database:** `db/001_initial.sql` runs only on first PostgreSQL volume creation. On existing installations, back up PostgreSQL, then apply `db/002_identity.sql` once using `psql -v ON_ERROR_STOP=1`. This is an interim migration script, not a migration framework.

## Backend tests
```sh
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m pytest -q backend/tests
```

## Frontend build
```sh
cd frontend
npm install
npm run build
```

## Security limitations
- The Director is deterministic: no language model, no shell, no publishing; original game directories are read-only.
- Open items are tracked in [the security audit](docs/SECURITY_AUDIT_2026-11-12.md): no per-session CSRF token (Origin and Fetch Metadata checks only), limited rate limiting, incomplete audit logging of authentication events.
- Migrations are plain SQL scripts applied manually, not a migration framework.

See [Enterprise roadmap](docs/ENTERPRISE_ROADMAP.md).
