from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from helpers import make_settings

from atlas_memory.engine import MemoryEngine
from atlas_memory.runtime import build_session_id
from atlas_memory.util import isoformat, utc_now


class EngineLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        self.engine = MemoryEngine(self.settings)
        self.engine.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_stop_is_checkpoint_and_session_end_finalizes(self) -> None:
        base = {"session_id": "host-1", "cwd": str(self.root), "project": "atlas"}
        self.engine.capture_hook(
            host="codex",
            hook_name="SessionStart",
            raw_payload={**base, "hook_event_name": "SessionStart"},
        )
        self.engine.capture_hook(
            host="codex",
            hook_name="UserPromptSubmit",
            raw_payload={**base, "prompt": "Implement durable memory"},
        )
        event, _ = self.engine.capture_hook(
            host="codex",
            hook_name="Stop",
            raw_payload={**base, "hook_event_name": "Stop"},
        )
        state = self.engine.runtime.load_state(event.atlas_session_id)
        self.assertIsNotNone(state)
        self.assertEqual(state.status, "checkpointed")
        self.assertIsNone(state.distilled_to)

        snapshot = self.engine.snapshot(event.atlas_session_id)
        state = self.engine.runtime.load_state(event.atlas_session_id)
        self.assertEqual(state.status, "checkpointed")
        self.assertIsNone(state.distilled_to)
        self.assertIn("status: checkpointed", snapshot.read_text(encoding="utf-8"))

        self.engine.capture_hook(
            host="codex",
            hook_name="SessionEnd",
            raw_payload={**base, "hook_event_name": "SessionEnd", "reason": "exit"},
        )
        note = self.engine.finalize_host_session("codex", "host-1")
        state = self.engine.runtime.load_state(event.atlas_session_id)
        self.assertEqual(state.status, "distilled")
        self.assertTrue(note.exists())
        self.assertIn("status: distilled", note.read_text(encoding="utf-8"))
        self.assertIn("Implement durable memory", note.read_text(encoding="utf-8"))

    def test_resuming_a_distilled_session_cancels_pending_retention(self) -> None:
        self.engine.record(
            event_type="session.open",
            host="codex",
            host_session_id="resumed",
            project="atlas",
            cwd=str(self.root),
        )
        session_id = build_session_id("codex", "resumed")
        self.engine.finalize(session_id)

        self.engine.record(
            event_type="turn.input",
            host="codex",
            host_session_id="resumed",
            project="atlas",
            cwd=str(self.root),
            payload={"prompt": "Continue the session"},
        )

        state = self.engine.runtime.load_state(session_id)
        self.assertEqual(state.status, "open")
        self.assertIsNone(state.finalized_at)
        self.assertIsNone(state.distilled_to)
        self.assertIsNone(state.purge_after)

    def test_capture_is_deduplicated_and_redacted(self) -> None:
        payload = {
            "session_id": "host-2",
            "cwd": str(self.root),
            "project": "atlas",
            "tool_name": "Bash",
            "tool_input": {"authorization": "Bearer very-secret-token"},
            "tool_response": "ok",
        }
        event, duplicate = self.engine.capture_hook(
            host="claude", hook_name="PostToolUse", raw_payload=payload
        )
        _, second_duplicate = self.engine.capture_hook(
            host="claude", hook_name="PostToolUse", raw_payload=payload
        )
        self.assertFalse(duplicate)
        self.assertTrue(second_duplicate)
        raw = self.engine.runtime.events_path(event.atlas_session_id).read_text(encoding="utf-8")
        self.assertNotIn("very-secret-token", raw)
        self.assertEqual(len(raw.splitlines()), 1)

    def test_remember_creates_pending_candidate(self) -> None:
        path = self.engine.remember(
            content="Stop must create a checkpoint, not finalize the session.",
            kind="decision",
            project="atlas",
        )
        content = path.read_text(encoding="utf-8")
        self.assertIn("type: memory_candidate", content)
        self.assertIn("status: pending", content)

    def test_cleanup_requires_distilled_note_and_expired_retention(self) -> None:
        self.engine.record(
            event_type="session.open",
            host="codex",
            host_session_id="cleanup",
            project="atlas",
            cwd=str(self.root),
        )
        session_id = build_session_id("codex", "cleanup")
        self.engine.finalize(session_id)
        state = self.engine.runtime.load_state(session_id)
        state.purge_after = isoformat(utc_now() - timedelta(days=1))
        self.engine.runtime.save_state(state)

        self.assertEqual(self.engine.cleanup(dry_run=True), [session_id])
        self.assertTrue(self.engine.runtime.session_dir(session_id).exists())
        self.engine.cleanup(dry_run=False)
        self.assertFalse(self.engine.runtime.session_dir(session_id).exists())


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        concept = self.settings.vault_path / "30_Knowledge" / "concepts" / "memory.md"
        concept.write_text(
            "---\ntype: concept\nproject: atlas\nstatus: active\n---\n\n"
            "# Durable memory\n\nMarkdown is the canonical source of truth.\n",
            encoding="utf-8",
        )
        self.engine = MemoryEngine(self.settings)
        self.engine.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_recall_returns_bounded_context(self) -> None:
        context, results = self.engine.recall(
            "canonical Markdown memory", project="atlas", token_budget=300
        )
        self.assertEqual(len(results), 1)
        self.assertIn("Durable memory", context)
        self.assertIn("<atlas-context", context)

    def test_health_reports_indexed_documents(self) -> None:
        health = self.engine.health()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["indexed_documents"], 1)


if __name__ == "__main__":
    unittest.main()
