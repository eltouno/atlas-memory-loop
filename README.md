# Atlas Memory Loop

Markdown-first persistent memory for agentic AI hosts.

Atlas Memory Loop captures lifecycle events through host hooks, keeps a short-lived JSONL journal, distills completed sessions into readable Markdown, and exposes bounded recall through a local MCP stdio server. Obsidian remains the human interface; Markdown remains the source of truth.

> Status: alpha. The storage model and CLI are usable; host hook APIs can still evolve.

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
- `Stop` creates a checkpoint; `SessionEnd` finalizes the session.
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
python3 -m venv .venv
.venv/bin/pip install "git+https://github.com/eltouno/atlas-memory-loop.git"
```

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

The default scope is the current project. This prevents two projects from accidentally recalling the same vault. Restart Codex after setup and approve its hook trust prompt if one appears.

Remove only the managed Codex integration while preserving Markdown memory:

```bash
atlas-memory setup remove codex
```

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
- Codex: copy [`integrations/codex/hooks.json`](integrations/codex/hooks.json) to `.codex/hooks.json` or `~/.codex/hooks.json`, and enable the stable `hooks` feature if required by your version.

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
atlas-memory setup codex --vault VAULT [--project-root PROJECT] [--dry-run]
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
