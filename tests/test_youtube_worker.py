"""Tests del worker ASR (dobles falsos: sin red ni modelo real)."""
from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from services.youtube_asr import AsrResult
from services.youtube_audio import TEMP_PREFIX, AudioDownloadResult
from services.youtube_cache import TranscriptCache
from services.youtube_errors import AsrFailed, AudioDownloadFailed
from services.youtube_jobs import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    JobStore,
)
from services.youtube_worker import AsrWorker, sweep_temporals

VIDEO_ID = "dQw4w9WgXcQ"
LANGS = ["es", "en"]
T0 = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


class FakeDownloader:
    """Escribe un WAV en un temporal real y registra cleanups."""

    def __init__(self, base_dir: Path, duration: float | None = 19.0,
                 error: Exception | None = None) -> None:
        self.base_dir = base_dir
        self.duration = duration
        self.error = error
        self.downloaded: list[str] = []
        self.cleaned: list[AudioDownloadResult] = []

    def download(self, video_id: str) -> AudioDownloadResult:
        if self.error is not None:
            raise self.error
        self.downloaded.append(video_id)
        work_dir = Path(
            f"{self.base_dir}/{TEMP_PREFIX}{video_id}_fake"
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        path = work_dir / f"{video_id}.wav"
        path.write_bytes(b"RIFF0000WAVE")
        return AudioDownloadResult(
            video_id=video_id, path=path, work_dir=work_dir,
            ext="wav", duration=self.duration,
        )

    def cleanup(self, result: AudioDownloadResult) -> None:
        shutil.rmtree(result.work_dir, ignore_errors=True)
        self.cleaned.append(result)


class FakeTranscriber:
    def __init__(self, result: AsrResult | None = None,
                 error: Exception | None = None) -> None:
        self.result = result if result is not None else AsrResult(
            language="es",
            segments=[{"start": 0.0, "end": 1.5, "text": "hola mundo"}],
        )
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, path: Any, language: str | None = None) -> AsrResult:
        self.calls.append({"path": str(path), "language": language})
        if self.error is not None:
            raise self.error
        return self.result


class FakeRateLimiter:
    def __init__(self) -> None:
        self.acquired = 0

    def acquire(self) -> float:
        self.acquired += 1
        return 0.0


@pytest.fixture
def jobs(tmp_path: Path) -> JobStore:
    store = JobStore(db_path=tmp_path / "jobs.db", backoff_base_seconds=30.0)
    yield store
    store.close()


@pytest.fixture
def cache(tmp_path: Path) -> TranscriptCache:
    c = TranscriptCache(db_path=tmp_path / "cache.db")
    yield c
    c.close()


@pytest.fixture
def downloader(tmp_path: Path) -> FakeDownloader:
    return FakeDownloader(base_dir=tmp_path / "audio")


def _worker(
    jobs: JobStore,
    cache: TranscriptCache,
    downloader: FakeDownloader,
    transcriber: FakeTranscriber | None = None,
    rate_limiter: Any | None = None,
) -> AsrWorker:
    return AsrWorker(
        jobs=jobs,
        cache=cache,
        downloader=downloader,
        transcriber=transcriber if transcriber is not None else FakeTranscriber(),
        rate_limiter=rate_limiter,
    )


class TestRunOnce:
    def test_sin_jobs_devuelve_none(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        worker = _worker(jobs, cache, downloader)
        assert worker.run_once() is None

    def test_happy_path_completa_job_y_guarda_en_cache(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader)

        job = worker.run_once()

        assert job is not None
        assert job["status"] == STATUS_COMPLETED
        assert job["stage"] == "done"
        # resultado en caché con source/track del plan
        entry = cache.get(VIDEO_ID, "es+en", "asr")
        assert entry is not None
        assert entry["source"] == "faster_whisper"
        assert entry["language_code"] == "es"
        assert entry["segments"][0]["text"] == "hola mundo"
        # audio limpiado (criterio §8)
        assert len(downloader.cleaned) == 1
        assert not downloader.cleaned[0].work_dir.exists()

    def test_duration_exceeded_falla_terminal_y_limpia(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        downloader.duration = 999999.0
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader)

        job = worker.run_once()

        assert job is not None
        assert job["status"] == STATUS_FAILED
        assert job["error_code"] == "duration_exceeded"
        assert job["attempts"] == 1  # sin reintentos: terminal
        assert len(downloader.cleaned) == 1  # finally limpió
        assert cache.get(VIDEO_ID, "es+en", "asr") is None

    def test_fallo_descarga_es_reintentable_sin_cleanup(
        self, jobs: JobStore, cache: TranscriptCache, tmp_path: Path,
    ) -> None:
        downloader = FakeDownloader(
            base_dir=tmp_path / "audio",
            error=AudioDownloadFailed("network boom", video_id=VIDEO_ID),
        )
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader)

        job = worker.run_once()

        assert job is not None
        assert job["status"] == STATUS_PENDING  # backoff: reintentable
        assert job["error_code"] == "audio_download_failed"
        assert job["attempts"] == 1
        # el downloader ya limpia su temporal en fallo; worker no llama cleanup
        assert downloader.cleaned == []

    def test_asr_sin_segmentos_falla_terminal(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        transcriber = FakeTranscriber(error=AsrFailed("no produjo segmentos"))
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader, transcriber=transcriber)

        job = worker.run_once()

        assert job is not None
        assert job["status"] == STATUS_FAILED
        assert job["error_code"] == "asr_failed"
        assert len(downloader.cleaned) == 1

    def test_excepcion_inesperada_es_reintentable(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        transcriber = FakeTranscriber(error=RuntimeError("cpu on fire"))
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader, transcriber=transcriber)

        job = worker.run_once()

        assert job is not None
        assert job["status"] == STATUS_PENDING
        assert job["error_code"] == "transcript_error"
        assert "cpu on fire" in (job["error_message"] or "")

    def test_rate_limiter_se_invoca_antes_de_descargar(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        limiter = FakeRateLimiter()
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader, rate_limiter=limiter)

        worker.run_once()

        assert limiter.acquired == 1
        assert downloader.downloaded == [VIDEO_ID]

    def test_transcribe_recibe_language_none_autodetect(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        transcriber = FakeTranscriber()
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader, transcriber=transcriber)

        worker.run_once()

        assert transcriber.calls[0]["language"] is None

    def test_job_fallido_no_vuelve_a_ejecutar_sin_vencer_backoff(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        downloader.error = AudioDownloadFailed("down", video_id=VIDEO_ID)
        jobs.create_or_get(VIDEO_ID, LANGS, now=T0)
        worker = _worker(jobs, cache, downloader)
        worker.run_once()

        assert worker.run_once() is None  # backoff 30s: nada vencido


class TestRunForever:
    def test_stop_pre_sett_no_procesa_nada(
        self, jobs: JobStore, cache: TranscriptCache, downloader: FakeDownloader,
    ) -> None:
        jobs.create_or_get(VIDEO_ID, LANGS)  # pending, pero loop no arranca
        worker = _worker(jobs, cache, downloader)
        stop = threading.Event()
        stop.set()

        worker.run_forever(poll_interval=0.01, stop_event=stop)

        assert downloader.downloaded == []


class TestSweepTemporals:
    def test_elimina_solo_prefijo_viejo(self, tmp_path: Path) -> None:
        old = tmp_path / f"{TEMP_PREFIX}aaaa_ old"
        old.mkdir()
        young = tmp_path / f"{TEMP_PREFIX}bbbb_ young"
        young.mkdir()
        other = tmp_path / "otra_cosa"
        other.mkdir()
        stale_time = 7200.0
        now = 100000.0
        os.utime(old, (now - stale_time, now - stale_time))
        os.utime(young, (now, now))

        removed = sweep_temporals(base_dir=tmp_path, max_age_seconds=3600.0, now=now)

        assert removed == [old]
        assert not old.exists()
        assert young.exists()
        assert other.exists()

    def test_base_inexistente_devuelve_vacio(self, tmp_path: Path) -> None:
        assert sweep_temporals(base_dir=tmp_path / "nope") == []

    def test_segunda_corrida_es_idempotente(self, tmp_path: Path) -> None:
        old = tmp_path / f"{TEMP_PREFIX}cccc_x"
        old.mkdir()
        now = 100000.0
        os.utime(old, (now - 7200, now - 7200))

        first = sweep_temporals(base_dir=tmp_path, now=now)
        second = sweep_temporals(base_dir=tmp_path, now=now)

        assert first == [old]
        assert second == []
