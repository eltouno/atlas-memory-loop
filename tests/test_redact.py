from __future__ import annotations

import unittest

from atlas_memory.redact import sanitize


class RedactionTests(unittest.TestCase):
    def test_sensitive_keys_and_known_token_shapes_are_redacted(self) -> None:
        value = sanitize(
            {
                "authorization": "Bearer secret-token-value",
                "nested": {"api_key": "abc", "message": "use sk-abcdefghijklmnop"},
            }
        )
        self.assertEqual(value["authorization"], "[REDACTED]")
        self.assertEqual(value["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(value["nested"]["message"], "use [REDACTED]")

    def test_long_strings_are_truncated(self) -> None:
        value = sanitize("x" * 100, max_chars=20)
        self.assertTrue(value.endswith("[TRUNCATED]"))


if __name__ == "__main__":
    unittest.main()
