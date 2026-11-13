# Autonomous AI Director 0.6

Status: **implemented and unit-tested in the repository; not deployed to Lunex and not exercised against a real Godot toolchain or a live ChatGPT session.** See "Verification status" below.

## What it is

The Director runs fixed, typed multi-stage **pipelines**. Each stage belongs to an agent role and is executed by a capability that already existed (static inspection, the isolated Godot validation queue, the Android debug build queue) or by the new verification gate. When a stage succeeds the Director starts the next one by itself; on the first failure it stops, classifies the error and writes it to the owner's error journal.

It is deterministic. There is no language model, no shell, no network call, no write to an original game, no publishing and no automatic retry. The connected chat (ChatGPT over MCP) supplies the reasoning and the proposed code; NEXUS supplies bounded, auditable execution.

| Pipeline | Stages (agent) | Needs change set | Builds APK |
|---|---|---|---|
| `project_audit` | inventory (tester) → android_audit (artist) → graphics_audit (artist) → audit_report (director) | no | no |
| `build_apk` | preflight (tester) → build (devops) → delivery (director) | no | yes |
| `change_validate` | verify_change (tester) → validate_change (developer) → change_report (director) | yes | no |
| `change_build_apk` | verify_change (tester) → validate_change (developer) → build_validated (devops) → delivery (director) | yes | yes |

## Safe code editing

1. Read a file and its SHA-256 with `nexus_godot_project_file`.
2. `nexus_director_changeset_create(project_id, files, description)` — 1–8 operations on `.gd/.gdshader/.tscn/.tres` files, at most 100 kB in total:
   - modify: `{path, expected_sha256, content}`
   - create: `{action: "create", path, content}` — the path must not exist; new folders are allowed
   - delete: `{action: "delete", path, expected_sha256}`
   - a rename is a delete plus a create

   The result contains per-file diffs and a verification verdict. The change set is an immutable record with a digest; nothing is written to the project.
3. Run `change_validate` or `change_build_apk`. The host worker re-checks every SHA pin, copies the project to a fresh workspace, applies all files to the copy (all or nothing) and runs Godot headless inside bubblewrap without network.
4. The APK from `change_build_apk` is built from that validated copy.

There is deliberately **no operation that writes a change back to an original game directory**; originals stay mounted read-only. A validated change leaves the sandbox only as a patch or as a Git branch for review (see "Adopting a validated change").

Change validation is enabled for `basheco` (the locked baseline, as the single-file tool has always had) plus any build-enabled game the **owner switches on in the dashboard** (Director console → "Проверка изменений кода", `POST /api/director/settings/change-validation`). There is no MCP tool for this switch; every change is written to `director-settings/audit.jsonl`. Change sets for other projects can be created and reviewed as diffs but not validated.

### Verification gate (`director_verification`)

Static rules, run when a change set is created and again immediately before it is queued:

- **block**: unbalanced brackets, unterminated strings, mixed tab/space indentation, merge-conflict markers, emptied file, missing `shader_type`, missing `[gd_scene`/`[gd_resource` header, newly introduced process APIs (`OS.execute`, `OS.create_process`, `OS.shell_open`, `OS.kill`, …).
- **warn**: newly introduced network, file-deletion or dynamic-code APIs, `ext_resource` paths that do not exist, deletion of more than 80 % of a file, deleting a file that the remaining project still references by `res://` path.

API rules compare old and new source, so code that already existed is not reported. These are heuristics; the Godot parser in the isolated copy is the authority.

## Authorization and approval

Nothing changed in OAuth, scopes, consent or the bearer guard.

- `mcp:read` may create change sets, plan pipelines and create approval requests. All of these are inert.
- `mcp:write` may launch, cancel and retry.
- With a read token, `nexus_director_pipeline_request_approval` creates a request in the existing owner-approval system and returns the same kind of `approval_url`. The dashboard approval page shows the stages and the full diff. Only an authenticated owner browser session can approve, once.
- Every plan has a SHA-256 **plan digest** over pipeline, project, change-set digest and stage list. The approval stores it, launch refuses a different one, and it is re-checked before every transition. A status poll (even with a read token) therefore can only continue exactly what the owner authorized.

## Automatic transitions

Transitions happen on `nexus_director_pipeline_status`, on the dashboard detail endpoint, or without any caller via the optional one-shot tick:

```
docker compose exec -T api python -m nexus.director_pipeline_worker
```

To schedule it without any host timer, set `NEXUS_DIRECTOR_TICK_SECONDS` (15–3600) on the API service: the API process then runs the same pass on that interval. It is **off by default**, and `compose.yaml` does not forward the variable: add it to the `api` service environment in your own override file. A per-pipeline lock prevents two callers from starting the same stage twice.

## Mission Control link

`nexus_director_pipeline_launch`, `nexus_director_pipeline_request_approval` and the dashboard accept an optional `task_id` (a Mission Control task UUID). The pipeline's milestones (`director.pipeline.started/completed/failed/cancelled/retried`) are appended to that task's existing event history and to `audit_events`; `nexus_director_pipeline_list(task_id=...)` and the task card in the dashboard show the linked runs. The link is metadata only: it is not part of the plan digest, a task's status stays under human control, and a database outage never affects a running pipeline. No migration is needed.

## Adopting a validated change (`director_adoption`)

**Patch export — always available.** `nexus_director_changeset_patch` (or the "Скачать патч" link on the approval page, `GET /api/director/changesets/{id}/patch`) returns a git-compatible patch with paths relative to the Godot project root, including new and deleted files. Apply it yourself: `git checkout -b nexus/adopt-… && git apply --check FILE && git apply FILE`. Nothing is applied by NEXUS.

**GitHub branch and draft pull request — off until you configure it.** Requires on the API service:

- `NEXUS_ADOPTION_REPOSITORIES`, e.g. `{"basheco": {"repository": "owner/repo", "base_branch": "main", "path_prefix": "client"}}` (`path_prefix` is where the Godot project lives inside the repository; empty for the root);
- a token file at `/run/secrets/github_adoption_token` (or `NEXUS_GITHUB_ADOPTION_TOKEN_FILE`) holding a fine-grained token for only those repositories with *Contents: write* and *Pull requests: write*.

Flow: `nexus_director_adoption_request(changeset_id)` creates an inert request and an `approval_url` (a read token is enough; GitHub is not contacted). The owner sees the repository, base branch and full diff in the dashboard. On approval NEXUS creates a new branch `nexus/adopt-<id>-<random>` with exactly one commit on top of the current base branch head and opens a **draft** pull request.

Safeguards:
- Only change sets with a completed `change_validate` or `change_build_apk` pipeline.
- Every modified or deleted file in the repository must be byte-identical (SHA-256) to the source the change was validated against, and a created file must not exist; otherwise nothing is written (`repository_differs_from_validated_source`).
- The approval pins change-set digest, repository, base branch and prefix; changing any of them invalidates it.
- Branches are created, never updated; the base branch is never written; there is no merge, no non-draft fallback, no deploy, and no MCP tool that executes adoption directly.
- The token is read from the file on each use and never appears in responses, records or logs. Each adoption is appended to `director-adoptions/audit.jsonl`.

`nexus_director_adoption_status` shows what is configured.

## Retention

Each scheduled or one-shot pass also removes finished Director state older than `NEXUS_DIRECTOR_RETENTION_DAYS` (default 30, `0` disables), at most once an hour: terminal pipelines with their journals, change sets not referenced by a kept pipeline or a pending approval request, rotated error journals and lock files older than a day. It never touches projects, workspaces, builds, host job queues or approval requests.

Limits: 3 running pipelines per owner, 45 minutes per asynchronous stage (then `worker_timeout`), 2 attempts per stage.

## Error journal (`director_errors`)

Each failed stage is recorded once: category, policy (`stop_and_report` or `reject_without_retry`), whether an explicit retry is allowed, a concrete next action, and structured Godot diagnostics (`file`, `line`, message) parsed from the validation log. Read it with `nexus_director_error_log` or in the dashboard. `nexus_director_pipeline_retry` works only for retryable categories (timeouts, unavailable toolchain or job, build failure) and only by explicit owner-write request.

## New MCP tools

`nexus_director_agents`, `nexus_director_pipelines`, `nexus_director_changeset_create`, `nexus_director_changeset_status`, `nexus_director_pipeline_plan`, `nexus_director_pipeline_launch`, `nexus_director_pipeline_request_approval`, `nexus_director_pipeline_status`, `nexus_director_pipeline_journal`, `nexus_director_pipeline_list`, `nexus_director_pipeline_cancel`, `nexus_director_pipeline_retry`, `nexus_director_error_log`.

All earlier tools keep their names, parameters and behaviour. `nexus_capabilities` now lists the tools from the live registry (the hand-written list had fallen behind).

## Dashboard API (owner session, same-origin write protection)

`GET /api/director/{agents,catalog,errors,pipelines}`, `GET /api/director/pipelines/{id}`, `GET /api/director/pipelines/{id}/journal`, `POST /api/director/pipelines`, `POST /api/director/pipelines/{id}/{cancel,retry}`.

## Deployment notes (owner action; nothing was changed on Lunex)

- No database migration. State is JSON in the existing queue volume: `director-changesets/`, `director-pipelines/`, `director-errors/`.
- API and web images need a rebuild to expose the new tools and console.
- `scripts/godot_agent_workspace.py` and `scripts/godot_queue_worker.py` changed. Until the host copies are updated, a single-file modification of `basheco` works (it uses the unchanged legacy job shape); every other change set (several files, create, delete, other projects) fails closed with `invalid_job_shape`.
- Behaviour change in the host script: the Godot error pattern was double-escaped and never matched. It is fixed, and a **patched** copy with `SCRIPT ERROR`/`Parse Error` lines now fails validation. Unpatched builds of existing games keep the exit-code rule, so their builds are not affected.

## Verification status

Verified here: 271 backend tests (the exported patch is applied with real `git apply` in a test) (pytest) and the dashboard production build; the console and approval page were rendered in Chromium against a mocked API.

Not verified: the GitHub adoption path against the real GitHub API (it is exercised against an in-memory fake), a real Godot/bubblewrap/Android SDK run, the deployed host worker, PostgreSQL-backed login, and a live ChatGPT MCP session. The host worker in tests is simulated by moving queue files exactly as the worker does.

## Known limitations

- No LLM planner: the Director cannot invent a fix. The chat proposes a corrected change set after reading the diagnostics.
- Change sets are limited to four text file types and 8 operations; binary assets cannot be added or removed.
- Cancelling does not interrupt a job the host worker has already taken.
- The Mission Control link writes history only; it does not move a task between statuses.
- Change sets are capped at 300 stored records; approval requests are not subject to retention.
- Open items of `SECURITY_AUDIT_2026-11-12.md` (CSRF token, rate limiting, audit logging of auth events) are unchanged.
