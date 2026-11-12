# NEXUS AI security audit: 2026-11-12

Status: **partial, not production security certification**.

## Confirmed
- HTTPS `https://rikagro.ru/nexusai/` responds 200; OAuth discovery responds 200.
- MCP and agent API return 401 without bearer/session.
- PostgreSQL health check passes; public OAuth client registry is empty.
- Internal bearer credential is disabled when `NEXUS_OAUTH_ISSUER` is configured.
- OAuth codes are hashed, expire after 3 minutes, single-use via transaction lock; PKCE S256 mandatory; exact redirect allowlist.
- Access tokens hashed and revocable, expire after 30 minutes, scoped to `mcp:read`.
- Owner exists and browser login was confirmed by user screenshot.
- 45 pytest tests passed; React build previously passed.

## Issues fixed
- Cookie deletion used `/` despite session cookie path `/nexusai`: fixed.
- MCP host allowlist omitted public HTTPS host `rikagro.ru`: fixed.
- Bearer validation fails closed on database error.
- Browser auth writes reject cross-site Fetch Metadata and mismatched Origin.

## Open security and interoperability findings
1. **ChatGPT not connected.** No real ChatGPT callback URI has been registered or validated; client table is empty. Do not claim working ChatGPT OAuth.
2. **Dynamic client registration** is absent. Some MCP OAuth clients require DCR; confirm ChatGPT connector's current requirements before enabling it. Do not auto-approve arbitrary redirects.
3. **Resource indicators / RFC 8707** are not implemented; tokens currently bind to the fixed internal audience `nexus-mcp`. Verify MCP client compatibility.
4. **Browser CSRF** uses Origin and Fetch Metadata, but lacks an independent per-session anti-CSRF token. Add CSRF token binding for consent and password changes.
5. **Audit logging** of login, consent, token issuance and revocation is incomplete. Do not log raw credentials or bearer tokens.
6. **OAuth negative and live end-to-end tests** with real HTTPS browser, code replay, revocation, expiry and ChatGPT itself remain outstanding.
7. **MCP tools** are currently read-only diagnostics. Agent registry contains planned capabilities only; no executable AI agents.
8. **Transport security** has a static public host allowlist. Any domain change requires an explicit config review.
9. **Rate limiting** is per username on password login, not a comprehensive IP/client-level throttle. Add reverse-proxy and endpoint-specific throttling.
10. **Operational readiness**: backup restore drill, dependency/security scan, incident runbook, and monitoring are still pending.
11. The first owner bootstrap credential remains in a root-only file until the owner rotates it. Delete securely after rotation.

## Safety policy
- No autonomous shell, Docker, Godot, Blender or GitHub writes are enabled.
- Never expose internal bearer secrets, OAuth codes, credentials or private files to the dashboard or logs.
- Never restart unrelated BASHECO/GameForge containers as part of NEXUS deployment.

## Integration handoff
- Public MCP endpoint: `https://rikagro.ru/nexusai/mcp/`
- OAuth authorization: `https://rikagro.ru/nexusai/oauth/authorize`
- OAuth token: `https://rikagro.ru/nexusai/oauth/token`
- OAuth discovery: `https://rikagro.ru/nexusai/.well-known/oauth-authorization-server`
- Protected resource metadata: `https://rikagro.ru/nexusai/.well-known/oauth-protected-resource`
- **ChatGPT connection requires explicit user action in ChatGPT's plugin/connector UI** and the real callback URI; a server deployment alone cannot complete this step.
