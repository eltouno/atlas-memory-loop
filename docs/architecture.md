# Architecture

## One loop, two integration surfaces

Atlas Memory Loop separates automatic observation from deliberate agent actions.

```text
                       HOST (Codex, Claude, ...)
                         |                 |
                  lifecycle hooks      MCP tools
                         |                 |
                         v                 v
                    Event normalizer   Recall / remember
                         |                 |
                         +------ MemoryEngine ------+
                                |             |
                                v             v
                         RuntimeStore      SearchIndex
                         JSONL + state     SQLite FTS5
                                |             ^
                                v             |
                         deterministic distillation
                                |
                                v
                         MarkdownStore / Obsidian
```

Hooks and MCP are complementary, not competing implementations:

- Hooks are host-owned triggers. They make capture reliable without asking the model to remember to call a tool.
- MCP is a standardized agent-facing interface. It enables explicit recall and reviewable memory proposals.
- Both call the same `MemoryEngine`, so storage rules and lifecycle semantics stay identical.

## Data layers

### 1. Runtime journal

Each host session maps deterministically to one Atlas session ID. Events are appended to `events.jsonl`; `session.json` tracks status, counts, timestamps, output path, and retention.

This layer is optimized for safe writes, recovery, and debugging. It is not the long-term memory and should normally be excluded from Git.

### 2. Canonical Markdown

Finalization produces one readable session note. Explicit `remember` calls produce candidate notes with `status: pending`. Humans can inspect, link, edit, promote, or reject these notes in Obsidian.

The engine never promotes a candidate into canonical domain knowledge silently.

### 3. Derived SQLite index

SQLite FTS5 indexes Markdown and provides BM25-ranked keyword recall. It can be deleted at any time and rebuilt with `atlas-memory index`.

No embeddings or external vector service are used in the MVP.

## Normalized lifecycle

| Normalized event | Typical native hook | Effect |
| --- | --- | --- |
| `session.open` | `SessionStart` | Open or resume a journal; optionally inject recall. |
| `turn.input` | `UserPromptSubmit` | Record the user objective. |
| `tool.before` | `PreToolUse` | Record reduced tool intent. |
| `tool.completed` | `PostToolUse` | Record reduced successful outcome. |
| `tool.failed` | `PostToolUseFailure` | Record the error for later learning. |
| `turn.checkpoint` | `Stop` | Save progress without closing the session. |
| `context.refresh` | `PreCompact` | Refresh bounded context around compaction. |
| `session.finalize` | `SessionEnd` | Distill to Markdown and set retention. |

`Stop` must not be treated as a session end: agent hosts may emit it after every completed response while the same conversation continues.

## Session state machine

```text
open <-> checkpointed
  |          |
  +----------+
       |
   finalizing
       |
    distilled ---- retention elapsed ----> runtime journal purged
```

If the host disappears without `SessionEnd`, `atlas-memory recover` finalizes sessions that have been idle past a configured threshold.

## Failure rules

- Hook capture is fail-open by default: memory failure must not block primary agent work.
- CLI and MCP commands remain strict and report errors to their caller.
- Journal writes use a lock file and atomic state replacement.
- Consecutive duplicate hook deliveries are suppressed.
- Raw journals are purged only when their durable Markdown output still exists.
- The index is never considered canonical.

## Token and latency model

Capture, redaction, indexing, and deterministic distillation do not call an LLM. Their token cost is zero. Recall adds only the selected context, bounded by `ATLAS_MEMORY_TOKEN_BUDGET` or the command/tool argument.

Every hook starts a short Python process in the current integration examples. This adds local process and disk I/O latency but avoids a permanent daemon. MCP stdio amortizes startup over the host session because the host keeps that subprocess alive.

## Extension points

- Add host-native names in `hooks.py` without changing the internal event schema.
- Replace or augment FTS5 behind `SearchIndex` while preserving Markdown as canonical.
- Add an optional LLM distiller that writes candidates, never direct canonical edits.
- Add consolidation policies for decisions, corrections, preferences, and recurring failures.
- Package host integrations separately as their hook systems stabilize.
