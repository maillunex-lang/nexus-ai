# GitHub Agent 0.5: read-only release

## Available in ordinary ChatGPT MCP
- `nexus_github_repositories()`: approved public repositories
- `nexus_github_repository(repo_id="nexus-ai")`: metadata and immutable HEAD SHA
- `nexus_github_tree(repo_id, commit_sha)`: bounded tree at full commit SHA
- `nexus_github_file(repo_id, commit_sha, path)`: UTF-8 source content

Initial allowlist: only `maillunex-lang/nexus-ai`, identifier `nexus-ai`. This is deliberate. Never allow arbitrary owner/repository, URL or local filesystem path from MCP arguments. The allowlist is currently code-managed in `backend/nexus/github_reader.py`; new repositories require a reviewed code change. Public GitHub API only, no API keys, no Codex CLI, no git subprocess and no OpenAI API. Anonymous GitHub rate limits apply. Private repositories are not supported in this phase.

Limits: 8-second upstream timeout, 450 KB HTTP response, 250 tree entries, 96 KB UTF-8 source file, 240-character path, immutable full 40-digit lowercase commit SHA, no redirect following. Deny dot traversal, .git, .env and .github file content. No mutations. Note: this does not replace GitHub content security review and public repositories can still contain secrets accidentally committed by their owners.

## Example
Ask: «@NEXUS AI Final вызови nexus_github_repositories, затем nexus_github_repository для nexus-ai, используй head_sha для nexus_github_tree и покажи структуру репозитория. Ничего не изменяй.»

## Planned write architecture (NOT IMPLEMENTED)
1. Authenticate individual OAuth user identity, not merely token validity. Require separate `mcp:write` consent and server-side project role checks.
2. Admin-managed allowlist and exact repository permissions; audit all access and decisions.
3. Work only in a disposable isolated worktree, never in the live deployment checkout. Generate a proposed patch with content hashes and diff preview.
4. Require explicit approval for exact repo, base SHA, branch name, file paths, patch digest and action; protect against TOCTOU and stale approval.
5. Apply patch in disposable workspace, run bounded tests with no secrets/network, inspect diff, then create a uniquely named branch.
6. Push with least-privilege GitHub App credentials restricted to the exact repository, never personal tokens or host SSH credentials.
7. Open a draft Pull Request with check results; do not auto-merge or deploy. Record immutable audit trail and allow cancellation.
8. Rate limits, max diff size, denylist sensitive files, concurrency caps, rollback by branch deletion after review.

The existing Mission Control Director approvals do not authorize GitHub writes. No write MCP tool exists in 0.5.
