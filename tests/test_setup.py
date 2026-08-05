from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from atlas_memory.cli import build_parser, run
from atlas_memory.setup import (
    SetupError,
    _hook_command,
    apply_codex_remove,
    apply_codex_setup,
    build_codex_plan,
    build_codex_remove_plan,
    verify_codex_setup,
)


class CodexSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project = self.root / "project"
        self.vault = self.root / "vault"
        self.project.mkdir()
        (self.vault / "00_System").mkdir(parents=True)
        self.plan = build_codex_plan(
            vault=self.vault,
            project_root=self.project,
            python_executable=sys.executable,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_setup_merges_existing_configuration_and_initializes_vault(self) -> None:
        self.plan.codex_dir.mkdir()
        self.plan.config_path.write_text(
            '[features]\nexperimental = true\n\n[mcp_servers.other]\ncommand = "other"\n',
            encoding="utf-8",
        )
        self.plan.hooks_path.write_text(
            json.dumps(
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo foreign"}]}]}}
            ),
            encoding="utf-8",
        )

        result = apply_codex_setup(self.plan)

        config = self.plan.config_path.read_text(encoding="utf-8")
        hooks = json.loads(self.plan.hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(result["status"], "configured")
        self.assertIn("experimental = true", config)
        self.assertIn("[mcp_servers.other]", config)
        self.assertNotIn("hooks = true", config)
        self.assertIn("[mcp_servers.atlas-memory-vault]", config)
        self.assertEqual(len(hooks["Stop"]), 2)
        self.assertIn("UserPromptSubmit", hooks)
        self.assertNotIn("SessionStart", hooks)
        self.assertNotIn("SessionEnd", hooks)
        self.assertTrue(self.plan.state_path.exists())
        self.assertTrue((self.vault / ".atlas-runtime" / "index" / "atlas.sqlite").exists())
        self.assertIn(".atlas-runtime/", self.plan.vault_gitignore_path.read_text())
        self.assertIn("backups/", self.plan.codex_gitignore_path.read_text())

    def test_setup_is_idempotent(self) -> None:
        apply_codex_setup(self.plan)
        apply_codex_setup(self.plan)

        config = self.plan.config_path.read_text(encoding="utf-8")
        hooks = json.loads(self.plan.hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(config.count("# >>> atlas-memory-loop:atlas-memory-vault"), 1)
        for event in ("UserPromptSubmit", "Stop"):
            self.assertEqual(len(hooks[event]), 1)
        self.assertNotIn("SessionStart", hooks)
        self.assertNotIn("SessionEnd", hooks)

    def test_setup_removes_legacy_session_end_but_preserves_foreign_hook(self) -> None:
        self.plan.codex_dir.mkdir()
        legacy_command = _hook_command(
            self.plan,
            "SessionEnd",
            project_name=self.vault.name,
        )
        self.plan.hooks_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionEnd": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": legacy_command,
                                    }
                                ]
                            },
                            {"hooks": [{"type": "command", "command": "echo foreign"}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        apply_codex_setup(self.plan)

        hooks = json.loads(self.plan.hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(len(hooks["SessionEnd"]), 1)
        self.assertEqual(hooks["SessionEnd"][0]["hooks"][0]["command"], "echo foreign")

    def test_setup_preserves_custom_atlas_handler_in_the_same_group(self) -> None:
        self.plan.codex_dir.mkdir()
        managed = _hook_command(self.plan, "Stop")
        custom = "python -m atlas_memory hook --host codex --event CustomCheckpoint"
        self.plan.hooks_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {"type": "command", "command": managed},
                                    {"type": "command", "command": custom},
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        apply_codex_setup(self.plan)

        hooks = json.loads(self.plan.hooks_path.read_text(encoding="utf-8"))["hooks"]
        commands = [handler["command"] for group in hooks["Stop"] for handler in group["hooks"]]
        self.assertEqual(commands.count(managed), 1)
        self.assertIn(custom, commands)

    def test_project_scope_depends_on_project_root_not_vault(self) -> None:
        other_project = self.root / "other-project"
        other_project.mkdir()
        other_plan = build_codex_plan(
            vault=self.vault,
            project_root=other_project,
            python_executable=sys.executable,
        )

        self.assertNotEqual(self.plan.project_name, other_plan.project_name)
        self.assertEqual(self.plan.mcp_name, other_plan.mcp_name)
        self.assertEqual(self.plan.project_name, "project")
        self.assertNotEqual(self.plan.project_name, self.vault.name)

    def test_project_scope_can_be_explicit(self) -> None:
        explicit_plan = build_codex_plan(
            vault=self.vault,
            project_root=self.project,
            project_name="Atlas Memory",
            python_executable=sys.executable,
        )

        self.assertEqual(explicit_plan.project_name, "atlas-memory")

    def test_setup_refuses_unmanaged_mcp_name_collision(self) -> None:
        self.plan.codex_dir.mkdir()
        original = '[mcp_servers.atlas-memory-vault]\ncommand = "custom"\n'
        self.plan.config_path.write_text(original, encoding="utf-8")

        with self.assertRaises(SetupError):
            apply_codex_setup(self.plan)

        self.assertEqual(self.plan.config_path.read_text(encoding="utf-8"), original)

    def test_remove_preserves_foreign_configuration_and_durable_memory(self) -> None:
        self.plan.codex_dir.mkdir()
        self.plan.hooks_path.write_text(
            '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo foreign"}]}]}}',
            encoding="utf-8",
        )
        apply_codex_setup(self.plan)

        remove_plan = build_codex_remove_plan(self.project)
        result = apply_codex_remove(remove_plan)

        config = self.plan.config_path.read_text(encoding="utf-8")
        hooks = json.loads(self.plan.hooks_path.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(result["status"], "removed")
        self.assertNotIn("atlas-memory-loop:atlas-memory-vault", config)
        self.assertEqual(hooks["Stop"][0]["hooks"][0]["command"], "echo foreign")
        self.assertFalse(self.plan.state_path.exists())
        self.assertTrue((self.vault / "70_State" / "agent_sessions").exists())

    def test_setup_rolls_back_host_files_when_initialization_fails(self) -> None:
        self.plan.codex_dir.mkdir()
        self.plan.config_path.write_text("[features]\nfoo = true\n", encoding="utf-8")
        self.plan.hooks_path.write_text('{"hooks": {}}\n', encoding="utf-8")

        with (
            patch("atlas_memory.setup.MemoryEngine.initialize", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            apply_codex_setup(self.plan)

        self.assertEqual(
            self.plan.config_path.read_text(encoding="utf-8"), "[features]\nfoo = true\n"
        )
        self.assertEqual(self.plan.hooks_path.read_text(encoding="utf-8"), '{"hooks": {}}\n')
        self.assertFalse(self.plan.state_path.exists())

    def test_cli_dry_run_requires_no_confirmation_and_changes_nothing(self) -> None:
        arguments = build_parser().parse_args(
            [
                "setup",
                "codex",
                "--vault",
                str(self.vault),
                "--project-root",
                str(self.project),
                "--dry-run",
            ]
        )
        output = io.StringIO()
        with patch("atlas_memory.cli.require_codex_cli") as codex_cli, redirect_stdout(output):
            return_code = run(arguments)

        self.assertEqual(return_code, 0)
        self.assertIn('"status": "planned"', output.getvalue())
        self.assertFalse(self.plan.codex_dir.exists())
        codex_cli.assert_not_called()

    def test_verify_checks_managed_files_python_and_codex_features(self) -> None:
        apply_codex_setup(self.plan)
        import_result = subprocess.CompletedProcess(
            args=[str(self.plan.python_executable)], returncode=0, stdout="", stderr=""
        )
        feature_result = subprocess.CompletedProcess(
            args=["codex", "features", "list"],
            returncode=0,
            stdout="hooks stable true\n",
            stderr="",
        )

        with (
            patch("atlas_memory.setup.require_codex_cli", return_value="codex"),
            patch(
                "atlas_memory.setup.subprocess.run",
                side_effect=[import_result, feature_result],
            ) as run_command,
        ):
            result = verify_codex_setup(self.project)

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["hooks"], ["UserPromptSubmit", "Stop"])
        self.assertTrue(result["hooks_enabled"])
        self.assertEqual(run_command.call_count, 2)


if __name__ == "__main__":
    unittest.main()
