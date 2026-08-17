from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SessionStatus = Literal[
    "open",
    "checkpointed",
    "finalizing",
    "distilled",
    "recovery_required",
]


@dataclass(slots=True)
class MemoryEvent:
    schema_version: int
    event_id: str
    event_type: str
    timestamp: str
    host: str
    host_session_id: str
    atlas_session_id: str
    project: str
    cwd: str
    payload: dict[str, Any] = field(default_factory=dict)
    sensitivity: str = "normal"
    event_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SessionState:
    schema_version: int
    session_id: str
    host: str
    host_session_id: str
    project: str
    cwd: str
    status: SessionStatus
    started_at: str
    updated_at: str
    checkpointed_at: str | None = None
    finalized_at: str | None = None
    distilled_to: str | None = None
    event_count: int = 0
    recent_hashes: list[str] = field(default_factory=list)
    purge_after: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SessionState:
        fields = cls.__dataclass_fields__
        return cls(**{key: value[key] for key in fields if key in value})


@dataclass(slots=True)
class RecallResult:
    path: str
    title: str
    note_type: str
    project: str
    status: str
    snippet: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    source_session: str
    signal: str
    proposed_memory: str
    candidate_type: str
