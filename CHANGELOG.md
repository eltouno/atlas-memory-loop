# Changelog

## 0.2.0 - Unreleased

- Add a repository-native, agent-assisted installation protocol with explicit
  approval boundaries, automated verification, and fresh-host completion criteria.
- Expose structured verification and remaining manual actions in Codex setup output.
- Recommend isolated `pipx` installation for a command available across projects.
- Remove legacy managed hooks that use an equivalent Python executable alias and
  make verification reject leftover or duplicate managed handlers.
- Add guided, project-scoped Codex setup with preview and explicit confirmation.
- Add non-destructive TOML/JSON merging, idempotent managed blocks, backups, and rollback.
- Add `setup remove codex` while preserving durable Markdown memory and unrelated host config.
- Simplify Codex setup to two turn-oriented hooks: `UserPromptSubmit` captures and recalls context, while `Stop` checkpoints plus refreshes durable Markdown.
- Migrate away the former managed `SessionEnd` hook without removing unrelated hooks.
- Keep checkpoint snapshots distinct from finalized sessions and capture the latest assistant response.
- Derive project scope from the Codex project path instead of the shared vault name.
- Add `setup verify codex` for non-mutating integration diagnostics.

## 0.1.0 - 2026-08-05

- Add normalized hook capture and explicit session lifecycle.
- Add temporary JSONL journals with deterministic Markdown distillation.
- Add SQLite FTS5/BM25 indexing and bounded context recall.
- Add MCP stdio tools and Claude/Codex integration examples.
- Support the declared Python 3.10 minimum by avoiding `datetime.UTC`.
