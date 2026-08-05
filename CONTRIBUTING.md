# Contributing

Atlas Memory Loop is intentionally small. Changes should preserve these invariants:

- Markdown remains the canonical store.
- Runtime and index data remain rebuildable or disposable.
- Hooks fail open unless explicitly run with `--strict`.
- New host integrations normalize events before touching storage.
- Automatic consolidation never overwrites canonical knowledge silently.

Create a virtual environment, install the development extra, then run:

```bash
ruff check .
ruff format --check .
python -W error::ResourceWarning -m unittest discover -s tests -v
python -m build
```

Please include tests for behavior changes and update `CHANGELOG.md` when user-visible behavior changes.
