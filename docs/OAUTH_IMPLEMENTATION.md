# OAuth 2.1 implementation gate

**Current status:** PKCE S256 helpers and dormant database schema only. There is **no OAuth authorization server** and **no ChatGPT connection**. The existing internal MCP token is not a user-facing OAuth credential.

## Required before enabling public access

1. HTTPS canonical issuer URL, trusted proxy headers and secure cookies.
2. OAuth Authorization Code flow with mandatory S256 PKCE, cryptographically random single-use codes, exact pre-registered redirect URI match, `state` managed by client, short code lifetime.
3. Authenticated user consent screen, scopes and per-project RBAC; do not auto-consent unknown clients.
4. Client registration policy appropriate for ChatGPT; validate redirect URIs and origins, avoid open registration abuse.
5. Access tokens hashed at rest, short-lived, audience-restricted, revocable; refresh token rotation if refresh tokens are implemented.
6. RFC 8414 metadata, OAuth Protected Resource Metadata, discovery, proper WWW-Authenticate challenges and resource indicator support.
7. Bearer validation on **all** MCP transports and tool calls, including streaming. Prevent unauthenticated MCP sessions.
8. CSRF protection, session fixation prevention, brute-force protection by user and source, rate limits and audit events.
9. Test browser and ChatGPT end-to-end authorization, revocation, wrong audience, wrong client, invalid PKCE, redirect URI mismatch and expired/used code.
10. Backup, rollback and security review before changing public Nginx.

Do not expose NEXUS AI publicly before these controls are implemented and verified.
