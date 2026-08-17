from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from typing import Any

from .candidates import extract_memory_candidates
from .models import MemoryCandidate, MemoryEvent, SessionState


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _walk_strings(value: Any, keys: set[str] | None = None) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if (keys is None or key in keys) and isinstance(item, str):
                yield item
            yield from _walk_strings(item, keys)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item, keys)


def _compact(value: Any, limit: int = 180) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_session_markdown(
    state: SessionState,
    events: list[MemoryEvent],
    *,
    note_status: str = "distilled",
    candidates: list[MemoryCandidate] | None = None,
) -> str:
    if note_status not in {"checkpointed", "distilled"}:
        raise ValueError(f"Unsupported session note status: {note_status}")
    prompts = [
        _compact(event.payload.get("prompt"), 300)
        for event in events
        if event.event_type == "turn.input" and event.payload.get("prompt")
    ]
    responses = [
        _compact(event.payload.get("last_assistant_message"), 600)
        for event in events
        if event.event_type == "turn.checkpoint" and event.payload.get("last_assistant_message")
    ]
    tools = [
        str(event.payload.get("tool_name", "unknown"))
        for event in events
        if event.event_type in {"tool.before", "tool.completed", "tool.failed"}
    ]
    failures = [event for event in events if event.event_type == "tool.failed"]
    completed = [event for event in events if event.event_type == "tool.completed"]
    file_keys = {"file", "file_path", "path"}
    files = sorted(
        {
            item
            for event in events
            for item in _walk_strings(event.payload, file_keys)
            if item and not item.startswith("[")
        }
    )
    tool_counts = Counter(tools)
    started_date = state.started_at[:10]
    title_subject = prompts[0] if prompts else f"Session {state.session_id}"
    title = _compact(title_subject, 80)
    candidates = (
        extract_memory_candidates(events, source_session=state.session_id)
        if candidates is None
        else candidates
    )

    lifecycle_timestamp = (
        f"finalized_at: {_yaml_string(state.finalized_at or state.updated_at)}"
        if note_status == "distilled"
        else f"updated_at: {_yaml_string(state.updated_at)}"
    )
    lines = [
        "---",
        f"id: {_yaml_string('session.' + state.session_id)}",
        "type: agent_session",
        f"status: {note_status}",
        f"project: {_yaml_string(state.project)}",
        f"host: {_yaml_string(state.host)}",
        f"host_session_id: {_yaml_string(state.host_session_id)}",
        f"started_at: {_yaml_string(state.started_at)}",
        lifecycle_timestamp,
        "source_of_truth: false",
        "---",
        "",
        f"# Session — {title}",
        "",
        "## Objectif",
        "",
        prompts[0] if prompts else "Objectif non déterminé automatiquement.",
        "",
        "## Résultat observable",
        "",
        f"- {len(completed)} utilisations d’outil terminées.",
        f"- {len(failures)} échecs d’outil capturés.",
        f"- {len(events)} événements enregistrés.",
    ]

    if responses:
        lines.extend(["", "## Réponses de l’agent", ""])
        lines.extend(f"- {response}" for response in responses[-20:])

    if tool_counts:
        lines.extend(["", "## Outils utilisés", ""])
        lines.extend(f"- `{name}` : {count}" for name, count in tool_counts.most_common())
    if files:
        lines.extend(["", "## Fichiers observés", ""])
        lines.extend(f"- `{path}`" for path in files[:50])
    if failures:
        lines.extend(["", "## Erreurs observées", ""])
        for event in failures[:20]:
            output = _compact(event.payload.get("tool_output"), 300) or "Erreur sans détail."
            lines.append(f"- `{event.payload.get('tool_name', 'unknown')}` — {output}")
    if len(prompts) > 1:
        lines.extend(["", "## Demandes complémentaires", ""])
        lines.extend(f"- {prompt}" for prompt in prompts[1:20])

    lines.extend(["", "## Candidats à la mémoire durable", ""])
    if candidates:
        for candidate in candidates:
            lines.extend(
                [
                    f"### {candidate.candidate_type}",
                    "",
                    f"- **Signal observé** : {candidate.signal}",
                    f"- **Mémoire proposée** : {candidate.proposed_memory}",
                    "- **Statut** : `pending` — revue humaine requise.",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "Aucun signal assez fort pour proposer automatiquement une mémoire durable.",
                "",
            ]
        )
    lines.extend(
        [
            "## Provenance",
            "",
            f"- Session Memory Loop : `{state.session_id}`",
            f"- Journal brut : `.atlas-runtime/sessions/{state.session_id}/events.jsonl`",
            f"- Date : `{started_date}`",
            "",
        ]
    )
    return "\n".join(lines)
