from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigurationError, Settings
from .engine import MemoryEngine
from .util import atomic_write_json, atomic_write_text, isoformat, slugify

MANAGED_PREFIX = "atlas-memory-loop"
STATE_FILENAME = "atlas-memory-loop.json"
HOOK_EVENTS = ("SessionStart", "Stop", "SessionEnd")


class SetupError(ValueError):
    """Raised when setup cannot safely merge or remove host configuration."""


@dataclass(frozen=True, slots=True)
class CodexSetupPlan:
    vault_path: Path
    project_root: Path
    codex_dir: Path
    config_path: Path
    hooks_path: Path
    state_path: Path
    codex_gitignore_path: Path
    vault_gitignore_path: Path
    python_executable: Path
    project_name: str
    mcp_name: str
    action: str = "install"

    @property
    def targets(self) -> tuple[Path, ...]:
        return (
            self.config_path,
            self.hooks_path,
            self.state_path,
            self.codex_gitignore_path,
            self.vault_gitignore_path,
        )

    def preview(self) -> str:
        verb = "configurer" if self.action == "install" else "retirer"
        lines = [
            f"Atlas Memory Loop va {verb} :",
            "",
            f"Vault       : {self.vault_path}",
            f"Projet Codex: {self.project_root}",
            "Hôte        : Codex",
            "Portée      : ce projet uniquement",
            f"MCP         : {self.mcp_name}",
            f"Hooks       : {', '.join(HOOK_EVENTS)}",
            f"Exécutable  : {self.python_executable} -m atlas_memory",
            f"Sauvegardes : {self.codex_dir / 'backups' / MANAGED_PREFIX}",
            "",
            "Les configurations existantes seront fusionnées, pas remplacées.",
        ]
        if self.action == "remove":
            lines[-1] = "Les autres configurations et les mémoires Markdown seront conservées."
        return "\n".join(lines)


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-") or "vault"


def build_codex_plan(
    *,
    vault: str | Path,
    project_root: str | Path | None = None,
    python_executable: str | Path | None = None,
    action: str = "install",
) -> CodexSetupPlan:
    vault_path = Path(vault).expanduser().resolve()
    if not vault_path.is_dir():
        raise ConfigurationError(f"Vault directory does not exist: {vault_path}")
    if not ((vault_path / ".obsidian").is_dir() or (vault_path / "00_System").is_dir()):
        raise ConfigurationError(
            f"Not a recognized vault: {vault_path}. Expected .obsidian/ or 00_System/."
        )

    root = Path(project_root or Path.cwd()).expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError(f"Codex project directory does not exist: {root}")

    # Do not resolve a virtualenv interpreter symlink: the symlink path selects
    # the environment in which atlas_memory is installed.
    python_path = Path(os.path.abspath(Path(python_executable or sys.executable).expanduser()))
    if not python_path.is_file():
        raise ConfigurationError(f"Python executable does not exist: {python_path}")

    codex_dir = root / ".codex"
    project_name = _safe_name(slugify(vault_path.name))
    return CodexSetupPlan(
        vault_path=vault_path,
        project_root=root,
        codex_dir=codex_dir,
        config_path=codex_dir / "config.toml",
        hooks_path=codex_dir / "hooks.json",
        state_path=codex_dir / STATE_FILENAME,
        codex_gitignore_path=codex_dir / ".gitignore",
        vault_gitignore_path=vault_path / ".gitignore",
        python_executable=python_path,
        project_name=project_name,
        mcp_name=f"atlas-memory-{project_name}",
        action=action,
    )


def _toml_string(value: str | Path) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _enable_hooks_feature(content: str) -> str:
    lines = content.splitlines()
    section_start: int | None = None
    section_end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[features]":
            section_start = index
            continue
        if section_start is not None and stripped.startswith("["):
            section_end = index
            break

    if section_start is None:
        base = content.rstrip()
        prefix = f"{base}\n\n" if base else ""
        return f"{prefix}[features]\nhooks = true\n"

    for index in range(section_start + 1, section_end):
        if re.match(r"^\s*hooks\s*=", lines[index]):
            indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
            lines[index] = f"{indent}hooks = true"
            return "\n".join(lines).rstrip() + "\n"

    lines.insert(section_end, "hooks = true")
    return "\n".join(lines).rstrip() + "\n"


def _managed_markers(mcp_name: str) -> tuple[str, str]:
    identifier = f"{MANAGED_PREFIX}:{mcp_name}"
    return f"# >>> {identifier}", f"# <<< {identifier}"


def _remove_managed_mcp_block(content: str, mcp_name: str) -> str:
    start, end = _managed_markers(mcp_name)
    pattern = re.compile(
        rf"^\s*{re.escape(start)}\s*$.*?^\s*{re.escape(end)}\s*$\n?",
        re.MULTILINE | re.DOTALL,
    )
    return pattern.sub("", content).rstrip() + ("\n" if content.strip() else "")


def merge_codex_config(content: str, plan: CodexSetupPlan) -> str:
    without_managed = _remove_managed_mcp_block(content, plan.mcp_name)
    table_pattern = re.compile(
        rf"^\s*\[mcp_servers\.{re.escape(plan.mcp_name)}\]\s*$", re.MULTILINE
    )
    if table_pattern.search(without_managed):
        raise SetupError(
            f"MCP server '{plan.mcp_name}' already exists outside the managed block. "
            "Rename or remove it before setup."
        )

    base = _enable_hooks_feature(without_managed).rstrip()
    start, end = _managed_markers(plan.mcp_name)
    block = "\n".join(
        [
            start,
            f"[mcp_servers.{plan.mcp_name}]",
            f"command = {_toml_string(plan.python_executable)}",
            'args = ["-m", "atlas_memory", "mcp"]',
            "",
            f"[mcp_servers.{plan.mcp_name}.env]",
            f"ATLAS_MEMORY_VAULT = {_toml_string(plan.vault_path)}",
            end,
        ]
    )
    return f"{base}\n\n{block}\n"


def remove_codex_config(content: str, mcp_name: str) -> str:
    return _remove_managed_mcp_block(content, mcp_name)


def _shell_command(arguments: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)


def _hook_command(plan: CodexSetupPlan, event: str) -> str:
    arguments = [
        str(plan.python_executable),
        "-m",
        "atlas_memory",
        "--vault",
        str(plan.vault_path),
        "hook",
        "--host",
        "codex",
        "--event",
        event,
        "--project",
        plan.project_name,
    ]
    if event == "SessionStart":
        arguments.extend(["--inject", "--structured-output"])
    return _shell_command(arguments)


def _is_managed_hook(group: Any) -> bool:
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks", [])
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command", ""))
        if "atlas_memory" in command and "--host codex" in command:
            return True
    return False


def _hook_group(plan: CodexSetupPlan, event: str) -> dict[str, Any]:
    hook: dict[str, Any] = {
        "type": "command",
        "command": _hook_command(plan, event),
        "timeout": 10 if event == "SessionStart" else 3 if event == "SessionEnd" else 5,
    }
    if event == "SessionStart":
        hook["statusMessage"] = "Loading Atlas memory"
    return {"hooks": [hook]}


def merge_codex_hooks(content: str, plan: CodexSetupPlan) -> str:
    if content.strip():
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SetupError(f"Invalid existing hooks JSON: {exc}") from exc
    else:
        data = {}
    if not isinstance(data, dict):
        raise SetupError("Existing hooks configuration must be a JSON object")

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SetupError("Existing 'hooks' value must be a JSON object")
    data.setdefault("description", "Project hooks including Atlas Memory Loop.")

    for event in HOOK_EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise SetupError(f"Existing hook event '{event}' must contain a JSON array")
        hooks[event] = [group for group in groups if not _is_managed_hook(group)]
        hooks[event].append(_hook_group(plan, event))

    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def remove_codex_hooks(content: str) -> str:
    if not content.strip():
        return ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SetupError(f"Invalid existing hooks JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise SetupError("Existing hooks configuration has an unsupported structure")

    hooks = data.get("hooks", {})
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        retained = [group for group in groups if not _is_managed_hook(group)]
        if retained:
            hooks[event] = retained
        else:
            del hooks[event]
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _ensure_ignore_entry(content: str, entry: str) -> str:
    lines = content.splitlines()
    if entry not in {line.strip() for line in lines}:
        lines.append(entry)
    return "\n".join(lines).strip() + "\n"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _backup_targets(plan: CodexSetupPlan) -> tuple[Path, list[dict[str, Any]]]:
    suffix = f"{isoformat().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
    backup_dir = plan.codex_dir / "backups" / MANAGED_PREFIX / suffix
    backup_dir.mkdir(parents=True, exist_ok=False)
    if os.name != "nt":
        backup_dir.chmod(0o700)
    manifest: list[dict[str, Any]] = []
    for index, target in enumerate(plan.targets):
        entry: dict[str, Any] = {"path": str(target), "existed": target.exists()}
        if target.exists():
            backup_name = f"{index}-{target.name}"
            backup_path = backup_dir / backup_name
            shutil.copy2(target, backup_path)
            entry["backup"] = backup_name
        manifest.append(entry)
    atomic_write_json(backup_dir / "manifest.json", {"files": manifest})
    return backup_dir, manifest


def _rollback(backup_dir: Path, manifest: list[dict[str, Any]]) -> None:
    for entry in manifest:
        target = Path(entry["path"])
        if entry["existed"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_dir / entry["backup"], target)
        else:
            target.unlink(missing_ok=True)


def apply_codex_setup(plan: CodexSetupPlan) -> dict[str, Any]:
    plan.codex_dir.mkdir(parents=True, exist_ok=True)
    config = merge_codex_config(_read(plan.config_path), plan)
    hooks = merge_codex_hooks(_read(plan.hooks_path), plan)
    codex_ignore = _ensure_ignore_entry(_read(plan.codex_gitignore_path), "backups/")
    codex_ignore = _ensure_ignore_entry(codex_ignore, STATE_FILENAME)
    vault_ignore = _ensure_ignore_entry(_read(plan.vault_gitignore_path), ".atlas-runtime/")

    backup_dir, manifest = _backup_targets(plan)
    try:
        atomic_write_text(plan.config_path, config)
        atomic_write_text(plan.hooks_path, hooks)
        atomic_write_text(plan.codex_gitignore_path, codex_ignore)
        atomic_write_text(plan.vault_gitignore_path, vault_ignore)

        settings = Settings.resolve(vault=plan.vault_path)
        health = MemoryEngine(settings).initialize()
        state = {
            "schema_version": 1,
            "host": "codex",
            "installed_at": isoformat(),
            "vault": str(plan.vault_path),
            "project_root": str(plan.project_root),
            "python_executable": str(plan.python_executable),
            "mcp_name": plan.mcp_name,
            "managed_hook_events": list(HOOK_EVENTS),
            "last_backup": str(backup_dir),
        }
        atomic_write_json(plan.state_path, state)

        json.loads(plan.hooks_path.read_text(encoding="utf-8"))
        if _managed_markers(plan.mcp_name)[0] not in plan.config_path.read_text(encoding="utf-8"):
            raise SetupError("Managed MCP block was not written")
    except Exception:
        _rollback(backup_dir, manifest)
        raise

    return {
        "status": "configured",
        "host": "codex",
        "vault": str(plan.vault_path),
        "project_root": str(plan.project_root),
        "mcp_name": plan.mcp_name,
        "config": str(plan.config_path),
        "hooks": str(plan.hooks_path),
        "backup": str(backup_dir),
        "runtime": health["runtime"],
        "restart_required": True,
    }


def _load_setup_state(project_root: Path) -> dict[str, Any]:
    state_path = project_root / ".codex" / STATE_FILENAME
    if not state_path.exists():
        raise SetupError(f"No Atlas Memory Loop setup state found at {state_path}")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SetupError(f"Invalid setup state: {exc}") from exc
    if not isinstance(state, dict) or state.get("host") != "codex":
        raise SetupError("Unsupported Atlas Memory Loop setup state")
    return state


def build_codex_remove_plan(project_root: str | Path | None = None) -> CodexSetupPlan:
    root = Path(project_root or Path.cwd()).expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError(f"Codex project directory does not exist: {root}")
    state = _load_setup_state(root)
    required = {"vault", "python_executable", "mcp_name"}
    missing = sorted(required - state.keys())
    if missing:
        raise SetupError(f"Setup state is missing: {', '.join(missing)}")
    vault_path = Path(state["vault"]).expanduser().resolve()
    codex_dir = root / ".codex"
    project_name = _safe_name(slugify(vault_path.name))
    return CodexSetupPlan(
        vault_path=vault_path,
        project_root=root,
        codex_dir=codex_dir,
        config_path=codex_dir / "config.toml",
        hooks_path=codex_dir / "hooks.json",
        state_path=codex_dir / STATE_FILENAME,
        codex_gitignore_path=codex_dir / ".gitignore",
        vault_gitignore_path=vault_path / ".gitignore",
        python_executable=Path(state["python_executable"]),
        project_name=project_name,
        mcp_name=str(state["mcp_name"]),
        action="remove",
    )


def apply_codex_remove(plan: CodexSetupPlan) -> dict[str, Any]:
    config = remove_codex_config(_read(plan.config_path), plan.mcp_name)
    hooks = remove_codex_hooks(_read(plan.hooks_path))
    backup_dir, manifest = _backup_targets(plan)
    try:
        atomic_write_text(plan.config_path, config)
        atomic_write_text(plan.hooks_path, hooks)
        plan.state_path.unlink(missing_ok=True)
    except Exception:
        _rollback(backup_dir, manifest)
        raise
    return {
        "status": "removed",
        "host": "codex",
        "vault": str(plan.vault_path),
        "project_root": str(plan.project_root),
        "backup": str(backup_dir),
        "durable_memory_preserved": True,
        "restart_required": True,
    }


def require_codex_cli() -> str:
    executable = shutil.which("codex")
    if not executable:
        raise SetupError("Codex CLI was not found in PATH")
    return executable
