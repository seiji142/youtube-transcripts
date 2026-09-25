"""Índice FTS5 de chunks de transcripción (Fase 3).

Tablas en la misma DB que la caché y los jobs (``data/youtube.db``):

- ``transcript_chunks``: tabla normal con los chunks (texto + timestamps).
- ``transcript_chunks_fts``: FTS5 *external content* sobre la anterior.

La indexación es **lazy**: se ejecuta en la primera búsqueda del video
(``ensure_indexed``) y es idempotente (borra e reinserta por clave
``video_id + lang + track_type``).

Búsqueda: ``bm25()`` (orden ascendente: más negativo = más relevante),
filtrada por ``video_id``. La query del usuario se sanea en tokens
literales unidos con ``OR`` — sin sintaxis FTS5 expuesta al exterior.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence

from services.youtube_chunking import chunk_transcript

DEFAULT_DB_PATH = Path("data") / "youtube.db"
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
MAX_QUERY_TERMS = 32

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    lang TEXT NOT NULL,
    track_type TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    UNIQUE (video_id, lang, track_type, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_transcript_chunks_key
    ON transcript_chunks (video_id, lang, track_type);
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_chunks_fts USING fts5(
    text,
    content='transcript_chunks',
    content_rowid='chunk_id'
);
"""

_QUERY_TOKEN_RE = re.compile(r"\S+")


def build_match_query(query: str, max_terms: int = MAX_QUERY_TERMS) -> str:
    """Sanea la query del usuario a tokens FTS5 literales unidos por OR.

    Cada término va entre comillas dobles (búsqueda literal, sin operadores
    FTS5). Los términos sin caracteres de palabra (puntuación pura) se
    descartan; si no queda ninguno, lanza ``ValueError``.

    Raises:
        ValueError: Si la query no contiene términos utilizables.
    """
    terms: list[str] = []
    for raw in _QUERY_TOKEN_RE.findall(query):
        term = raw.replace('"', "").strip()
        if not term or not re.search(r"\w", term, re.UNICODE):
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= max_terms:
            break
    if not terms:
        raise ValueError("query sin términos utilizables")
    return " OR ".join(f'"{term}"' for term in terms)


class TranscriptIndex:
    """Índice FTS5 de chunks (thread-safe, una conexión por instancia)."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.isolation_level = None  # transacciones explícitas
        self._lock = threading.Lock()
        for statement in _SCHEMA.split(";"):
            if statement.strip():
                self._conn.execute(statement)

    def index_transcript(
        self,
        video_id: str,
        lang: str,
        track_type: str,
        segments: Sequence[Any],
    ) -> int:
        """Indexa (o reindexa) la transcripción. Devuelve nº de chunks.

        Idempotente: borra los chunks previos de la clave y reinserta,
        manteniendo la tabla FTS sincronizada (borrado explícito
        ``'delete'`` de FTS5 external content).
        """
        chunks = chunk_transcript(segments)
        key = (video_id, lang, track_type)

        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                old_ids = [
                    row["chunk_id"]
                    for row in self._conn.execute(
                        "SELECT chunk_id FROM transcript_chunks "
                        "WHERE video_id = ? AND lang = ? AND track_type = ?",
                        key,
                    )
                ]
                for chunk_id in old_ids:
                    text = self._conn.execute(
                        "SELECT text FROM transcript_chunks WHERE chunk_id = ?",
                        (chunk_id,),
                    ).fetchone()
                    if text is not None:
                        self._conn.execute(
                            "INSERT INTO transcript_chunks_fts "
                            "(transcript_chunks_fts, rowid, text) "
                            "VALUES ('delete', ?, ?)",
                            (chunk_id, text["text"]),
                        )
                self._conn.execute(
                    "DELETE FROM transcript_chunks "
                    "WHERE video_id = ? AND lang = ? AND track_type = ?",
                    key,
                )

                for chunk in chunks:
                    cursor = self._conn.execute(
                        "INSERT INTO transcript_chunks "
                        "(video_id, lang, track_type, chunk_index, start, end, "
                        " text, token_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            video_id, lang, track_type, chunk.index,
                            chunk.start, chunk.end, chunk.text, chunk.token_count,
                        ),
                    )
                    self._conn.execute(
                        "INSERT INTO transcript_chunks_fts (rowid, text) "
                        "VALUES (?, ?)",
                        (cursor.lastrowid, chunk.text),
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return len(chunks)

    def is_indexed(self, video_id: str, lang: str, track_type: str) -> bool:
        """True si la clave ya tiene chunks indexados."""
        row = self._conn.execute(
            "SELECT 1 FROM transcript_chunks "
            "WHERE video_id = ? AND lang = ? AND track_type = ? LIMIT 1",
            (video_id, lang, track_type),
        ).fetchone()
        return row is not None

    def ensure_indexed(
        self,
        video_id: str,
        lang: str,
        track_type: str,
        segments: Sequence[Any],
    ) -> bool:
        """Indexa si falta. Devuelve True si indexó en esta llamada."""
        if self.is_indexed(video_id, lang, track_type):
            return False
        self.index_transcript(video_id, lang, track_type, segments)
        return True

    def search(self, video_id: str, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        """Busca chunks del video por BM25. Más negativo = más relevante.

        Args:
            video_id: Restringe la búsqueda a este video.
            query: Texto libre (saneado a tokens literales).
            top_k: Máximo de resultados (1..MAX_TOP_K).

        Returns:
            Lista de dicts con chunk_id, chunk_index, start, end, text,
            token_count, video_id y score (bm25).

        Raises:
            ValueError: query sin términos o top_k fuera de rango.
        """
        if top_k < 1 or top_k > MAX_TOP_K:
            raise ValueError(f"top_k debe estar en [1, {MAX_TOP_K}]")
        match = build_match_query(query)

        with self._lock:
            rows = self._conn.execute(
                "SELECT c.chunk_id, c.chunk_index, c.start, c.end, c.text, "
                "       c.token_count, c.video_id, "
                "       bm25(transcript_chunks_fts) AS score "
                "FROM transcript_chunks_fts "
                "JOIN transcript_chunks c ON c.chunk_id = transcript_chunks_fts.rowid "
                "WHERE transcript_chunks_fts MATCH ? AND c.video_id = ? "
                "ORDER BY score ASC "
                "LIMIT ?",
                (match, video_id, top_k),
            ).fetchall()

        return [
            {
                "chunk_id": row["chunk_id"],
                "chunk_index": row["chunk_index"],
                "start": row["start"],
                "end": row["end"],
                "text": row["text"],
                "token_count": row["token_count"],
                "video_id": row["video_id"],
                "score": row["score"],
            }
            for row in rows
        ]

    def delete(self, video_id: str, lang: str | None = None,
               track_type: str | None = None) -> None:
        """Borra chunks (y su entrada FTS) del video o de una clave exacta."""
        conditions = ["video_id = ?"]
        params: list[Any] = [video_id]
        if lang is not None:
            conditions.append("lang = ?")
            params.append(lang)
        if track_type is not None:
            conditions.append("track_type = ?")
            params.append(track_type)
        where = " AND ".join(conditions)

        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                old_ids = [
                    row["chunk_id"]
                    for row in self._conn.execute(
                        f"SELECT chunk_id FROM transcript_chunks WHERE {where}",
                        params,
                    )
                ]
                for chunk_id in old_ids:
                    text = self._conn.execute(
                        "SELECT text FROM transcript_chunks WHERE chunk_id = ?",
                        (chunk_id,),
                    ).fetchone()
                    if text is not None:
                        self._conn.execute(
                            "INSERT INTO transcript_chunks_fts "
                            "(transcript_chunks_fts, rowid, text) "
                            "VALUES ('delete', ?, ?)",
                            (chunk_id, text["text"]),
                        )
                self._conn.execute(
                    f"DELETE FROM transcript_chunks WHERE {where}", params,
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def clear(self) -> None:
        """Borra todos los chunks e índices."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._conn.execute(
                    "SELECT chunk_id, text FROM transcript_chunks"
                ).fetchall()
                for row in rows:
                    self._conn.execute(
                        "INSERT INTO transcript_chunks_fts "
                        "(transcript_chunks_fts, rowid, text) "
                        "VALUES ('delete', ?, ?)",
                        (row["chunk_id"], row["text"]),
                    )
                self._conn.execute("DELETE FROM transcript_chunks")
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TranscriptIndex":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
