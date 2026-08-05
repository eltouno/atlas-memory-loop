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
                "hook_event_name": "SessionStart",
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
        self.assertEqual(response["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("Canonical memory", response["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
