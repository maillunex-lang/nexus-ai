# NEXUS AI Meshy Agent 6.1 (read-only preparation)

Official Meshy API docs: https://docs.meshy.ai/en/api/balance and https://docs.meshy.ai/en/api/text-to-3d.

Implemented: optional `NEXUS_MESHY_API_KEY` environment variable (no key in repository), a strictly GET-only client for balance and up to ten recent text-to-3D API tasks, bounded responses, 8s timeout, no redirects, sanitized output and error codes. No paid POST requests, uploads, downloads, task deletion or generation. No additional Python dependencies.

MCP exposes only `nexus_meshy_status`, a public-safe flag for whether integration is configured. **Balance and task data are NOT exposed through MCP** because current MCP bearer guard authenticates a token but does not enforce a distinct owner's identity and permission. Exposing billing or private task data now would be unsafe. These functions remain internal until owner-only authorization and audit are implemented.

Current deployment deliberately does NOT configure an API key, so the integration reports `configured=false`. The user's Meshy website Premium plan does not necessarily grant API credits. Do not copy credentials from browser or other apps. Provision a new API key only with user's explicit approval through a secure secret channel; do not paste it into chat, commit it, or echo it in logs. A server-side secret should be mounted read-only into NEXUS AI only, not shared with other containers. Before enabling any private read tool, implement user identity and ownership checks.

Follow-on 6.2: explicit cost preview and user approval for each paid operation; never trigger billable generation from a status check.
