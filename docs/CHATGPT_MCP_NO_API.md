# NEXUS AI for ordinary ChatGPT, no OpenAI API key

Architecture: ChatGPT conversation (reasoning and tool orchestration) -> OAuth-protected NEXUS AI MCP -> narrowly scoped server tools. This implementation does not call OpenAI API, Codex CLI or any paid model API. ChatGPT subscription usage limits still apply. ChatGPT does not automatically continue reasoning after its turn ends.

## Available MCP tools
- nexus_status, nexus_capabilities: service health
- nexus_agents, nexus_workflow: catalog and workflow summary
- nexus_godot_inspect_script(source, filename): inspect user-supplied .gd text
- nexus_godot_inspect_shader(source, filename): inspect user-supplied .gdshader text

Both Godot tools are read-only, have 100,000-character input limits, do not open server files, and do not run Godot, Blender or shell commands. Findings are heuristics, not performance measurements. Source text is sent through the connected MCP service, so do not paste credentials or proprietary code unless permitted.

## Roadmap
1. Explicit per-project read-only registration and access grants, with no access to unrelated directories.
2. Read-only Godot project inventory, scenes, scripts and shader analysis in an isolated read-only mount.
3. Changes only in isolated worktrees/branches, requiring per-action approval and tested rollback.
4. Godot validation and Android build in isolated resource-limited containers.
5. Optional Blender analysis, asset workflows, screenshot comparison and profiling.

## Security
Existing OAuth client uses mcp:read only. Do not add MCP write or remote execution tools without separate user identity, authorization and consent. Do not mount the whole VPS or Docker socket into the MCP container. Avoid background workers that call external models.
