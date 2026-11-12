# NEXUS AI 0.1.1 Secure Foundation

Development-only scaffold for the NEXUS AI MCP platform. **Do not expose the API or MCP endpoint to the public internet.** OAuth, RBAC enforcement, approval execution and audit enforcement are not implemented.

## Included
- FastAPI: `/api/health` and `/api/status`
- FastMCP Streamable HTTP at `/mcp/`, read-only `nexus_status` and `nexus_capabilities`
- Temporary fail-closed bearer guard for MCP; secret must be at least 32 characters
- PostgreSQL 16 starter schema and identity schema `db/002_identity.sql`
- React 19 / Vite diagnostic dashboard in Russian
- Local-only Docker Compose port `127.0.0.1:4189`
- GitHub Actions: backend pytest and frontend build

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
- The internal bearer token is a **temporary development-only mechanism**, not OAuth or a safe replacement for public ChatGPT integration.
- Status endpoints remain unauthenticated; they contain only limited diagnostics.
- Identity tables do not yet implement login, RBAC middleware, session handling, or permissions.
- Audit and approval tables do not enforce actions.
- No privileged tool execution or background agents are implemented.
- Do not publish the current service; public deployment requires an independently tested OAuth authorization server, secure sessions and audit.

See [Enterprise roadmap](docs/ENTERPRISE_ROADMAP.md).
