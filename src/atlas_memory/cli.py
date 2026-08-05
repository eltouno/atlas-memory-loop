from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import ConfigurationError, Settings
from .engine import MemoryEngine
from .hooks import extract_project, normalize_hook_name
from .mcp_server import run_server
from .runtime import build_session_id
from .setup import (
    SetupError,
    apply_codex_remove,
    apply_codex_setup,
    build_codex_plan,
    build_codex_remove_plan,
    require_codex_cli,
)

logger = logging.getLogger("atlas_memory")


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.resolve(vault=args.vault, runtime=args.runtime)


def _read_stdin_json() -> dict[str, Any]:
    content = sys.stdin.read()
    if not content.strip():
        raise ValueError("Expected a JSON hook payload on stdin")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Hook payload must be a JSON object")
    return value


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas-memory",
        description="Markdown-first persistent memory loop for agentic AI hosts.",
    )
    parser.add_argument("--vault", help="Path to the canonical Markdown vault")
    parser.add_argument("--runtime", help="Path to temporary runtime state")
    parser.add_argument(
        "--log-level",
        default=os.environ.get("ATLAS_MEMORY_LOG_LEVEL", "WARNING"),
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create runtime and canonical memory directories")

    hook = subparsers.add_parser("hook", help="Capture one native host hook from stdin")
    hook.add_argument("--host", required=True)
    hook.add_argument("--event", help="Native hook name; defaults to hook_event_name from stdin")
    hook.add_argument("--project")
    hook.add_argument(
        "--inject", action="store_true", help="Print bounded recall context to stdout"
    )
    hook.add_argument(
        "--structured-output",
        action="store_true",
        help="Wrap injected context in the hook JSON format used by Codex and Claude",
    )
    hook.add_argument("--strict", action="store_true", help="Return non-zero on capture failure")

    session = subparsers.add_parser("session", help="Manage an explicit session lifecycle")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    for name in ("start", "checkpoint"):
        command = session_sub.add_parser(name)
        command.add_argument("--host", required=True)
        command.add_argument("--session-id", required=True)
        command.add_argument("--project", required=True)
        command.add_argument("--cwd", default=str(Path.cwd()))
    finalize = session_sub.add_parser("finalize")
    finalize.add_argument("--host", required=True)
    finalize.add_argument("--session-id", required=True)

    recall = subparsers.add_parser("recall", help="Search Markdown and emit bounded context")
    recall.add_argument("query")
    recall.add_argument("--project")
    recall.add_argument("--limit", type=int, default=8)
    recall.add_argument("--token-budget", type=int)
    recall.add_argument("--json", action="store_true")

    remember = subparsers.add_parser("remember", help="Create a reviewable memory candidate")
    remember.add_argument("content")
    remember.add_argument("--kind", default="observation")
    remember.add_argument("--project", default="global")
    remember.add_argument("--source-session-id")

    subparsers.add_parser("index", help="Synchronize the derived SQLite index")

    recover = subparsers.add_parser("recover", help="Finalize stale interrupted sessions")
    recover.add_argument("--idle-minutes", type=int, default=120)

    cleanup = subparsers.add_parser("cleanup", help="Purge expired distilled runtime journals")
    cleanup.add_argument("--apply", action="store_true", help="Actually delete; default is dry-run")

    subparsers.add_parser("doctor", help="Inspect vault, runtime, index, and sessions")
    subparsers.add_parser("mcp", help="Run the local MCP stdio server")

    setup = subparsers.add_parser("setup", help="Safely configure a supported AI host")
    setup_sub = setup.add_subparsers(dest="setup_command", required=True)
    setup_codex = setup_sub.add_parser("codex", help="Configure Codex for one project")
    setup_codex.add_argument("--vault", default=argparse.SUPPRESS)
    setup_codex.add_argument("--project-root", default=str(Path.cwd()))
    setup_codex.add_argument("--yes", action="store_true", help="Apply the displayed plan")
    setup_codex.add_argument(
        "--dry-run", action="store_true", help="Display without changing files"
    )
    setup_remove = setup_sub.add_parser("remove", help="Remove managed host configuration")
    setup_remove.add_argument("host", choices=("codex",))
    setup_remove.add_argument("--project-root", default=str(Path.cwd()))
    setup_remove.add_argument("--yes", action="store_true", help="Apply the displayed plan")
    setup_remove.add_argument(
        "--dry-run", action="store_true", help="Display without changing files"
    )
    return parser


def _confirm_setup(args: argparse.Namespace, preview: str) -> bool:
    print(preview)
    if args.dry_run:
        return False
    if args.yes:
        return True
    if not sys.stdin.isatty():
        raise SetupError("Interactive confirmation unavailable; review the plan and pass --yes")
    return input("\nContinuer ? [o/N] ").strip().lower() in {"o", "oui", "y", "yes"}


def _handle_setup(args: argparse.Namespace) -> int:
    require_codex_cli()
    if args.setup_command == "codex":
        if not getattr(args, "vault", None):
            raise ConfigurationError("setup codex requires --vault")
        plan = build_codex_plan(vault=args.vault, project_root=args.project_root)
        if not _confirm_setup(args, plan.preview()):
            _json({"status": "planned" if args.dry_run else "cancelled"})
            return 0
        _json(apply_codex_setup(plan))
        return 0
    if args.setup_command == "remove" and args.host == "codex":
        plan = build_codex_remove_plan(args.project_root)
        if not _confirm_setup(args, plan.preview()):
            _json({"status": "planned" if args.dry_run else "cancelled"})
            return 0
        _json(apply_codex_remove(plan))
        return 0
    raise SetupError("Unsupported setup operation")


def _handle_hook(args: argparse.Namespace, engine: MemoryEngine) -> int:
    try:
        payload = _read_stdin_json()
        native_name = args.event or str(
            payload.get("hook_event_name", payload.get("hookEventName", "observation"))
        )
        event, duplicate = engine.capture_hook(
            host=args.host,
            raw_payload=payload,
            hook_name=native_name,
            project=args.project,
        )
        event_type = normalize_hook_name(native_name)
        if event_type == "session.finalize":
            engine.finalize(event.atlas_session_id)
        if args.inject or event_type in {"context.refresh"}:
            project = extract_project(payload, args.project)
            prompt = str(payload.get("prompt", payload.get("userPrompt", project)))
            context, _ = engine.recall(prompt, project=project)
            if context:
                if args.structured_output:
                    _json(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": native_name,
                                "additionalContext": context,
                            }
                        }
                    )
                else:
                    sys.stdout.write(context)
        logger.info(
            "captured event=%s session=%s duplicate=%s",
            event.event_type,
            event.atlas_session_id,
            duplicate,
        )
        return 0
    except Exception as exc:  # hooks fail open by design
        print(f"atlas-memory hook warning: {exc}", file=sys.stderr)
        return 1 if args.strict else 0


def run(args: argparse.Namespace) -> int:
    if args.command == "setup":
        return _handle_setup(args)

    settings = _settings(args)
    engine = MemoryEngine(settings)

    if args.command == "mcp":
        run_server(settings)
        return 0
    if args.command == "init":
        _json(engine.initialize())
        return 0

    engine.initialize()

    if args.command == "hook":
        return _handle_hook(args, engine)
    if args.command == "session":
        if args.session_command == "finalize":
            session_id = build_session_id(args.host, args.session_id)
            path = engine.finalize(session_id)
            _json({"session_id": session_id, "status": "distilled", "path": str(path)})
            return 0
        event_type = "session.open" if args.session_command == "start" else "turn.checkpoint"
        event, duplicate = engine.record(
            event_type=event_type,
            host=args.host,
            host_session_id=args.session_id,
            project=args.project,
            cwd=args.cwd,
        )
        _json({"session_id": event.atlas_session_id, "duplicate": duplicate})
        return 0
    if args.command == "recall":
        context, results = engine.recall(
            args.query,
            project=args.project,
            limit=args.limit,
            token_budget=args.token_budget,
        )
        if args.json:
            _json({"context": context, "results": [result.to_dict() for result in results]})
        elif context:
            print(context)
        return 0
    if args.command == "remember":
        path = engine.remember(
            content=args.content,
            kind=args.kind,
            project=args.project,
            source_session_id=args.source_session_id,
        )
        _json({"status": "pending_review", "path": str(path)})
        return 0
    if args.command == "index":
        _json(engine.index.sync())
        return 0
    if args.command == "recover":
        paths = engine.recover_stale(args.idle_minutes)
        _json({"recovered": [str(path) for path in paths]})
        return 0
    if args.command == "cleanup":
        session_ids = engine.cleanup(dry_run=not args.apply)
        _json({"dry_run": not args.apply, "sessions": session_ids})
        return 0
    if args.command == "doctor":
        _json(engine.health())
        return 0
    raise ValueError(f"Unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        raise SystemExit(run(args))
    except (ConfigurationError, SetupError, ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"atlas-memory: {exc}\n")


if __name__ == "__main__":
    main()
