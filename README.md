# Atlas Memory Loop

Markdown-first persistent memory for agentic AI hosts.

Atlas Memory Loop captures lifecycle events through host hooks, keeps a short-lived JSONL journal, distills completed sessions into readable Markdown, and exposes bounded recall through a local MCP stdio server. Obsidian remains the human interface; Markdown remains the source of truth.

> Status: alpha. The storage model and CLI are usable; host hook APIs can still evolve.

## Naming

**Atlas Memory Loop** is the full product name. **Memory Loop** is the accepted
short name. **Atlas** alone is not a synonym for this product: it may describe a
user's vault, workspace, or broader knowledge system.

Technical identifiers such as the `atlas-memory` command, the `atlas_memory`
Python package, `.atlas-runtime`, and the `<atlas-context>` envelope remain stable
for compatibility.

## Easiest install: ask your AI agent

Give an AI coding agent access to the project you want to connect, then send it
this request:

```text
Install Atlas Memory Loop from https://github.com/eltouno/atlas-memory-loop
for this project. Follow docs/agent-installation.md from that repository.
Explain each approval in plain language, perform the configuration for me,
run every automated check, and clearly identify the final Codex action I must
approve myself.
```

The repository contains a complete agent execution protocol covering discovery,
isolated installation, non-destructive configuration, approval boundaries,
verification, rollback, and a fresh-host smoke test. The user should not need to
translate the guide into terminal commands. See
[`docs/agent-installation.md`](docs/agent-installation.md).

## Why this exists

Most agent sessions end with useful knowledge trapped in a transcript. Atlas Memory Loop turns that knowledge into a controlled loop:

```text
host hook -> temporary event journal -> deterministic distillation -> Markdown
     ^                                                        |
     |---------------- bounded recall (SQLite FTS5) -----------|
```

The first release deliberately avoids an LLM during distillation. Capture and consolidation therefore consume no model tokens. Tokens are used only when recalled Markdown is injected into an agent context, and that injection has a configurable budget.

## Design principles

- Markdown is canonical; SQLite is disposable and rebuildable.
- Hooks capture automatically and fail open if memory is unavailable.
- `UserPromptSubmit` captures the user objective and injects relevant bounded context.
- `Stop` checkpoints the turn and refreshes a durable Markdown snapshot without finalizing.
- Raw runtime journals expire only after a durable Markdown note exists.
- Explicit memories enter a review queue instead of silently rewriting knowledge.
- MCP uses stdio: the AI host starts and stops the process automatically.
- No daemon, cloud account, vector database, or API key is required.

## Storage model

```text
your-vault/
├── 70_State/
│   ├── agent_sessions/YYYY/MM/*.md       # durable session summaries
│   └── memory_candidates/*.md            # review queue
└── .atlas-runtime/                        # temporary, gitignored
    ├── sessions/<session-id>/
    │   ├── events.jsonl                   # append-only event journal
    │   └── session.json                   # lifecycle and retention state
    └── index/atlas.sqlite                 # derived FTS5 search index
```

Temporary session files are retained for 14 days by default after successful distillation. `atlas-memory cleanup --apply` removes only expired journals whose Markdown output still exists.

## Install

Python 3.10 or newer is required.

From GitHub:

```bash
pipx install "git+https://github.com/eltouno/atlas-memory-loop.git"
```

`pipx` keeps the command isolated from application dependencies while making it
available across projects. If `pipx` is unavailable, an AI agent can create and
manage a dedicated virtual environment by following the installation protocol.

For local development:

```bash
git clone https://github.com/eltouno/atlas-memory-loop.git
cd atlas-memory-loop
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Five-minute smoke test

```bash
export ATLAS_MEMORY_VAULT="/absolute/path/to/your/Obsidian/vault"

atlas-memory init
atlas-memory session start --host manual --session-id demo-1 --project demo
atlas-memory remember "Markdown is the canonical memory." --kind decision --project demo
atlas-memory session checkpoint --host manual --session-id demo-1 --project demo
atlas-memory session finalize --host manual --session-id demo-1
atlas-memory recall "canonical memory" --project demo
atlas-memory doctor
```

Open `70_State/agent_sessions/` and `70_State/memory_candidates/` in Obsidian to inspect what was written.

## Recommended: guided Codex setup

Run the setup command from the Codex project root. It displays every target, asks for one confirmation, backs up existing files, merges configuration non-destructively, initializes the vault, and rolls host configuration back if validation fails.

```bash
atlas-memory setup codex --vault /absolute/path/to/your/vault
```

Preview without changing anything:

```bash
atlas-memory setup codex --vault /absolute/path/to/your/vault --dry-run
```

The default scope is derived from the current project directory name, not the vault name. Use `--project-name` to select an explicit durable scope or disambiguate projects with the same directory name. The Codex integration installs two hooks: `UserPromptSubmit` captures the prompt and recalls relevant context, while `Stop` records the latest assistant response and writes a durable checkpoint snapshot. Restart Codex after setup, open `/hooks`, and trust the two generated commands.

Automated verification intentionally reports hook trust as a remaining user
action: Codex binds trust to the exact command definition and requires review in
the host UI.

Remove only the managed Codex integration while preserving Markdown memory:

```bash
atlas-memory setup remove codex
```

## Optional: initialize the first memories

The repository includes the
[`memory-loop-startup`](skills/memory-loop-startup/SKILL.md) skill for a new or
sparse vault. Ask Codex to install the skill directly from
`https://github.com/eltouno/atlas-memory-loop/tree/main/skills/memory-loop-startup`,
then invoke it with `$memory-loop-startup`. The skill is separate from the
automatic session hooks and runs only when requested.

The skill first scans existing memory, then guides the user through four domains:

1. user and collaboration;
2. project and outcomes;
3. environment and methods;
4. memory governance.

Each stage follows the same review gate: the agent asks the question series,
waits for the answers, reformulates durable knowledge, obtains explicit
validation, and only then creates a Memory Loop candidate. Final health and
recall checks must pass before initialization is reported as complete.

## MCP stdio

MCP complements hooks: hooks observe lifecycle events automatically; MCP lets the agent deliberately recall or propose memory.

Codex CLI:

```bash
codex mcp add atlas-memory \
  --env ATLAS_MEMORY_VAULT=/absolute/path/to/your/vault \
  -- atlas-memory mcp
```

Claude Code:

```bash
claude mcp add --transport stdio \
  --env ATLAS_MEMORY_VAULT=/absolute/path/to/your/vault \
  atlas-memory -- atlas-memory mcp
```

The host launches the stdio process when needed and closes it with the session. There is no permanent server to supervise.

Available MCP tools:

- `atlas_recall`: search and return bounded context.
- `atlas_remember`: create a reviewable Markdown candidate.
- `atlas_session_start`, `atlas_session_checkpoint`, `atlas_session_finalize`: explicit lifecycle fallback.
- `atlas_health`: inspect storage and index health.

## Hooks

Ready-to-adapt examples are provided in [`integrations/`](integrations/). Set `ATLAS_MEMORY_VAULT` in the environment that launches the host, then copy the relevant configuration.

- Claude Code: merge [`integrations/claude/settings.hooks.json`](integrations/claude/settings.hooks.json) into `.claude/settings.json` or `~/.claude/settings.json`.
- Codex: copy [`integrations/codex/hooks.json`](integrations/codex/hooks.json) to `.codex/hooks.json` or `~/.codex/hooks.json`. Hooks are enabled by default in current Codex releases.

See [`docs/integrations.md`](docs/integrations.md) for lifecycle semantics, trust prompts, caveats, and manual fallback commands.

## CLI overview

```text
atlas-memory init
atlas-memory hook --host HOST [--event EVENT] [--inject] [--structured-output]
atlas-memory session start|checkpoint|finalize ...
atlas-memory recall QUERY [--project PROJECT] [--token-budget N]
atlas-memory remember TEXT [--kind KIND] [--project PROJECT]
atlas-memory index
atlas-memory recover [--idle-minutes 120]
atlas-memory cleanup [--apply]
atlas-memory doctor
atlas-memory mcp
atlas-memory setup codex --vault VAULT [--project-root PROJECT] [--project-name NAME] [--dry-run]
atlas-memory setup verify codex [--project-root PROJECT]
atlas-memory setup remove codex [--project-root PROJECT] [--dry-run]
```

## Safety and privacy

Hook payloads are reduced before storage. Common secret fields and token patterns are redacted, and large values are truncated. This is defense in depth, not a guarantee: inspect your hook selection and never point the runtime at a shared location containing sensitive data. See [`SECURITY.md`](SECURITY.md).

## Development

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
.venv/bin/python -m build
```

Architecture and invariants are documented in [`docs/architecture.md`](docs/architecture.md).

## License

MIT
