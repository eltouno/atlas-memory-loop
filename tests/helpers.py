from __future__ import annotations

from pathlib import Path

from atlas_memory.config import Settings


def make_settings(root: Path) -> Settings:
    vault = root / "vault"
    (vault / "00_System").mkdir(parents=True)
    (vault / "30_Knowledge" / "concepts").mkdir(parents=True)
    return Settings(vault_path=vault, runtime_path=root / "runtime", retention_days=14)
