from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        (self.vault / "00_System").mkdir(parents=True)
        self.env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(
        self, *arguments: str, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "atlas_memory", "--vault", str(self.vault), *arguments],
            input=stdin,
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def test_init_and_doctor(self) -> None:
        initialized = self.run_cli("init")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        doctor = self.run_cli("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertEqual(json.loads(doctor.stdout)["status"], "ok")

    def test_hook_fails_open_on_invalid_payload(self) -> None:
        result = self.run_cli("hook", "--host", "codex", stdin="not-json")
        self.assertEqual(result.returncode, 0)
        self.assertIn("warning", result.stderr)

    def test_hook_can_emit_structured_context(self) -> None:
        note = self.vault / "30_Knowledge" / "memory.md"
        note.parent.mkdir(parents=True)
        note.write_text("# Canonical memory\n\nMarkdown remains canonical.\n", encoding="utf-8")
        payload = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-structured",
                "cwd": str(self.vault),
                "prompt": "canonical Markdown",
            }
        )
        result = self.run_cli(
            "hook",
            "--host",
            "codex",
            "--inject",
            "--structured-output",
            stdin=payload,
        )
        response = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(response["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("Canonical memory", response["hookSpecificOutput"]["additionalContext"])

    def test_prompt_and_stop_create_a_contentful_checkpoint_snapshot(self) -> None:
        prompt_payload = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-stop",
                "cwd": str(self.vault),
                "prompt": "Implement durable memory",
            }
        )
        prompt_result = self.run_cli(
            "hook",
            "--host",
            "codex",
            "--event",
            "UserPromptSubmit",
            "--project",
            "atlas",
            stdin=prompt_payload,
        )
        payload = json.dumps(
            {
                "hook_event_name": "Stop",
                "session_id": "session-stop",
                "cwd": str(self.vault),
                "last_assistant_message": "Durable memory is implemented and tested.",
            }
        )

        result = self.run_cli(
            "hook",
            "--host",
            "codex",
            "--event",
            "Stop",
            "--project",
            "atlas",
            stdin=payload,
        )

        self.assertEqual(prompt_result.returncode, 0, prompt_result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        notes = list((self.vault / "70_State" / "agent_sessions").rglob("*.md"))
        self.assertEqual(len(notes), 1)
        note = notes[0].read_text(encoding="utf-8")
        self.assertIn("status: checkpointed", note)
        self.assertIn("Implement durable memory", note)
        self.assertIn("Durable memory is implemented and tested.", note)

        state_files = list((self.vault / ".atlas-runtime" / "sessions").glob("*/session.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "checkpointed")
        self.assertIsNone(state["distilled_to"])
        self.assertIsNone(state["purge_after"])


if __name__ == "__main__":
    unittest.main()
