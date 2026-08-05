from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .models import SessionState
from .util import atomic_write_text, isoformat, slugify

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_markdown(path: Path) -> tuple[dict[str, str], str, str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    metadata: dict[str, str] = {}
    body = content
    match = FRONTMATTER_RE.match(content)
    if match:
        body = content[match.end() :]
        for line in match.group(1).splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            key, raw_value = line.split(":", 1)
            value = raw_value.strip()
            if value.startswith('"') and value.endswith('"'):
                with suppress(json.JSONDecodeError):
                    value = json.loads(value)
            metadata[key.strip()] = str(value)
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("-", " ")
    return metadata, title, content


class MarkdownStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def session_note_path(self, state: SessionState) -> Path:
        try:
            started = datetime.fromisoformat(state.started_at.replace("Z", "+00:00"))
        except ValueError:
            started = datetime.now(timezone.utc)
        return (
            self.settings.session_notes_path
            / f"{started.year:04d}"
            / f"{started.month:02d}"
            / f"{state.session_id}.md"
        )

    def write_session(self, state: SessionState, markdown: str) -> Path:
        path = self.session_note_path(state)
        atomic_write_text(path, markdown)
        return path

    def write_candidate(
        self,
        *,
        content: str,
        kind: str,
        project: str,
        source_session_id: str | None = None,
    ) -> Path:
        digest = hashlib.sha256(content.encode()).hexdigest()[:10]
        candidate_id = f"candidate-{slugify(kind)}-{digest}"
        path = self.settings.candidates_path / f"{candidate_id}.md"
        now = isoformat()
        source_line = (
            f"source_session: {json.dumps(source_session_id)}\n" if source_session_id else ""
        )
        markdown = (
            "---\n"
            f"id: {json.dumps('memory.' + candidate_id)}\n"
            "type: memory_candidate\n"
            "status: pending\n"
            f"candidate_type: {json.dumps(kind)}\n"
            f"project: {json.dumps(project)}\n"
            f"created_at: {json.dumps(now)}\n"
            f"{source_line}"
            "source_of_truth: false\n"
            "---\n\n"
            f"# Candidat — {kind.replace('_', ' ').title()}\n\n"
            "## Proposition\n\n"
            f"{content.strip()}\n\n"
            "## Décision de consolidation\n\n"
            "- [ ] Créer\n"
            "- [ ] Renforcer\n"
            "- [ ] Remplacer\n"
            "- [ ] Contradiction à examiner\n"
            "- [ ] Ignorer\n"
        )
        atomic_write_text(path, markdown)
        return path

    def iter_markdown(self) -> list[Path]:
        runtime = self.settings.runtime_path
        paths: list[Path] = []
        for path in self.settings.vault_path.rglob("*.md"):
            try:
                path.relative_to(runtime)
                continue
            except ValueError:
                pass
            if any(
                part.startswith(".") for part in path.relative_to(self.settings.vault_path).parts
            ):
                continue
            paths.append(path)
        return sorted(paths)
