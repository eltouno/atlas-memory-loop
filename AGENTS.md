# Repository guidance

Atlas Memory Loop is a Markdown-first persistent memory layer for agentic hosts.

## Architecture rules

- Markdown is the canonical durable store.
- Runtime JSONL and SQLite indexes are derived or temporary.
- Host-specific hook names must be normalized before reaching the engine.
- `Stop` is a turn checkpoint; only `SessionEnd`, an explicit command, or stale recovery finalizes a session.
- Capture failures must not block the host by default, but they must be visible on stderr.
- Never create a silent secondary memory fallback.
- Core capture, distillation, indexing, and recall must work without an LLM API key.

## Verification

Run before committing:

```bash
python -m unittest discover -s tests -v
ruff check .
```
