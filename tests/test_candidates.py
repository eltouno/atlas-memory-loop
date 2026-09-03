from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import make_settings

from atlas_memory.candidates import extract_memory_candidates
from atlas_memory.engine import MemoryEngine
from atlas_memory.models import MemoryEvent
from atlas_memory.runtime import build_session_id

EXPECTED_VINGT_MARS_MEMORY = (
    "Pour les livrables Vingt Mars existants, surtout les tableurs, présentations, PDF, "
    "pages d'accueil, guides et supports déjà mis en forme, Codex doit préserver la "
    "structure visuelle, la grille, la hiérarchie, les couleurs, les polices et le "
    "principe graphique existants sauf demande explicite de refonte. Une demande de "
    "contenu plus ludique, visuel, clair ou agréable ne suffit pas à autoriser une "
    "refonte graphique."
)


def make_event(event_type: str, payload: dict[str, str]) -> MemoryEvent:
    return MemoryEvent(
        schema_version=1,
        event_id=f"event-{event_type}",
        event_type=event_type,
        timestamp="2026-08-14T12:00:00Z",
        host="codex",
        host_session_id="example",
        atlas_session_id="codex-3c00e8d6f2e34fb3",
        project="vingt-mars",
        cwd="/tmp/project",
        payload=payload,
    )


def example_events() -> list[MemoryEvent]:
    return [
        make_event(
            "turn.input",
            {
                "prompt": (
                    "Oulala c’est quoi cette vilaine mise en page? Tu étais supposé "
                    "conserver ma mise en page alignée avec la charte graphique vingt mars… "
                    "Reprends la page initiale et adapte le contenu en conservant la mise "
                    "en forme."
                )
            },
        ),
        make_event(
            "turn.checkpoint",
            {
                "last_assistant_message": (
                    "Tu avais raison. J’ai corrigé le tir et j’ai restauré la mise en page "
                    "initiale."
                )
            },
        ),
    ]


class CandidateExtractionTests(unittest.TestCase):
    def test_vingt_mars_feedback_produces_expected_delivery_standard(self) -> None:
        candidates = extract_memory_candidates(
            example_events(), source_session="codex-3c00e8d6f2e34fb3"
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.source_session, "codex-3c00e8d6f2e34fb3")
        self.assertEqual(candidate.candidate_type, "delivery_standard")
        self.assertEqual(candidate.proposed_memory, EXPECTED_VINGT_MARS_MEMORY)
        self.assertIn("insatisfaction utilisateur explicite", candidate.signal.lower())
        self.assertIn("reconnaît ensuite l’erreur", candidate.signal)

    def test_vague_complaint_does_not_create_a_candidate(self) -> None:
        events = [make_event("turn.input", {"prompt": "Ce n’est pas bon, recommence."})]

        self.assertEqual(
            extract_memory_candidates(events, source_session="session-vague"),
            [],
        )

    def test_one_off_preference_does_not_create_a_candidate(self) -> None:
        events = [
            make_event(
                "turn.input",
                {"prompt": "Pour ce fichier uniquement, je préfère une présentation bleue."},
            )
        ]

        self.assertEqual(
            extract_memory_candidates(events, source_session="session-one-off"),
            [],
        )

    def test_known_secret_shape_blocks_candidate(self) -> None:
        events = [
            make_event(
                "turn.input",
                {
                    "prompt": (
                        "La prochaine fois, utilise l’outil avec le token "
                        "sk-abcdefghijklmnop et vérifie le résultat."
                    )
                },
            )
        ]

        self.assertEqual(
            extract_memory_candidates(events, source_session="session-secret"),
            [],
        )

    def test_process_correction_without_complaint_creates_tooling_rule(self) -> None:
        events = [
            make_event(
                "turn.input",
                {
                    "prompt": (
                        "La prochaine fois, vérifie la source de vérité du projet avant "
                        "d’utiliser le gabarit d’export."
                    )
                },
            )
        ]

        candidates = extract_memory_candidates(events, source_session="session-tooling")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_type, "tooling_rule")
        self.assertIn("source de vérité", candidates[0].proposed_memory)


class CandidatePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = MemoryEngine(make_settings(self.root))
        self.engine.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_snapshot_writes_pending_reviewable_candidate_idempotently(self) -> None:
        for event in example_events():
            self.engine.record(
                event_type=event.event_type,
                host=event.host,
                host_session_id=event.host_session_id,
                project=event.project,
                cwd=event.cwd,
                payload=event.payload,
            )
        session_id = build_session_id("codex", "example")

        session_note = self.engine.snapshot(session_id)
        candidate_paths = list(self.engine.settings.candidates_path.glob("*.md"))

        self.assertEqual(len(candidate_paths), 1)
        session_content = session_note.read_text(encoding="utf-8")
        candidate_content = candidate_paths[0].read_text(encoding="utf-8")
        self.assertIn("## Candidats à la mémoire durable", session_content)
        self.assertIn(EXPECTED_VINGT_MARS_MEMORY, session_content)
        self.assertIn("status: pending", candidate_content)
        self.assertIn('candidate_type: "delivery_standard"', candidate_content)
        self.assertIn(f'source_session: "{session_id}"', candidate_content)
        self.assertIn("source_of_truth: false", candidate_content)
        self.assertIn("## Signal observé", candidate_content)
        self.assertIn("## Décision de consolidation", candidate_content)

        reviewed_content = candidate_content.replace("- [ ] Ignorer", "- [x] Ignorer")
        candidate_paths[0].write_text(reviewed_content, encoding="utf-8")
        self.engine.snapshot(session_id)

        self.assertEqual(
            candidate_paths[0].read_text(encoding="utf-8"),
            reviewed_content,
        )

    def test_pending_candidate_is_not_returned_by_recall(self) -> None:
        self.engine.remember(
            content="Use the unique-review-only-tool for every durable export.",
            kind="tooling_rule",
            project="vingt-mars",
            source_session_id="source",
        )

        context, results = self.engine.recall(
            "unique-review-only-tool",
            project="vingt-mars",
        )

        self.assertEqual(context, "")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
