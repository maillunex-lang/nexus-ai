# NEXUS AI 0.1 Secure Foundation

Development-only scaffold for the NEXUS AI MCP platform. **Do not expose the API or MCP endpoint to the public internet.** OAuth, RBAC, approval execution and audit enforcement are not implemented.

## Included
- FastAPI: `/api/health` and `/api/status`
- FastMCP Streamable HTTP, read-only `nexus_status` and `nexus_capabilities`
- PostgreSQL 16 starter schema (projects and audit_events)
- React 19 / Vite diagnostic dashboard in Russian
- Local-only Docker Compose port `127.0.0.1:4189`
- GitHub Actions: backend pytest and frontend build

## Local Docker start (not on production VPS)
1. Copy `.env.example` to `.env`.
2. Set a strong, unique `POSTGRES_PASSWORD` (URI-special characters require encoding for the current DATABASE_URL).
3. Run `docker compose up --build -d`.
4. Open `http://127.0.0.1:4189` on the same machine.
5. Run `docker compose down` to stop services while retaining the DB volume.

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
- MCP and status endpoints are **unauthenticated**; do not publish them.
- The schema is initialized by Docker on first database creation; no migration framework yet.
- The current audit table does not implement tamper protection or automated audit writes.
- No privileged tool execution, background agents, OAuth or permissions are implemented.
- Do not run on Lunex until a separate audit and deployment authorization.

## Next work
OAuth provider integration, authorization middleware, RBAC, audit service, Alembic migrations, safe MCP protocol tests and real ChatGPT connection testing.
