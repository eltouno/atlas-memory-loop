from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when Atlas Memory Loop cannot resolve a valid configuration."""


def _discover_vault(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "00_System").is_dir() or (candidate / ".obsidian").is_dir():
            return candidate
    return None


@dataclass(frozen=True, slots=True)
class Settings:
    vault_path: Path
    runtime_path: Path
    retention_days: int = 14
    context_token_budget: int = 2_000
    max_event_chars: int = 8_000

    @classmethod
    def resolve(
        cls,
        vault: str | Path | None = None,
        runtime: str | Path | None = None,
    ) -> Settings:
        vault_value = vault or os.environ.get("ATLAS_MEMORY_VAULT")
        vault_path = Path(vault_value).expanduser() if vault_value else _discover_vault(Path.cwd())
        if vault_path is None:
            raise ConfigurationError("No vault found. Pass --vault or set ATLAS_MEMORY_VAULT.")
        vault_path = vault_path.resolve()

        runtime_value = runtime or os.environ.get("ATLAS_MEMORY_RUNTIME")
        runtime_path = (
            Path(runtime_value).expanduser().resolve()
            if runtime_value
            else (vault_path / ".atlas-runtime").resolve()
        )

        retention = int(os.environ.get("ATLAS_MEMORY_RETENTION_DAYS", "14"))
        budget = int(os.environ.get("ATLAS_MEMORY_TOKEN_BUDGET", "2000"))
        max_chars = int(os.environ.get("ATLAS_MEMORY_MAX_EVENT_CHARS", "8000"))
        if retention < 1:
            raise ConfigurationError("ATLAS_MEMORY_RETENTION_DAYS must be >= 1")
        if budget < 100:
            raise ConfigurationError("ATLAS_MEMORY_TOKEN_BUDGET must be >= 100")
        if max_chars < 256:
            raise ConfigurationError("ATLAS_MEMORY_MAX_EVENT_CHARS must be >= 256")

        return cls(
            vault_path=vault_path,
            runtime_path=runtime_path,
            retention_days=retention,
            context_token_budget=budget,
            max_event_chars=max_chars,
        )

    @property
    def sessions_path(self) -> Path:
        return self.runtime_path / "sessions"

    @property
    def index_path(self) -> Path:
        return self.runtime_path / "index" / "atlas.sqlite"

    @property
    def session_notes_path(self) -> Path:
        return self.vault_path / "70_State" / "agent_sessions"

    @property
    def candidates_path(self) -> Path:
        return self.vault_path / "70_State" / "memory_candidates"

    def ensure_directories(self) -> None:
        for path in (
            self.vault_path,
            self.sessions_path,
            self.index_path.parent,
            self.session_notes_path,
            self.candidates_path,
        ):
            path.mkdir(parents=True, exist_ok=True)
