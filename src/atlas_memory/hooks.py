from __future__ import annotations

from pathlib import Path
from typing import Any

HOOK_EVENT_MAP = {
    "sessionstart": "session.open",
    "userpromptsubmit": "turn.input",
    "pretooluse": "tool.before",
    "posttooluse": "tool.completed",
    "posttoolusefailure": "tool.failed",
    "stop": "turn.checkpoint",
    "sessionend": "session.finalize",
    "precompact": "context.refresh",
    "postcompact": "context.refreshed",
}


def normalize_hook_name(value: str) -> str:
    compact = "".join(char for char in value if char.isalnum()).lower()
    return HOOK_EVENT_MAP.get(compact, value.strip().lower().replace("_", "."))


def extract_host_session_id(payload: dict[str, Any]) -> str:
    for key in ("session_id", "sessionId", "thread_id", "threadId", "conversation_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("Hook payload has no session identifier")


def extract_project(payload: dict[str, Any], explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    value = payload.get("project")
    if isinstance(value, str) and value.strip():
        return value.strip()
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return Path(cwd).resolve().name
    return "global"


def normalized_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    common: dict[str, Any] = {}
    for key in ("source", "reason", "model", "permission_mode", "agent_id", "agent_type"):
        if key in payload:
            common[key] = payload[key]

    if event_type == "turn.input":
        common["prompt"] = payload.get("prompt", payload.get("userPrompt", ""))
    elif event_type.startswith("tool."):
        common.update(
            {
                "tool_name": payload.get("tool_name", payload.get("toolName", "unknown")),
                "tool_input": payload.get("tool_input", payload.get("toolArgs", {})),
                "tool_output": payload.get(
                    "tool_response",
                    payload.get(
                        "tool_output", payload.get("tool_result", payload.get("toolResult"))
                    ),
                ),
            }
        )
    elif event_type.startswith("context."):
        common["trigger"] = payload.get("trigger", payload.get("source", "unknown"))

    return common
