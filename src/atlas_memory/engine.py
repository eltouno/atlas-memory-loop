from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .candidates import extract_memory_candidates
from .config import Settings
from .distill import render_session_markdown
from .hooks import (
    extract_host_session_id,
    extract_project,
    normalize_hook_name,
    normalized_payload,
)
from .markdown_store import MarkdownStore
from .models import MemoryEvent, RecallResult, SessionState
from .runtime import RuntimeStore, build_session_id
from .search import SearchIndex
from .util import isoformat, utc_now

logger = logging.getLogger(__name__)


class MemoryEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = RuntimeStore(settings)
        self.markdown = MarkdownStore(settings)
        self.index = SearchIndex(settings)

    def initialize(self) -> dict[str, str]:
        self.settings.ensure_directories()
        self.index.sync()
        return {
            "vault": str(self.settings.vault_path),
            "runtime": str(self.settings.runtime_path),
            "index": str(self.settings.index_path),
        }

    def capture_hook(
        self,
        *,
        host: str,
        raw_payload: dict[str, Any],
        hook_name: str | None = None,
        project: str | None = None,
    ) -> tuple[MemoryEvent, bool]:
        event_type = normalize_hook_name(
            hook_name
            or str(
                raw_payload.get("hook_event_name", raw_payload.get("hookEventName", "observation"))
            )
        )
        host_session_id = extract_host_session_id(raw_payload)
        resolved_project = extract_project(raw_payload, project)
        cwd = str(raw_payload.get("cwd") or Path.cwd())
        payload = normalized_payload(event_type, raw_payload)
        return self.runtime.append(
            event_type=event_type,
            host=host,
            host_session_id=host_session_id,
            project=resolved_project,
            cwd=cwd,
            payload=payload,
        )

    def record(
        self,
        *,
        event_type: str,
        host: str,
        host_session_id: str,
        project: str,
        cwd: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[MemoryEvent, bool]:
        return self.runtime.append(
            event_type=event_type,
            host=host,
            host_session_id=host_session_id,
            project=project,
            cwd=cwd,
            payload=payload or {},
        )

    def finalize(self, session_id: str) -> Path:
        state = self.runtime.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown session: {session_id}")
        events = self.runtime.load_events(session_id)
        path = self._write_distillation(state, events, note_status="distilled")
        self.runtime.mark_distilled(session_id, path)
        self.index.sync()
        return path

    def snapshot(self, session_id: str) -> Path:
        """Write the current session note without closing the session lifecycle."""

        state = self.runtime.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown session: {session_id}")
        events = self.runtime.load_events(session_id)
        return self._write_distillation(state, events, note_status="checkpointed")

    def _write_distillation(
        self,
        state: SessionState,
        events: list[MemoryEvent],
        *,
        note_status: str,
    ) -> Path:
        candidates = extract_memory_candidates(events, source_session=state.session_id)
        markdown = render_session_markdown(
            state,
            events,
            note_status=note_status,
            candidates=candidates,
        )
        path = self.markdown.write_session(state, markdown)
        for candidate in candidates:
            try:
                self.markdown.write_candidate(
                    content=candidate.proposed_memory,
                    kind=candidate.candidate_type,
                    project=state.project,
                    source_session_id=candidate.source_session,
                    signal=candidate.signal,
                )
            except Exception:
                logger.exception(
                    "failed to persist memory candidate for session=%s",
                    state.session_id,
                )
        return path

    def finalize_host_session(self, host: str, host_session_id: str) -> Path:
        return self.finalize(build_session_id(host, host_session_id))

    def remember(
        self,
        *,
        content: str,
        kind: str = "observation",
        project: str = "global",
        source_session_id: str | None = None,
    ) -> Path:
        if not content.strip():
            raise ValueError("Memory content cannot be empty")
        path = self.markdown.write_candidate(
            content=content,
            kind=kind,
            project=project,
            source_session_id=source_session_id,
        )
        self.index.sync()
        return path

    def recall(
        self,
        query: str,
        *,
        project: str | None = None,
        limit: int = 8,
        token_budget: int | None = None,
    ) -> tuple[str, list[RecallResult]]:
        self.index.sync()
        results = self.index.search(query, project=project, limit=limit)
        budget = token_budget or self.settings.context_token_budget
        header = f'<atlas-context project="{project or "global"}">'
        footer = "</atlas-context>"
        selected: list[str] = []
        used = max(1, (len(header) + len(footer)) // 4)
        kept_results: list[RecallResult] = []

        for result in results:
            block = f"- [{result.note_type}] {result.title} ({result.path})\n  {result.snippet}"
            cost = max(1, len(block) // 4)
            if used + cost > budget:
                continue
            selected.append(block)
            kept_results.append(result)
            used += cost

        if not selected:
            return "", []
        return f"{header}\n" + "\n".join(selected) + f"\n{footer}", kept_results

    def recover_stale(self, max_idle_minutes: int = 120) -> list[Path]:
        now = utc_now()
        recovered: list[Path] = []
        for state in self.runtime.iter_states():
            if state.status == "distilled":
                continue
            try:
                updated = datetime.fromisoformat(state.updated_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if (now - updated).total_seconds() < max_idle_minutes * 60:
                continue
            state.status = "recovery_required"
            state.updated_at = isoformat(now)
            self.runtime.save_state(state)
            recovered.append(self.finalize(state.session_id))
        return recovered

    def cleanup(self, *, dry_run: bool = True) -> list[str]:
        now = utc_now()
        purgeable: list[str] = []
        for state in self.runtime.iter_states():
            if state.status != "distilled" or not state.purge_after or not state.distilled_to:
                continue
            distilled_path = Path(state.distilled_to)
            if not distilled_path.exists():
                continue
            try:
                purge_after = datetime.fromisoformat(state.purge_after.replace("Z", "+00:00"))
            except ValueError:
                continue
            if purge_after > now:
                continue
            purgeable.append(state.session_id)
            if not dry_run:
                shutil.rmtree(self.runtime.session_dir(state.session_id))
        return purgeable

    def health(self) -> dict[str, Any]:
        states = self.runtime.iter_states()
        counts: dict[str, int] = {}
        for state in states:
            counts[state.status] = counts.get(state.status, 0) + 1
        return {
            "status": "ok",
            "vault": str(self.settings.vault_path),
            "runtime": str(self.settings.runtime_path),
            "index": str(self.settings.index_path),
            "indexed_documents": self.index.document_count(),
            "sessions": counts,
        }

    @staticmethod
    def json_output(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
