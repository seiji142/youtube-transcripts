"""Jobs durables de ASR en SQLite (Fase 2, bloque D).

Tabla ``youtube_jobs`` en la misma DB que la caché (``data/youtube.db``).
Un job es idempotente por ``video_id + lang_key`` (``job_id =
f"{video_id}:{lang_key}"``): re-encolar el mismo video no duplica trabajo.

Ciclo de vida::

    pending ──claim_next──▶ processing ──mark_completed──▶ completed
       ▲                        │
       │     mark_failed (retryable, backoff exponencial)
       └────────────────────────┘
                                └──mark_failed (terminal o
                                    attempts >= max)──▶ failed
                                └──requeue (nueva petición)──▶ pending

``failed`` no es final para el usuario: una nueva llamada de enqueue
(``create_or_get``) lo resetea a ``pending`` (D1: nueva petición =
nueva oportunidad).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path("data") / "youtube.db"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 30.0
DEFAULT_STALE_SECONDS = 900.0  # 15 min sin heartbeat → job muerto

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS youtube_jobs (
    job_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    lang_key TEXT NOT NULL,
    languages_json TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TEXT NOT NULL,
    heartbeat_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_youtube_jobs_claim
    ON youtube_jobs (status, next_attempt_at);
"""


def utcnow() -> datetime:
    """Timestamp UTC actual (sobrescribible en tests vía inyección)."""
    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    """ISO UTC de ancho fijo: orden lexicográfico == orden cronológico."""
    return value.isoformat(timespec="microseconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def make_job_id(video_id: str, lang_key: str) -> str:
    """Job id idempotente: ``{video_id}:{lang_key}``."""
    return f"{video_id}:{lang_key}"


def make_lang_key(languages: list[str] | tuple[str, ...]) -> str:
    """Clave de idiomas en el mismo formato que ``YouTubeService``."""
    return "+".join(languages)


class JobStore:
    """Almacén de jobs ASR en SQLite (thread-safe, una conn por store)."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts debe ser >= 1")
        if backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds no puede ser negativo")

        self.db_path = Path(db_path)
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # isolation_level=None → autocommit; transacciones explícitas
        # con BEGIN IMMEDIATE en claim_next (evita race entre hilos).
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.isolation_level = None
        self._lock = threading.Lock()
        for statement in _SCHEMA.split(";"):
            if statement.strip():
                self._conn.execute(statement)

    def create_or_get(
        self,
        video_id: str,
        languages: list[str] | tuple[str, ...],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Crea el job o devuelve el existente (idempotente).

        Semántica por estado del job existente:
        - ``pending``/``processing``/``completed``: se devuelve tal cual.
        - ``failed``: se resetea a ``pending`` (nueva petición del usuario).
        """
        now = now or utcnow()
        lang_key = make_lang_key(languages)
        job_id = make_job_id(video_id, lang_key)

        with self._lock:
            existing = self._get_row(job_id=job_id)
            if existing is not None:
                if existing["status"] == STATUS_FAILED:
                    return self._requeue_row(job_id, now)
                return _row_to_dict(existing)

            self._conn.execute(
                "INSERT INTO youtube_jobs "
                "(job_id, video_id, lang_key, languages_json, status, stage, "
                " attempts, max_attempts, next_attempt_at, heartbeat_at, "
                " error_code, error_message, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, NULL, NULL, ?, ?)",
                (
                    job_id, video_id, lang_key,
                    json.dumps(list(languages), ensure_ascii=False),
                    STATUS_PENDING, "queued", self.max_attempts,
                    to_iso(now), to_iso(now), to_iso(now),
                ),
            )
            row = self._get_row(job_id=job_id)
            assert row is not None
            return _row_to_dict(row)

    def claim_next(self, now: datetime | None = None) -> dict[str, Any] | None:
        """Toma el próximo job ``pending`` vencido (atómico) o ``None``.

        Al reclamar incrementa ``attempts`` y pasa a ``processing``
        con ``heartbeat`` = now.
        """
        now = now or utcnow()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT * FROM youtube_jobs "
                    "WHERE status = ? AND next_attempt_at <= ? "
                    "ORDER BY next_attempt_at, created_at LIMIT 1",
                    (STATUS_PENDING, to_iso(now)),
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return None
                attempts = int(row["attempts"]) + 1
                self._conn.execute(
                    "UPDATE youtube_jobs SET status = ?, attempts = ?, "
                    "stage = ?, heartbeat_at = ?, updated_at = ? "
                    "WHERE job_id = ?",
                    (
                        STATUS_PROCESSING, attempts, "claimed",
                        to_iso(now), to_iso(now), row["job_id"],
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            claimed = self._get_row(job_id=row["job_id"])
            assert claimed is not None
            return _row_to_dict(claimed)

    def heartbeat(
        self, job_id: str, now: datetime | None = None,
        stage: str | None = None,
    ) -> None:
        """Marca vivo al worker y opcionalmente actualiza la etapa."""
        now = now or utcnow()
        with self._lock:
            if stage is not None:
                self._conn.execute(
                    "UPDATE youtube_jobs SET heartbeat_at = ?, stage = ?, "
                    "updated_at = ? WHERE job_id = ?",
                    (to_iso(now), stage, to_iso(now), job_id),
                )
            else:
                self._conn.execute(
                    "UPDATE youtube_jobs SET heartbeat_at = ?, updated_at = ? "
                    "WHERE job_id = ?",
                    (to_iso(now), to_iso(now), job_id),
                )

    def mark_completed(self, job_id: str, now: datetime | None = None) -> None:
        """Cierra el job como ``completed`` (stage ``done``)."""
        now = now or utcnow()
        with self._lock:
            self._conn.execute(
                "UPDATE youtube_jobs SET status = ?, stage = ?, "
                "heartbeat_at = ?, error_code = NULL, error_message = NULL, "
                "updated_at = ? WHERE job_id = ?",
                (STATUS_COMPLETED, "done", to_iso(now), to_iso(now), job_id),
            )

    def mark_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        now: datetime | None = None,
        terminal: bool = False,
    ) -> dict[str, Any]:
        """Registra un fallo.

        Si ``terminal`` o ``attempts >= max_attempts`` → ``failed``;
        si no → ``pending`` con backoff ``base * 2^(attempts-1)``.
        Devuelve el job actualizado.
        """
        now = now or utcnow()
        with self._lock:
            row = self._get_row(job_id=job_id)
            if row is None:
                raise KeyError(f"job no existe: {job_id}")
            attempts = int(row["attempts"])
            max_attempts = int(row["max_attempts"])
            give_up = terminal or attempts >= max_attempts
            if give_up:
                status = STATUS_FAILED
                next_attempt = now
            else:
                status = STATUS_PENDING
                delay = self.backoff_base_seconds * (2 ** max(attempts - 1, 0))
                next_attempt = now + timedelta(seconds=delay)
            self._conn.execute(
                "UPDATE youtube_jobs SET status = ?, stage = ?, "
                "next_attempt_at = ?, error_code = ?, error_message = ?, "
                "updated_at = ? WHERE job_id = ?",
                (
                    status, "failed", to_iso(next_attempt),
                    error_code, error_message[:500], to_iso(now), job_id,
                ),
            )
            row = self._get_row(job_id=job_id)
            assert row is not None
            return _row_to_dict(row)

    def requeue(self, job_id: str, now: datetime | None = None) -> dict[str, Any]:
        """Resetea un job (cualquier estado) a ``pending`` con intentos en 0."""
        now = now or utcnow()
        with self._lock:
            return self._requeue_row(job_id, now)

    def get(
        self,
        job_id: str | None = None,
        video_id: str | None = None,
        lang_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Obtiene un job por id, o por video (+lang_key opcional: el más reciente)."""
        with self._lock:
            if job_id is not None:
                row = self._get_row(job_id=job_id)
            elif video_id is not None and lang_key is not None:
                row = self._get_row(
                    video_id=video_id, lang_key=lang_key,
                )
            elif video_id is not None:
                row = self._conn.execute(
                    "SELECT * FROM youtube_jobs WHERE video_id = ? "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (video_id,),
                ).fetchone()
            else:
                raise ValueError("proporcionar job_id o video_id")
            return _row_to_dict(row) if row is not None else None

    def reclaim_stale(
        self,
        now: datetime | None = None,
        stale_seconds: float = DEFAULT_STALE_SECONDS,
    ) -> int:
        """Devuelve a ``pending`` los jobs ``processing`` con heartbeat vencido.

        Detecta workers muertos (crash a mitad de ASR). Devuelve la
        cantidad de jobs recuperados. Los ``attempts`` ya contados no
        se resetean (el intento fallido sigue contando).
        """
        now = now or utcnow()
        cutoff = now - timedelta(seconds=stale_seconds)
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE youtube_jobs SET status = ?, stage = ?, "
                "next_attempt_at = ?, updated_at = ? "
                "WHERE status = ? AND (heartbeat_at IS NULL OR heartbeat_at < ?)",
                (
                    STATUS_PENDING, "reclaimed", to_iso(now), to_iso(now),
                    STATUS_PROCESSING, to_iso(cutoff),
                ),
            )
            return cursor.rowcount

    def clear(self) -> None:
        """Borra todos los jobs (tests)."""
        with self._lock:
            self._conn.execute("DELETE FROM youtube_jobs")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "JobStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get_row(self, **filters: str) -> sqlite3.Row | None:
        clauses = " AND ".join(f"{key} = ?" for key in filters)
        return self._conn.execute(
            f"SELECT * FROM youtube_jobs WHERE {clauses}",  # noqa: S608 — filtros internos
            tuple(filters.values()),
        ).fetchone()

    def _requeue_row(self, job_id: str, now: datetime) -> dict[str, Any]:
        self._conn.execute(
            "UPDATE youtube_jobs SET status = ?, stage = ?, attempts = 0, "
            "next_attempt_at = ?, heartbeat_at = NULL, "
            "error_code = NULL, error_message = NULL, updated_at = ? "
            "WHERE job_id = ?",
            (STATUS_PENDING, "queued", to_iso(now), to_iso(now), job_id),
        )
        row = self._get_row(job_id=job_id)
        assert row is not None
        return _row_to_dict(row)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["languages"] = json.loads(data.pop("languages_json"))
    data["attempts"] = int(data["attempts"])
    data["max_attempts"] = int(data["max_attempts"])
    return data
