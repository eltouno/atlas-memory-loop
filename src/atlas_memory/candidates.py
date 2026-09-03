from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import MemoryCandidate, MemoryEvent
from .redact import redact_text

MAX_CANDIDATES_PER_SESSION = 5

_DISSATISFACTION_PATTERNS = (
    r"\bce n est pas (?:bon|ce que je voulais|satisfaisant)\b",
    r"\bvilaine? mise en page\b",
    r"\btu t es trompe\b",
    r"\bca ne va pas\b",
    r"\bpas satisfaisant\b",
    r"\bje ne suis pas satisfait",
    r"\bthat s not (?:right|what i wanted|good enough)\b",
    r"\byou got (?:it|this) wrong\b",
)

_PROCESS_CORRECTION_PATTERNS = (
    r"\btu etais suppose",
    r"\btu etais cense",
    r"\bil fallait\b",
    r"\bj attendais (?:que|de)\b",
    r"\bje t avais demande (?:de|que)\b",
    r"\bla prochaine fois\b",
    r"\btu aurais du\b",
    r"\btu devais\b",
    r"\byou were supposed to\b",
    r"\bnext time\b",
    r"\bi expected (?:you )?to\b",
)

_ACTION_PATTERNS = (
    r"\bconserv",
    r"\bpreserv",
    r"\brespect",
    r"\brestaur",
    r"\brepr(?:ends?|endre)",
    r"\bgard",
    r"\bmaint(?:iens?|enir)",
    r"\badapt",
    r"\bappliqu",
    r"\bsuiv",
    r"\bprends?\b",
    r"\bpartir\b",
    r"\butilis",
    r"\bverifi",
    r"\bvalid",
    r"\bdemand",
    r"\bne (?:change|modifie|supprime|refais) pas\b",
    r"\bkeep\b",
    r"\bpreserve\b",
    r"\brestore\b",
    r"\bverify\b",
)

_REPEATABLE_DOMAIN_PATTERNS = (
    r"\blivrable",
    r"\bmise en page\b",
    r"\bcharte(?: graphique)?\b",
    r"\bgrille\b",
    r"\bhierarch",
    r"\bcouleur",
    r"\bpolice",
    r"\btypograph",
    r"\btableur",
    r"\bexcel\b",
    r"\bpresentation",
    r"\bpdf\b",
    r"\bguide\b",
    r"\bsupport\b",
    r"\bformat\b",
    r"\bgabarit\b",
    r"\btemplate\b",
    r"\bmethode\b",
    r"\bprocess",
    r"\bworkflow\b",
    r"\boutil",
    r"\bsource de verite\b",
    r"\bverification\b",
    r"\bvalidation\b",
    r"\bfichier\b",
    r"\bprojet\b",
)

_ASSISTANT_ACKNOWLEDGEMENT_PATTERNS = (
    r"\btu avais raison\b",
    r"\bvous aviez raison\b",
    r"\bj ai corrige(?: le tir| mon erreur)?\b",
    r"\bj ai restaure\b",
    r"\bc etait une erreur\b",
    r"\bmon erreur\b",
    r"\bje n aurais pas du\b",
    r"\byou were right\b",
    r"\bi corrected\b",
    r"\bi restored\b",
    r"\bmy mistake\b",
)

_VISUAL_DOMAIN_PATTERNS = (
    r"\bmise en page\b",
    r"\bcharte(?: graphique)?\b",
    r"\bgrille\b",
    r"\bhierarch",
    r"\bcouleur",
    r"\bpolice",
    r"\btypograph",
)

_VISUAL_PRESERVATION_PATTERNS = (
    r"\bconserv",
    r"\bpreserv",
    r"\brestaur",
    r"\brepr(?:ends?|endre)",
    r"\bmaint(?:iens?|enir)",
    r"\bne (?:change|refais) pas\b",
)


@dataclass(slots=True)
class _Turn:
    prompt: str
    response: str = ""


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", without_accents)).strip().lower()


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def _session_turns(events: list[MemoryEvent]) -> list[_Turn]:
    turns: list[_Turn] = []
    for event in events:
        if event.event_type == "turn.input":
            prompt = event.payload.get("prompt")
            if isinstance(prompt, str) and prompt.strip():
                turns.append(_Turn(prompt=prompt.strip()))
        elif event.event_type == "turn.checkpoint" and turns:
            response = event.payload.get("last_assistant_message")
            if isinstance(response, str) and response.strip():
                for turn in reversed(turns):
                    if not turn.response:
                        turn.response = response.strip()
                        break
    return turns


def _extract_brand(prompt: str) -> str | None:
    match = re.search(
        r"charte\s+graphique\s+(?:de\s+|du\s+|des\s+)?([^\n,.!?;:…]{2,60})",
        prompt,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    brand = " ".join(match.group(1).strip(" '\"“”").split())
    if not brand or len(brand.split()) > 5:
        return None
    return brand.title() if brand.islower() else brand


def _visual_preservation_memory(prompt: str, normalized_prompt: str) -> str | None:
    if not _matches_any(normalized_prompt, _VISUAL_DOMAIN_PATTERNS):
        return None
    if not _matches_any(normalized_prompt, _VISUAL_PRESERVATION_PATTERNS):
        return None
    brand = _extract_brand(prompt)
    scope = f" {brand}" if brand else ""
    return (
        f"Pour les livrables{scope} existants, surtout les tableurs, présentations, PDF, "
        "pages d'accueil, guides et supports déjà mis en forme, Codex doit préserver la "
        "structure visuelle, la grille, la hiérarchie, les couleurs, les polices et le "
        "principe graphique existants sauf demande explicite de refonte. Une demande de "
        "contenu plus ludique, visuel, clair ou agréable ne suffit pas à autoriser une "
        "refonte graphique."
    )


def _extract_directive(prompt: str) -> str | None:
    sentences = [
        sentence.strip(" -\t•")
        for sentence in re.split(r"(?<=[.!?…])\s+|\n+", prompt)
        if sentence.strip(" -\t•")
    ]
    selected: list[str] = []
    for sentence in sentences:
        normalized = _normalize(sentence)
        has_action = _matches_any(normalized, _ACTION_PATTERNS)
        has_scope = _matches_any(normalized, _REPEATABLE_DOMAIN_PATTERNS)
        has_process = _matches_any(normalized, _PROCESS_CORRECTION_PATTERNS)
        if has_action and (has_scope or has_process):
            selected.append(sentence)
        if len(selected) == 2:
            break
    if not selected:
        return None
    directive = " ".join(selected)
    if len(directive) > 600:
        directive = directive[:599].rstrip() + "…"
    return f"Instruction durable pour les tâches similaires : {directive}"


def _candidate_type(normalized_prompt: str) -> str:
    if re.search(r"\b(?:outil|source de verite|verification|validation)\b", normalized_prompt):
        return "tooling_rule"
    if _matches_any(normalized_prompt, _VISUAL_DOMAIN_PATTERNS) or re.search(
        r"\b(?:livrable|format|gabarit|template|pdf|tableur|presentation|guide)\b",
        normalized_prompt,
    ):
        return "delivery_standard"
    if re.search(r"\b(?:jamais|erreur a eviter|ne .* pas)\b", normalized_prompt):
        return "error_to_avoid"
    if re.search(r"\b(?:methode|projet|workflow)\b", normalized_prompt):
        return "project_method"
    if re.search(r"\b(?:je prefere|ma preference|i prefer)\b", normalized_prompt):
        return "user_preference"
    if re.search(r"\b(?:la prochaine fois|next time)\b", normalized_prompt):
        return "working_rule"
    return "process_feedback"


def _signal_description(
    *,
    dissatisfaction: bool,
    process_correction: bool,
    assistant_acknowledgement: bool,
    visual_preservation: bool,
) -> str:
    parts: list[str] = []
    if dissatisfaction:
        parts.append("insatisfaction utilisateur explicite")
    if process_correction:
        parts.append("correction explicite du processus attendu")
    if visual_preservation:
        parts.append("règle réutilisable de préservation d’une mise en forme existante")
    else:
        parts.append("attendu réutilisable pour des tâches similaires")
    signal = ", ".join(parts).capitalize() + "."
    if assistant_acknowledgement:
        signal += " L’assistant reconnaît ensuite l’erreur ou indique l’avoir corrigée."
    return signal


def extract_memory_candidates(
    events: list[MemoryEvent],
    *,
    source_session: str,
) -> list[MemoryCandidate]:
    """Extract reviewable durable-memory proposals using deterministic strong-signal rules."""

    candidates: list[MemoryCandidate] = []
    seen_memories: set[str] = set()
    for turn in _session_turns(events):
        normalized_prompt = _normalize(turn.prompt)
        normalized_response = _normalize(turn.response)
        dissatisfaction = _matches_any(normalized_prompt, _DISSATISFACTION_PATTERNS)
        process_correction = _matches_any(normalized_prompt, _PROCESS_CORRECTION_PATTERNS)
        actionable = _matches_any(normalized_prompt, _ACTION_PATTERNS)
        repeatable = _matches_any(normalized_prompt, _REPEATABLE_DOMAIN_PATTERNS)
        assistant_acknowledgement = _matches_any(
            normalized_response, _ASSISTANT_ACKNOWLEDGEMENT_PATTERNS
        )

        # A vague complaint or a one-off preference is intentionally insufficient.
        if not repeatable or not actionable:
            continue
        if not process_correction and not dissatisfaction:
            continue

        proposed_memory = _visual_preservation_memory(turn.prompt, normalized_prompt)
        visual_preservation = proposed_memory is not None
        proposed_memory = proposed_memory or _extract_directive(turn.prompt)
        if not proposed_memory:
            continue

        # Runtime capture already redacts secrets. This second check prevents a caller that
        # bypasses RuntimeStore from turning a known secret shape into durable Markdown.
        redacted_memory = redact_text(proposed_memory, 1_200)
        if redacted_memory != proposed_memory or "[REDACTED]" in proposed_memory:
            continue
        memory_key = _normalize(proposed_memory)
        if memory_key in seen_memories:
            continue
        seen_memories.add(memory_key)
        candidates.append(
            MemoryCandidate(
                source_session=source_session,
                signal=_signal_description(
                    dissatisfaction=dissatisfaction,
                    process_correction=process_correction,
                    assistant_acknowledgement=assistant_acknowledgement,
                    visual_preservation=visual_preservation,
                ),
                proposed_memory=proposed_memory,
                candidate_type=_candidate_type(normalized_prompt),
            )
        )
        if len(candidates) >= MAX_CANDIDATES_PER_SESSION:
            break
    return candidates
