from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import Settings
from .engine import MemoryEngine
from .runtime import build_session_id

logger = logging.getLogger(__name__)


def create_server(settings: Settings | None = None) -> Any:
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised only in minimal installs
        raise RuntimeError("MCP support requires the 'mcp>=2,<3' package") from exc

    resolved = settings or Settings.resolve()
    engine = MemoryEngine(resolved)
    engine.initialize()
    mcp = MCPServer(
        "Atlas Memory Loop",
        version="0.1.0",
        instructions=(
            "Use atlas_recall before work that may depend on prior project context. "
            "Use atlas_remember for explicit durable candidates; it never mutates "
            "canonical knowledge directly."
        ),
    )

    @mcp.tool()
    def atlas_recall(
        query: str,
        project: str = "",
        limit: int = 8,
        token_budget: int = 2_000,
    ) -> dict[str, Any]:
        """Recall bounded Markdown context relevant to a query."""

        context, results = engine.recall(
            query,
            project=project or None,
            limit=limit,
            token_budget=token_budget,
        )
        return {"context": context, "results": [result.to_dict() for result in results]}

    @mcp.tool()
    def atlas_remember(
        content: str,
        kind: str = "observation",
        project: str = "global",
        source_session_id: str = "",
    ) -> dict[str, str]:
        """Create a reviewable Markdown memory candidate."""

        path = engine.remember(
            content=content,
            kind=kind,
            project=project,
            source_session_id=source_session_id or None,
        )
        return {"status": "pending_review", "path": str(path)}

    @mcp.tool()
    def atlas_session_start(
        host: str,
        host_session_id: str,
        project: str,
        cwd: str = "",
    ) -> dict[str, Any]:
        """Open or resume an Atlas memory session."""

        event, duplicate = engine.record(
            event_type="session.open",
            host=host,
            host_session_id=host_session_id,
            project=project,
            cwd=cwd or str(Path.cwd()),
        )
        return {
            "session_id": event.atlas_session_id,
            "duplicate": duplicate,
        }

    @mcp.tool()
    def atlas_session_checkpoint(
        host: str,
        host_session_id: str,
        project: str,
        cwd: str = "",
    ) -> dict[str, Any]:
        """Save a turn checkpoint without finalizing the session."""

        event, duplicate = engine.record(
            event_type="turn.checkpoint",
            host=host,
            host_session_id=host_session_id,
            project=project,
            cwd=cwd or str(Path.cwd()),
        )
        return {"session_id": event.atlas_session_id, "duplicate": duplicate}

    @mcp.tool()
    def atlas_session_finalize(host: str, host_session_id: str) -> dict[str, str]:
        """Finalize and deterministically distill one session to Markdown."""

        session_id = build_session_id(host, host_session_id)
        path = engine.finalize(session_id)
        return {"session_id": session_id, "status": "distilled", "path": str(path)}

    @mcp.tool()
    def atlas_health() -> dict[str, Any]:
        """Return storage, index, and session health."""

        return engine.health()

    @mcp.resource("atlas://status")
    def atlas_status() -> str:
        """Machine-readable Atlas Memory Loop status."""

        return json.dumps(engine.health(), ensure_ascii=False, indent=2)

    return mcp


def run_server(settings: Settings | None = None) -> None:
    server = create_server(settings)
    server.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_server()
