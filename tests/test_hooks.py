from __future__ import annotations

import unittest

from atlas_memory.hooks import (
    extract_host_session_id,
    normalize_hook_name,
    normalized_payload,
)


class HookNormalizationTests(unittest.TestCase):
    def test_native_names_are_normalized(self) -> None:
        self.assertEqual(normalize_hook_name("SessionStart"), "session.open")
        self.assertEqual(normalize_hook_name("Stop"), "turn.checkpoint")
        self.assertEqual(normalize_hook_name("SessionEnd"), "session.finalize")
        self.assertEqual(normalize_hook_name("PostToolUseFailure"), "tool.failed")

    def test_session_identifier_variants(self) -> None:
        self.assertEqual(extract_host_session_id({"session_id": "one"}), "one")
        self.assertEqual(extract_host_session_id({"sessionId": "two"}), "two")
        with self.assertRaises(ValueError):
            extract_host_session_id({})

    def test_tool_payload_is_reduced_to_stable_fields(self) -> None:
        payload = normalized_payload(
            "tool.completed",
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "README.md"},
                "tool_response": "ok",
                "transcript_path": "/private/transcript.jsonl",
            },
        )
        self.assertEqual(payload["tool_name"], "Edit")
        self.assertNotIn("transcript_path", payload)


if __name__ == "__main__":
    unittest.main()
