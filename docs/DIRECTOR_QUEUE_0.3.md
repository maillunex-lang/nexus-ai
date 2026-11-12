# Director queue 0.3: safe initial implementation

The queue is persistent in PostgreSQL. Only an owner can enqueue an approved, unexpired proposal. Approval requires a distinct reviewer from its creator. Jobs are unique by proposal ID, scoped by project, and can be cancelled while queued.

Endpoints:
- POST /nexusai/api/mission/proposals/{id}/enqueue
- GET /nexusai/api/mission/projects/{id}/jobs
- POST /nexusai/api/mission/jobs/{id}/cancel

The worker is deliberately **not scheduled**. An operator may run a single offline, deterministic processing pass using:
`docker compose exec -T api python -m nexus.director_worker`

This processor reads approved plans and writes a template review result. It does **not** call an AI model, execute shell commands, modify repositories, access Docker, or contact third-party services. A queued job is not automatically processed. If a process crashes while running, it remains in running state; recovery/retries need to be designed and tested before enabling a background worker.

Database migration: `db/007_director_queue.sql`; backup PostgreSQL first. New tables are additive. No changes to unrelated Compose projects.

Open blockers before real autonomous execution:
- Per-action approval of explicit command/target/repository, not just a generic plan.
- Isolated sandbox with resource limits and no ambient VPS credentials.
- Worker leases, bounded retries, heartbeat, idempotency and cancellation.
- AI provider selection and secure credential management; structured-output validation and prompt-injection defenses.
- End-to-end database/browser tests with multiple users and approval roles.
- CSRF nonce and fine-grained OAuth scopes before enabling MCP writes.
