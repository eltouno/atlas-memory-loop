from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing

from .config import Settings
from .markdown_store import MarkdownStore, parse_markdown
from .models import RecallResult

TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)


class SearchIndex:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.markdown = MarkdownStore(settings)

    def connect(self) -> sqlite3.Connection:
        self.settings.index_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.settings.index_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema(connection)
        return connection

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                path TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                note_type TEXT NOT NULL,
                project TEXT NOT NULL,
                status TEXT NOT NULL,
                content TEXT NOT NULL,
                checksum TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                path UNINDEXED,
                title,
                content,
                tokenize='unicode61 remove_diacritics 2'
            );
            """
        )

    def sync(self) -> dict[str, int]:
        indexed = 0
        unchanged = 0
        deleted = 0
        current_paths: set[str] = set()

        with closing(self.connect()) as connection:
            known = {
                row["path"]: (row["checksum"], row["mtime_ns"])
                for row in connection.execute("SELECT path, checksum, mtime_ns FROM documents")
            }
            for path in self.markdown.iter_markdown():
                relative = path.relative_to(self.settings.vault_path).as_posix()
                current_paths.add(relative)
                stat = path.stat()
                if relative in known and known[relative][1] == stat.st_mtime_ns:
                    unchanged += 1
                    continue
                metadata, title, content = parse_markdown(path)
                checksum = hashlib.sha256(content.encode()).hexdigest()
                if relative in known and known[relative][0] == checksum:
                    connection.execute(
                        "UPDATE documents SET mtime_ns = ? WHERE path = ?",
                        (stat.st_mtime_ns, relative),
                    )
                    unchanged += 1
                    continue
                connection.execute("DELETE FROM documents_fts WHERE path = ?", (relative,))
                connection.execute("DELETE FROM documents WHERE path = ?", (relative,))
                connection.execute(
                    """
                    INSERT INTO documents(
                        path, title, note_type, project, status, content, checksum, mtime_ns
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        relative,
                        title,
                        metadata.get("type", "note"),
                        metadata.get("project", metadata.get("domain", "global")),
                        metadata.get("status", "active"),
                        content,
                        checksum,
                        stat.st_mtime_ns,
                    ),
                )
                connection.execute(
                    "INSERT INTO documents_fts(path, title, content) VALUES (?, ?, ?)",
                    (relative, title, content),
                )
                indexed += 1

            stale_paths = set(known) - current_paths
            for relative in stale_paths:
                connection.execute("DELETE FROM documents_fts WHERE path = ?", (relative,))
                connection.execute("DELETE FROM documents WHERE path = ?", (relative,))
                deleted += 1

            connection.commit()

        return {"indexed": indexed, "unchanged": unchanged, "deleted": deleted}

    def search(
        self,
        query: str,
        *,
        project: str | None = None,
        limit: int = 8,
    ) -> list[RecallResult]:
        limit = max(1, min(limit, 50))
        tokens = TOKEN_RE.findall(query.lower())
        with closing(self.connect()) as connection:
            # Pending candidates are proposals for human review, never recallable knowledge.
            filters = ["d.status NOT IN ('obsolete', 'archived', 'pending')"]
            parameters: list[object] = []
            if project:
                filters.append("(d.project = ? OR d.project = 'global')")
                parameters.append(project)
            where_filter = " AND ".join(filters)

            if tokens:
                match_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
                rows = connection.execute(
                    f"""
                    SELECT d.path, d.title, d.note_type, d.project, d.status,
                           snippet(documents_fts, 2, '', '', ' … ', 28) AS snippet,
                           bm25(documents_fts, 1.5, 1.0) AS rank
                    FROM documents_fts
                    JOIN documents d ON d.path = documents_fts.path
                    WHERE documents_fts MATCH ? AND {where_filter}
                    ORDER BY rank ASC
                    LIMIT ?
                    """,
                    [match_query, *parameters, limit],
                ).fetchall()
                return [
                    RecallResult(
                        path=row["path"],
                        title=row["title"],
                        note_type=row["note_type"],
                        project=row["project"],
                        status=row["status"],
                        snippet=" ".join((row["snippet"] or "").split()),
                        score=-float(row["rank"]),
                    )
                    for row in rows
                ]

            rows = connection.execute(
                f"""
                SELECT d.path, d.title, d.note_type, d.project, d.status,
                       substr(d.content, 1, 600) AS snippet,
                       d.mtime_ns
                FROM documents d
                WHERE {where_filter}
                ORDER BY d.mtime_ns DESC
                LIMIT ?
                """,
                [*parameters, limit],
            ).fetchall()
            return [
                RecallResult(
                    path=row["path"],
                    title=row["title"],
                    note_type=row["note_type"],
                    project=row["project"],
                    status=row["status"],
                    snippet=" ".join((row["snippet"] or "").split()),
                    score=0.0,
                )
                for row in rows
            ]

    def document_count(self) -> int:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()
            return int(row["count"])
