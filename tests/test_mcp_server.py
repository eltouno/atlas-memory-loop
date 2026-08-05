from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from atlas_memory.config import Settings
from atlas_memory.mcp_server import create_server


class McpServerTests(unittest.TestCase):
    def test_server_exposes_expected_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            server = create_server(Settings(root, root / "runtime"))
            tools = asyncio.run(server.list_tools())

        self.assertEqual(
            {tool.name for tool in tools},
            {
                "atlas_health",
                "atlas_recall",
                "atlas_remember",
                "atlas_session_checkpoint",
                "atlas_session_finalize",
                "atlas_session_start",
            },
        )


if __name__ == "__main__":
    unittest.main()
