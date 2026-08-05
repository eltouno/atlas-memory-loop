from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from .config import Settings
from .models import MemoryEvent, SessionState
from .redact import sanitize
from .util import atomic_write_json, file_lock, isoformat, slugify, utc_now


def build_session_id(host: str, host_session_id: str) -> str:
    digest = hashlib.sha256(f"{host}:{host_session_id}".encode()).hexdigest()[:16]
    return f"{slugify(host)}-{digest}"


class RuntimeStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def session_dir(self, session_id: str) -> Path:
        return self.settings.sessions_path / slugify(session_id)

    def state_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def events_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "events.jsonl"

    def load_state(self, session_id: str) -> SessionState | None:
        path = self.state_path(session_id)
        if not path.exists():
            return None
        return SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_state(self, state: SessionState) -> None:
        atomic_write_json(self.state_path(state.session_id), state.to_dict())

    def ensure_session(
        self,
        *,
        host: str,
        host_session_id: str,
        project: str,
        cwd: str,
        timestamp: str,
    ) -> SessionState:
        session_id = build_session_id(host, host_session_id)
        state = self.load_state(session_id)
        if state is not None:
            return state
        return SessionState(
            schema_version=1,
            session_id=session_id,
            host=host,
            host_session_id=host_session_id,
            project=project,
            cwd=cwd,
            status="open",
            started_at=timestamp,
            updated_at=timestamp,
        )

    def append(
        self,
        *,
        event_type: str,
        host: str,
        host_session_id: str,
        project: str,
        cwd: str,
        payload: dict[str, Any],
        timestamp: str | None = None,
    ) -> tuple[MemoryEvent, bool]:
        timestamp = timestamp or isoformat()
        clean_payload = sanitize(payload, self.settings.max_event_chars)
        session_id = build_session_id(host, host_session_id)
        fingerprint = json.dumps(
            {
                "event_type": event_type,
                "host": host,
                "host_session_id": host_session_id,
                "project": project,
                "cwd": cwd,
                "payload": clean_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        event_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
        event = MemoryEvent(
            schema_version=1,
            event_id=f"evt_{uuid.uuid4().hex}",
            event_type=event_type,
            timestamp=timestamp,
            host=slugify(host),
            host_session_id=host_session_id,
            atlas_session_id=session_id,
            project=project,
            cwd=cwd,
            payload=clean_payload,
            event_hash=event_hash,
        )

        state_path = self.state_path(session_id)
        with file_lock(state_path):
            state = self.ensure_session(
                host=host,
                host_session_id=host_session_id,
                project=project,
                cwd=cwd,
                timestamp=timestamp,
            )
            # Hooks can occasionally be delivered twice by a host. Suppress only
            # consecutive duplicates so a legitimate repeated action later in the
            # session is still retained.
            if state.recent_hashes and event_hash == state.recent_hashes[-1]:
                return event, True

            events_path = self.events_path(session_id)
            events_path.parent.mkdir(parents=True, exist_ok=True)
            with events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()

            state.project = project or state.project
            state.cwd = cwd or state.cwd
            state.updated_at = timestamp
            state.event_count += 1
            state.recent_hashes = [*state.recent_hashes[-99:], event_hash]
            if event_type == "turn.checkpoint":
                state.status = "checkpointed"
                state.checkpointed_at = timestamp
            elif event_type == "session.finalize":
                state.status = "finalizing"
                state.finalized_at = timestamp
            else:
                state.status = "open"
            self.save_state(state)

        return event, False

    def load_events(self, session_id: str) -> list[MemoryEvent]:
        path = self.events_path(session_id)
        if not path.exists():
            return []
        events: list[MemoryEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(MemoryEvent(**json.loads(line)))
        return events

    def mark_distilled(self, session_id: str, markdown_path: Path) -> SessionState:
        state_path = self.state_path(session_id)
        with file_lock(state_path):
            state = self.load_state(session_id)
            if state is None:
                raise KeyError(f"Unknown session: {session_id}")
            now = utc_now()
            state.status = "distilled"
            state.updated_at = isoformat(now)
            state.finalized_at = state.finalized_at or isoformat(now)
            state.distilled_to = str(markdown_path)
            state.purge_after = isoformat(now + timedelta(days=self.settings.retention_days))
            self.save_state(state)
            return state

    def iter_states(self) -> list[SessionState]:
        if not self.settings.sessions_path.exists():
            return []
        states: list[SessionState] = []
        for path in self.settings.sessions_path.glob("*/session.json"):
            try:
                states.append(SessionState.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError, KeyError):
                continue
        return states
