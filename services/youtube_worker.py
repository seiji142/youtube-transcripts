"""Worker durable de ASR (Fase 2, bloque D — decisión D1).

Thread único que consume la cola ``youtube_jobs``: descarga audio,
transcribe con faster-whisper, guarda en la caché y limpia temporales.

- **Durable**: el estado vive en SQLite; un crash no pierde el job
  (``reclaim_stale`` lo devuelve a ``pending`` por heartbeat vencido).
- **Reintentos**: fallos reintentables con backoff (ver JobStore);
  errores terminales (duración, ASR sin habla) no se reintentan.
- **Rate limit**: si se inyecta un ``RateLimiter`` (el mismo del
  servicio), las descargas del worker también respetan ≥1s (prevención
  429 del incidente 21/09).
- **Limpieza**: ``cleanup()`` corre en ``finally`` — el audio se borra
  también cuando el job falla (criterio §8).
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.youtube_asr import FasterWhisperTranscriber
from services.youtube_audio import TEMP_PREFIX, YtDlpAudioDownloader
from services.youtube_cache import TranscriptCache
from services.youtube_errors import AsrFailed, DurationExceeded, TranscriptError
from services.youtube_jobs import JobStore
from services.youtube_rate_limit import RateLimiter
from services.youtube_service import MAX_DURATION_SECONDS

SOURCE_ASR = "faster_whisper"
TRACK_TYPE_ASR = "asr"
_ORPHAN_MAX_AGE_SECONDS = 3600.0

# Errores que un reintento no va a arreglar (no pierden intentos en vano).
_TERMINAL_CODES = {DurationExceeded.code, AsrFailed.code}


def sweep_temporals(
    base_dir: Path | None = None,
    max_age_seconds: float = _ORPHAN_MAX_AGE_SECONDS,
    now: float | None = None,
) -> list[Path]:
    """Elimina directorios temporales huérfanos del downloader.

    Solo toca dirs con prefijo ``youtube_transcripts_`` más viejos que
    ``max_age_seconds`` (huérfanos de crashes; lo normal se borra en
    ``cleanup`` tras cada job). Idempotente; devuelve los eliminados.
    """
    base = Path(base_dir) if base_dir is not None else Path(tempfile.gettempdir())
    if not base.is_dir():
        return []
    now_ts = now if now is not None else time.time()
    removed: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or not entry.name.startswith(TEMP_PREFIX):
            continue
        try:
            age = now_ts - entry.stat().st_mtime
        except OSError:
            continue
        if age > max_age_seconds:
            shutil.rmtree(entry, ignore_errors=True)
            if not entry.exists():
                removed.append(entry)
    return removed


class AsrWorker:
    """Procesa jobs ASR de ``youtube_jobs`` de a uno por llamada."""

    def __init__(
        self,
        jobs: JobStore,
        cache: TranscriptCache,
        downloader: Any | None = None,
        transcriber: Any | None = None,
        rate_limiter: RateLimiter | None = None,
        max_duration_seconds: int = MAX_DURATION_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.jobs = jobs
        self.cache = cache
        self.downloader = downloader if downloader is not None else YtDlpAudioDownloader()
        self.transcriber = transcriber if transcriber is not None else FasterWhisperTranscriber()
        self.rate_limiter = rate_limiter
        self.max_duration_seconds = max_duration_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run_once(self) -> dict[str, Any] | None:
        """Recupera jobs zombies, procesa a lo sumo uno y devuelve su estado.

        Devuelve ``None`` si no había trabajo vencido.
        """
        self.jobs.reclaim_stale(now=self._clock())
        job = self.jobs.claim_next(now=self._clock())
        if job is None:
            return None

        try:
            self._process(job)
        except TranscriptError as exc:
            self.jobs.mark_failed(
                job["job_id"],
                error_code=exc.code,
                error_message=exc.message,
                now=self._clock(),
                terminal=exc.code in _TERMINAL_CODES,
            )
        except Exception as exc:  # noqa: BLE001 — nunca matar el loop del worker
            self.jobs.mark_failed(
                job["job_id"],
                error_code="transcript_error",
                error_message=str(exc),
                now=self._clock(),
            )

        updated = self.jobs.get(job_id=job["job_id"])
        return updated

    def run_forever(
        self,
        poll_interval: float = 2.0,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Loop del worker: sweep + run_once, duerme si no hay trabajo."""
        stop = stop_event if stop_event is not None else threading.Event()
        while not stop.is_set():
            sweep_temporals()
            job = self.run_once()
            if job is None:
                stop.wait(poll_interval)

    def _process(self, job: dict[str, Any]) -> None:
        job_id = job["job_id"]
        video_id = job["video_id"]

        # Prevención 429: misma instancia (o equivalente) que el servicio.
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()

        self.jobs.heartbeat(job_id, now=self._clock(), stage="downloading")
        audio = self.downloader.download(video_id)
        try:
            if audio.duration is not None and audio.duration > self.max_duration_seconds:
                raise DurationExceeded(
                    f"El video dura {audio.duration:.0f}s "
                    f"(máximo {self.max_duration_seconds}s)",
                    video_id=video_id,
                    suggestion="Los videos mayores a 2h no están soportados en v1",
                )

            self.jobs.heartbeat(job_id, now=self._clock(), stage="transcribing")
            # Autodetect de idioma (language=None); los idiomas pedidos
            # quedan en el job (languages) por si el servicio los usa.
            asr = self.transcriber.transcribe(audio.path, language=None)
        finally:
            # Criterio §8: audio eliminado tras ASR o tras cualquier fallo.
            self.downloader.cleanup(audio)

        self.cache.set(
            video_id,
            job["lang_key"],
            TRACK_TYPE_ASR,
            segments=asr.segments,
            language_code=asr.language,
            source=SOURCE_ASR,
        )
        self.jobs.mark_completed(job_id, now=self._clock())
