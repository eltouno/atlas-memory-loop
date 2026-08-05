# Host integrations

## Guided Codex setup

For a novice-friendly installation, give the repository URL to an AI coding
agent and ask it to follow [`agent-installation.md`](agent-installation.md). That
protocol makes the agent responsible for discovery, execution, and verification
while preserving explicit user approval for package installation, configuration,
and Codex hook trust.

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
- registers a vault-specific MCP name and project-scoped hook commands;
- initializes the runtime and validates the written configuration;
- restores host files automatically if initialization or validation fails.

It also adds local ignore rules for setup backups/state and `.atlas-runtime`. The default memory scope is the project directory name; pass `--project-name NAME` when the vault already uses another project identifier or when two projects share the same directory name. Use `--dry-run` to preview or `--yes` only after the plan has already been explicitly approved.

After installation or an upgrade, verify the generated commands and local runtimes:

```bash
atlas-memory setup verify codex
```

Verification does not execute a hook or modify memory. It checks the managed files, Python import, Codex executable, and stable hooks feature. Trust remains an explicit host action through `/hooks`.

Its JSON result separates passed automated checks from three remaining activation
steps: restart, hook trust, and a fresh-host smoke test. Agents must not describe
the integration as fully operational until those activation steps are confirmed.

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

Copy `integrations/codex/hooks.json` to `.codex/hooks.json` or merge it into `~/.codex/hooks.json`. Hooks are enabled by default in current Codex releases; `integrations/codex/config.toml.example` is retained only for older versions that require an explicit feature override.

The Codex sample deliberately uses only `UserPromptSubmit` and `Stop`. `UserPromptSubmit` captures the actual user prompt and uses it as the bounded-recall query before the model runs. `Stop` captures `last_assistant_message`, checkpoints the turn, and refreshes the durable Markdown snapshot without closing the session.

`SessionEnd` remains supported by the generic hook adapter for hosts that need it, but the guided Codex setup does not install it.

Project-local hooks load only after the project configuration is trusted. Restart Codex from the configured project root, run `/hooks`, verify both generated commands, and trust them. Use `codex features list` and `codex doctor --summary` when diagnosing upgrades or host configuration.

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
