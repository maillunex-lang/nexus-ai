# Mission Control 0.2: initial working slice

## Available

- Authenticated REST API with project creation/listing and membership checks.
- Durable tasks with title, description, status, agent assignment and optimistic version checks.
- Status transitions: backlog -> ready -> in_progress -> done, with blocked and cancelled paths. Terminal statuses cannot be reopened.
- Audit trail in `mission_task_events` and general `audit_events`.
- Read-only deterministic Director draft (NOT AI-generated, NOT executing).
- Russian responsive UI for project/task creation, assignment and status transitions.
- MCP read-only discovery tools: `nexus_status`, `nexus_capabilities`, `nexus_agents`, `nexus_workflow`.
- Writes are available only via authenticated same-origin dashboard REST API. OAuth `mcp:read` cannot write or run commands.

## API

- `GET/POST /nexusai/api/mission/projects`
- `GET /nexusai/api/mission/projects/{project_id}/tasks`
- `POST /nexusai/api/mission/tasks`
- `PATCH /nexusai/api/mission/tasks/{task_id}` with `version` to avoid lost updates
- `GET /nexusai/api/mission/tasks/{task_id}/director-plan`

Owner can see all projects; operators/viewers only their memberships. Viewers cannot write. Owner/operator can create projects and tasks. Assignment records a planned agent only; it does not execute code.

## Safety and limitations

- No shell/SSH/Docker/GitHub/Godot/Blender command execution.
- No live AI model invocation or autonomous task runner.
- No task write tools over MCP until OAuth token is bound to a user and write scope/approvals are implemented.
- No comprehensive production security audit yet; CSRF token, rate limiting and end-to-end authenticated workflow tests remain outstanding.
- Mission Control overview includes approval requests but does not yet provide approval actions.
- No sample project records are created on deployment.

## Deployment

1. Check GitHub revision and backup PostgreSQL with `pg_dump -Fc` to a mode-0600 file outside the repo.
2. Apply `db/005_mission_control.sql` once using `psql -v ON_ERROR_STOP=1`.
3. Run pytest and React build.
4. Recreate only `nexus-ai-dev` API/web containers using `docker compose up -d --no-build`.
5. Check HTTPS dashboard, unauthenticated API 401, and unrelated project health.
6. For rollback, restore the previous tested application revision; schema additions are backward compatible. Never remove volumes or drop tables automatically.

## Next steps

- Full integration tests with isolated test PostgreSQL and browser auth.
- CSRF nonce on cookie-authenticated mutations and explicit per-project access policy.
- Director model integration with structured, inspectable plans and human approvals.
- Durable worker queue, retries, idempotency and sandboxed executor with per-action allowlist.
