# Godot Project Inspector 0.4: BASHECO

Read-only project inspection through ordinary ChatGPT MCP, without OpenAI API keys or Codex CLI.

## Scope
Only `basheco` is registered. Docker mounts host `/opt/basheco/client` to `/projects/basheco` in NEXUS API as read-only. No Godot execution, project modification or additional background service.

## MCP
- `nexus_godot_projects()`: allowlisted project IDs and availability.
- `nexus_godot_project_report(project_id="basheco",include_files=false)`: inventory, project settings, scene node counts and static heuristic findings.
- `nexus_godot_project_file(project_id,relative_path)`: single-file structural or heuristic analysis.

Supported: project.godot, .tscn, .tres, .gd, .gdshader. Limits: 1200 files, 100 KB/file, 80 findings. No absolute paths, traversal or symlink following. Excludes .git, .godot and build output.

## Security
The current OAuth mcp:read scope is not per-project. Anyone authorized to access the NEXUS MCP connector can inspect registered BASHECO metadata. Do not add sensitive projects before per-user project grants. File-system confinement additionally relies on the read-only Docker mount. Static findings are not syntax validation, runtime testing or FPS measurements.

## Example
Ask in ChatGPT: «NEXUS AI Final, вызови nexus_godot_projects и nexus_godot_project_report для basheco. Проанализируй проблемы архитектуры сцен и графики. Ничего не меняй.»

## Next
Per-user project grants and audit logs, isolated Godot CLI checks, approved worktree edits and Android builds.
