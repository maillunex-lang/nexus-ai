# GitHub Agent 5.2: safe preview foundation

Implemented:
- `nexus_github_change_preview(repo_id,base_sha,path,proposed_content,branch)` produces bounded unified diff, original/new SHA256 and exact approval digest; no mutation.
- `nexus_github_branch_policy()` exposes protected branch, scope and approval requirements.
- All reads remain pinned to immutable 40-character commit SHA and the public allowlist.
- Rejects unsafe paths, secret-like paths, non-`nexus/` branches, oversized or binary content.

**Not implemented**: per-user MCP OAuth identity, `mcp:write` scope, repository grants, isolated test runner, creating branches, pushing commits, draft PR creation. These cannot safely be enabled with the current bearer token guard, which only verifies a token is valid for `mcp:read`. No GitHub write credentials are installed or needed for this stage. The preview approval digest is informational, not a substitute for a real signed, persisted approval. No automatic merge or deploy.

## Future implementation sequence
1. Add a token-to-user identity lookup and separate write scope, fail closed for legacy read tokens. Introduce project/repo ACL and audit records.
2. Introduce durable proposal and approval records with reviewer separation, expiry, and exact base SHA / file digest validation.
3. Run proposed changes in an isolated temporary workspace with resource limits, no secrets or live mounts. Store bounded test output.
4. GitHub App installation with exact repository grants and minimal contents/PR permissions. Create `nexus/` branches only from validated base SHA and open **draft** PRs after tests and explicit authorization.
5. Never merge, write to protected branches, or deploy through MCP.

## ChatGPT test
After refreshing tools, call `nexus_github_branch_policy` and `nexus_github_change_preview` using `repo_id=nexus-ai`, a current full SHA, path `README.md`, branch `nexus/test-preview`, and a small replacement text. Inspect the diff. No branch will be created.
