# Host integrations

## Guided Codex setup

For Codex, the recommended path is the project-scoped setup assistant:

```bash
cd /absolute/path/to/the/codex/project
atlas-memory setup codex --vault /absolute/path/to/the/vault
```

The assistant:

- verifies the vault, project root, Python environment, and Codex CLI;
- displays the exact plan and requires confirmation;
- creates timestamped local backups under `.codex/backups/atlas-memory-loop/`;
- merges `.codex/config.toml` and `.codex/hooks.json` without replacing foreign entries;
- registers a vault-specific MCP name and explicit hook commands;
- initializes the runtime and validates the written configuration;
- restores host files automatically if initialization or validation fails.

It also adds local ignore rules for setup backups/state and `.atlas-runtime`. Use `--dry-run` to preview or `--yes` only after the plan has already been explicitly approved.

To remove the managed integration without deleting runtime journals or Markdown memory:

```bash
atlas-memory setup remove codex
```

## Shared prerequisite

Install `atlas-memory` in an environment visible to the AI host, then give the host an absolute vault path:

```bash
export ATLAS_MEMORY_VAULT="/absolute/path/to/your/Obsidian/vault"
atlas-memory init
```

If GUI-launched applications do not inherit your shell environment, put `--vault /absolute/path/to/vault` before the `hook` or `mcp` subcommand in each configuration command.

## Claude Code hooks

Claude Code stores hooks inside `settings.json`; a standalone `.claude/hooks.json` is not loaded. Merge the `hooks` object from `integrations/claude/settings.hooks.json` into either:

- `.claude/settings.json` for the current project, or
- `~/.claude/settings.json` for the current user.

The sample captures prompts and tool results, checkpoints on `Stop`, and finalizes on `SessionEnd`. `SessionStart` performs a bounded recall and returns it as structured `additionalContext`.

Use `/hooks` in Claude Code to inspect and trust the commands. Keep the hooks fast; their timeout is intentionally short.

## Codex hooks

Copy `integrations/codex/hooks.json` to `.codex/hooks.json` or merge it into `~/.codex/hooks.json`. If your Codex version requires explicit activation, merge this into `.codex/config.toml`:

```toml
[features]
hooks = true
```

The conservative Codex sample uses the lifecycle events confirmed in current public examples: `SessionStart`, `Stop`, and `SessionEnd`. Add tool hooks only after confirming that your installed Codex version exposes them.

Codex hook support is evolving. Project-local hook discovery may differ between releases and worktree modes; a user-level configuration is the practical fallback. Run `codex features list` and use the host's own diagnostics after upgrades.

## MCP stdio

MCP is optional but recommended. It gives the agent explicit, portable tools while hooks cover automatic lifecycle capture.

Codex:

```bash
codex mcp add atlas-memory \
  --env ATLAS_MEMORY_VAULT=/absolute/path/to/your/vault \
  -- atlas-memory mcp
codex mcp get atlas-memory
```

Claude Code:

```bash
claude mcp add --transport stdio \
  --env ATLAS_MEMORY_VAULT=/absolute/path/to/your/vault \
  atlas-memory -- atlas-memory mcp
claude mcp get atlas-memory
```

The host owns the subprocess lifecycle. It starts the local server when connecting and stops it when the host session closes.

## Manual fallback

Any agent host capable of running commands can use the explicit lifecycle even without hooks or MCP:

```bash
atlas-memory session start \
  --host my-agent --session-id SESSION_ID --project PROJECT --cwd "$PWD"

atlas-memory session checkpoint \
  --host my-agent --session-id SESSION_ID --project PROJECT --cwd "$PWD"

atlas-memory session finalize \
  --host my-agent --session-id SESSION_ID
```

This makes the core algorithm host-agnostic. A new integration needs only a mapping from native lifecycle events to these normalized operations.
