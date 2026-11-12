# NEXUS AI 0.1: Stage 1 release gate

**Current release status: NOT APPROVED FOR PUBLIC ACCESS.**

## Implemented and checked locally
- PostgreSQL schema and persistent hashed sessions; first owner created via local CLI.
- Scrypt password hashing, owner login and password rotation endpoint.
- OAuth code + S256 PKCE, exact pre-registered callback, 3-minute one-time code, 30-minute hashed bearer tokens, client-token revocation.
- Consent preview, Russian browser consent UI, authorization redirect.
- JSON discovery metadata **only after** `NEXUS_OAUTH_ISSUER` is configured.
- MCP bearer guard fails closed; internal credential is disabled when a public issuer is configured.
- API and dashboard bound to `127.0.0.1:4189`; no public exposure.
- CI: pytest and React build.

## Mandatory blockers before public release
1. User-approved dedicated hostname with DNS pointing to Lunex. Do not reuse another project's host without approval.
2. Backup existing Nginx, inspect existing server blocks and port assignments, configure a separate HTTPS virtual host with a trusted certificate, HTTP-to-HTTPS redirect and safe rollback. Do not alter other apps.
3. Set `NEXUS_OAUTH_ISSUER` to the **exact** HTTPS origin and verify issuer, metadata, reverse-proxy behavior and secure cookies end to end.
4. Register ChatGPT client with its **verified exact callback URI**. Do not guess callbacks, auto-register unknown clients, or log secrets.
5. Test owner login and logout through real HTTPS, consent approve/deny, token exchange, MCP discovery and tool list, token revocation, expiration and replay, and blocked access to all transports.
6. Test OAuth with ChatGPT itself. Browser simulation is not sufficient.
7. Security audit: consent CSRF, origin/host validation behind proxies, rate limiting, audit logs, authorization code binding, resource indicators, metadata and error semantics.
8. Remove or restrict any diagnostic endpoints that reveal unnecessary operational details; verify backups and rollback.
9. Obtain explicit production deployment approval after reviewing the domain, TLS and Nginx changes.

## Rollback
- Keep loopback binding `127.0.0.1:4189:80`.
- Restore the prior Nginx vhost from a timestamped backup if public proxy configuration fails.
- Roll back the application to a tested Git SHA and rebuild only NEXUS containers; never run `docker compose down -v`.
- Preserve PostgreSQL data and existing other Docker projects.

## Owner credentials
- Username: `nexusadmin`.
- Initial random password stored only at `/root/nexus-ai-credentials/initial-owner-password` on Lunex, mode 0600. Never commit or transmit it.
- Rotate after first secure login and remove the bootstrap password file once no longer needed.
