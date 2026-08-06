# Repository guidance

Atlas Memory Loop is a Markdown-first persistent memory layer for agentic hosts.

## Product naming

- Use **Atlas Memory Loop** as the full product name and **Memory Loop** as its
  short name.
- Never use **Atlas** alone as a synonym for the product. Atlas may refer to a
  user's vault, workspace, or wider knowledge system.
- Keep compatibility identifiers such as `atlas-memory`, `atlas_memory`,
  `.atlas-runtime`, and `<atlas-context>` unchanged unless a dedicated migration
  explicitly replaces them.

## Agent-assisted installation

When a user asks to install, configure, upgrade, migrate, verify, or remove Atlas
Memory Loop, follow [`docs/agent-installation.md`](docs/agent-installation.md).

- Communicate in the user's language and keep shell details out of the explanation
  unless they ask for them.
- Perform read-only discovery before asking questions.
- Never guess a vault when several candidates exist.
- Show the generated setup plan and obtain explicit user approval before applying it.
- Do not use `--yes` until that exact plan has been approved.
- Never disable Codex sandboxing or hook trust to make installation easier.
- Run the documented automated checks and report separately what still requires a
  user action in the host UI.
- Do not call the integration fully operational until hook trust and a fresh-host
  smoke test have been confirmed.

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
