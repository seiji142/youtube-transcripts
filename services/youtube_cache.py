"""Caché SQLite de transcripts.

Clave: ``video_id + lang + track_type``. TTL configurable (7 días por
defecto). La DB vive en ``data/youtube.db`` (gitignored).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path("data") / "youtube.db"
DEFAULT_TTL = timedelta(days=7)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT NOT NULL,
    lang TEXT NOT NULL,
    track_type TEXT NOT NULL,
    language_code TEXT,
    source TEXT,
    segments_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (video_id, lang, track_type)
);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class TranscriptCache:
    """Caché SQLite para segmentos de transcript."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH,
                 ttl: timedelta = DEFAULT_TTL) -> None:
        self.db_path = Path(db_path)
        self.ttl = ttl
        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, video_id: str, lang: str, track_type: str) -> dict[str, Any] | None:
        """Devuelve la entrada si existe y no expiró; si no, ``None``."""
        row = self._conn.execute(
            "SELECT * FROM transcripts "
            "WHERE video_id = ? AND lang = ? AND track_type = ?",
            (video_id, lang, track_type),
        ).fetchone()
        if row is None:
            return None

        fetched_at = _parse_ts(row["fetched_at"])
        if _utcnow() - fetched_at > self.ttl:
            self.delete(video_id, lang, track_type)
            return None

        return {
            "video_id": row["video_id"],
            "lang": row["lang"],
            "track_type": row["track_type"],
            "language_code": row["language_code"],
            "source": row["source"],
            "segments": json.loads(row["segments_json"]),
            "fetched_at": row["fetched_at"],
        }

    def set(self, video_id: str, lang: str, track_type: str,
            segments: list[dict[str, Any]],
            language_code: str | None = None,
            source: str | None = None) -> None:
        """Guarda (o sobrescribe) una entrada con timestamp actual."""
        self._conn.execute(
            "INSERT OR REPLACE INTO transcripts "
            "(video_id, lang, track_type, language_code, source, "
            " segments_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                video_id,
                lang,
                track_type,
                language_code,
                source,
                json.dumps(segments, ensure_ascii=False),
                _utcnow().isoformat(),
            ),
        )
        self._conn.commit()

    def delete(self, video_id: str, lang: str, track_type: str) -> None:
        """Elimina una entrada concreta."""
        self._conn.execute(
            "DELETE FROM transcripts WHERE video_id = ? AND lang = ? AND track_type = ?",
            (video_id, lang, track_type),
        )
        self._conn.commit()

    def clear(self) -> None:
        """Elimina todas las entradas (útil en tests)."""
        self._conn.execute("DELETE FROM transcripts")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TranscriptCache":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
