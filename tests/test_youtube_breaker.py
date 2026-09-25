"""Tests del circuit breaker + métricas (Fase 4 E2, sin red)."""
from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any

import pytest

from services.youtube_asr import AsrResult
from services.youtube_audio import TEMP_PREFIX, AudioDownloadResult
from services.youtube_breaker import (
    DEFAULT_COOLDOWN_SECONDS,
    CircuitBreaker,
    ProviderMetrics,
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
)
from services.youtube_cache import TranscriptCache
from services.youtube_errors import (
    NoCaptionsAvailable,
    ProviderUnavailable,
    TranscriptError,
    VideoBlockedOrUnavailable,
)
from services.youtube_jobs import JobStore
from services.youtube_providers import (
    ProviderResult,
    TranscriptProvider,
    TranscriptSegment,
)
from services.youtube_service import YouTubeService
from services.youtube_worker import AsrWorker

VIDEO_ID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _breaker(**kwargs: Any) -> tuple[CircuitBreaker, _Clock]:
    clock = _Clock()
    breaker = CircuitBreaker(
        "test", failure_threshold=3, window_seconds=60.0,
        cooldown_seconds=30.0, jitter_ratio=0.0,
        clock=clock, rng=random.Random(42), **kwargs,
    )
    return breaker, clock


class _Blocked(TranscriptProvider):
    name = "blocked"

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, video_id: str, languages: Any) -> ProviderResult:
        self.calls += 1
        raise VideoBlockedOrUnavailable("bloqueo", video_id=video_id)


class TestValidacion:
    def test_defaults_esperados(self) -> None:
        breaker = CircuitBreaker("d")
        assert breaker.failure_threshold == 5
        assert breaker.window_seconds == 60.0
        assert breaker.cooldown_seconds == DEFAULT_COOLDOWN_SECONDS

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"failure_threshold": 0},
            {"window_seconds": 0.0},
            {"cooldown_seconds": -1.0},
            {"jitter_ratio": 1.0},
            {"jitter_ratio": -0.1},
        ],
    )
    def test_parametros_invalidos(self, kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            CircuitBreaker("x", **kwargs)


class TestTransiciones:
    def test_empieza_cerrado(self) -> None:
        breaker, _ = _breaker()
        assert breaker.state == STATE_CLOSED
        assert breaker.allow() is True

    def test_abre_al_alcanzar_umbral(self) -> None:
        breaker, _ = _breaker()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.allow() is True
        breaker.record_failure()

        assert breaker.state == STATE_OPEN
        assert breaker.allow() is False

    def test_fallos_fuera_de_ventana_no_cuentan(self) -> None:
        breaker, clock = _breaker()
        breaker.record_failure()
        breaker.record_failure()
        clock.advance(61.0)
        breaker.record_failure()

        assert breaker.state == STATE_CLOSED

    def test_cooldown_vencido_permite_prueba(self) -> None:
        breaker, clock = _breaker()
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == STATE_OPEN

        clock.advance(30.0)
        assert breaker.state == STATE_HALF_OPEN
        assert breaker.allow() is True

    def test_exito_en_half_open_cierra(self) -> None:
        breaker, clock = _breaker()
        for _ in range(3):
            breaker.record_failure()
        clock.advance(30.0)
        assert breaker.state == STATE_HALF_OPEN

        breaker.record_success()
        assert breaker.state == STATE_CLOSED
        assert breaker.failure_count == 0

    def test_fallo_en_half_open_reabre(self) -> None:
        breaker, clock = _breaker()
        for _ in range(3):
            breaker.record_failure()
        clock.advance(30.0)
        assert breaker.state == STATE_HALF_OPEN

        breaker.record_failure()
        assert breaker.state == STATE_OPEN

    def test_cooldown_con_jitter_en_rango(self) -> None:
        clock = _Clock()
        breaker = CircuitBreaker(
            "j", failure_threshold=1, cooldown_seconds=100.0,
            jitter_ratio=0.2, clock=clock, rng=random.Random(7),
        )
        breaker.record_failure()

        # jitter ±20%: cooldown en [80, 120]
        clock.advance(79.9)
        assert breaker.state == STATE_OPEN
        clock.advance(40.2)  # total 120.1 > máximo posible
        assert breaker.state == STATE_HALF_OPEN

    def test_cooldown_sin_jitter_exacto(self) -> None:
        breaker, clock = _breaker()
        for _ in range(3):
            breaker.record_failure()

        clock.advance(29.9)
        assert breaker.state == STATE_OPEN
        clock.advance(0.1)
        assert breaker.state == STATE_HALF_OPEN


class TestCall:
    def test_exito_devuelve_resultado(self) -> None:
        breaker, _ = _breaker()
        assert breaker.call(lambda: 42) == 42
        assert breaker.state == STATE_CLOSED

    def test_no_captions_cuenta_como_exito(self) -> None:
        breaker, _ = _breaker()

        def _empty() -> None:
            raise NoCaptionsAvailable("vacío", video_id=VIDEO_ID)

        with pytest.raises(NoCaptionsAvailable):
            breaker.call(_empty)
        assert breaker.state == STATE_CLOSED
        assert breaker.failure_count == 0

    def test_error_cuenta_como_fallo_y_propaga(self) -> None:
        breaker, _ = _breaker()

        def _boom() -> None:
            raise VideoBlockedOrUnavailable("bloqueo", video_id=VIDEO_ID)

        with pytest.raises(VideoBlockedOrUnavailable):
            breaker.call(_boom)
        assert breaker.failure_count == 1

    def test_abierto_no_ejecuta_fn(self) -> None:
        breaker, _ = _breaker()
        called: list[bool] = []
        for _ in range(3):
            try:
                breaker.call(_boom_or_false)
            except VideoBlockedOrUnavailable:
                pass

        with pytest.raises(ProviderUnavailable) as exc_info:
            breaker.call(lambda: called.append(True))

        assert called == []
        assert exc_info.value.code == "provider_unavailable"


def _boom_or_false() -> bool:
    raise VideoBlockedOrUnavailable("bloqueo", video_id=VIDEO_ID)


class TestMetrics:
    def test_snapshot_vacio(self) -> None:
        assert ProviderMetrics().snapshot() == {}

    def test_registra_por_outcome(self) -> None:
        metrics = ProviderMetrics()
        metrics.record("a", "success", 0.5)
        metrics.record("a", "empty", 0.1)
        metrics.record("a", "failure", 0.2, error_code="blocked")
        metrics.record("a", "rejected")

        snap = metrics.snapshot()["a"]
        assert snap["calls"] == 4
        assert snap["success"] == 1
        assert snap["empties"] == 1
        assert snap["failures"] == 1
        assert snap["rejected"] == 1
        assert snap["last_error"] == "blocked"
        assert snap["last_latency_s"] == 0.0

    def test_proveedores_aislados(self) -> None:
        metrics = ProviderMetrics()
        metrics.record("a", "success")
        metrics.record("b", "failure", error_code="x")

        snap = metrics.snapshot()
        assert snap["a"]["success"] == 1
        assert snap["b"]["failures"] == 1
        assert snap["b"]["last_error"] == "x"


class TestServicioConBreaker:
    def test_bloqueo_repetido_abre_breaker_y_falla_rapido(self) -> None:
        blocked = _Blocked()
        svc = YouTubeService(cache=None, providers=[blocked])

        for _ in range(5):
            with pytest.raises(VideoBlockedOrUnavailable):
                svc.get_transcript(URL)
        assert blocked.calls == 5

        with pytest.raises(ProviderUnavailable) as exc_info:
            svc.get_transcript(URL)
        assert blocked.calls == 5  # fail fast: no llama al proveedor
        assert exc_info.value.code == "provider_unavailable"

    def test_metricas_registran_fallos(self) -> None:
        svc = YouTubeService(cache=None, providers=[_Blocked()])

        with pytest.raises(VideoBlockedOrUnavailable):
            svc.get_transcript(URL)

        snap = svc.metrics.snapshot()["blocked"]
        assert snap["calls"] == 1
        assert snap["failures"] == 1
        assert snap["last_error"] == "blocked"

    def test_exito_registra_y_no_abre(self) -> None:
        class _Ok(TranscriptProvider):
            name = "ok"

            def fetch(self, video_id: str, languages: Any) -> ProviderResult:
                return ProviderResult(
                    segments=[TranscriptSegment(0.0, 1.0, "hola")],
                    language="es", source="ok", track_type="manual",
                )

        svc = YouTubeService(cache=None, providers=[_Ok()])
        result = svc.get_transcript(URL)

        assert result.source == "ok"
        snap = svc.metrics.snapshot()["ok"]
        assert snap["success"] == 1
        assert svc.breakers["ok"].state == STATE_CLOSED

    def test_breaker_desactivable(self) -> None:
        blocked = _Blocked()
        svc = YouTubeService(
            cache=None, providers=[blocked], enable_breaker=False,
        )

        for _ in range(6):
            with pytest.raises(VideoBlockedOrUnavailable):
                svc.get_transcript(URL)
        assert blocked.calls == 6  # sin fail fast

    def test_breakers_por_defecto_uno_por_proveedor(self) -> None:
        svc = YouTubeService(cache=None)
        assert set(svc.breakers) == {"youtube_captions", "yt_dlp_subtitles"}
        assert all(b.state == STATE_CLOSED for b in svc.breakers.values())


class TestWorkerConBreaker:
    def test_breaker_abierto_falla_rapido_reintentable(
        self, tmp_path: Path,
    ) -> None:
        with JobStore(db_path=tmp_path / "j.db") as jobs, \
                TranscriptCache(db_path=tmp_path / "c.db") as cache:
            breaker = CircuitBreaker("faster_whisper", failure_threshold=1)
            breaker.record_failure()
            assert breaker.state == STATE_OPEN
            worker = AsrWorker(jobs=jobs, cache=cache, breaker=breaker)

            job = jobs.create_or_get(VIDEO_ID, ["es"])
            assert job is not None
            updated = worker.run_once()

            assert updated is not None
            assert updated["status"] == "pending"  # reintentable, no terminal
            assert updated["error_code"] == "blocked"

    def test_exito_registra_metricas(self, tmp_path: Path) -> None:
        class _Dl:
            def __init__(self, base: Path) -> None:
                self.base = base

            def download(self, video_id: str) -> AudioDownloadResult:
                work = self.base / f"{TEMP_PREFIX}x"
                work.mkdir(parents=True, exist_ok=True)
                path = work / "a.wav"
                path.write_bytes(b"RIFF0000WAVE")
                return AudioDownloadResult(
                    video_id=video_id, path=path, work_dir=work,
                    ext="wav", duration=19.0,
                )

            def cleanup(self, result: AudioDownloadResult) -> None:
                shutil.rmtree(result.work_dir, ignore_errors=True)

        class _Tr:
            def transcribe(self, path: Any, language: Any = None) -> AsrResult:
                return AsrResult(
                    language="es",
                    segments=[{"start": 0.0, "end": 1.0, "text": "hola"}],
                )

        with JobStore(db_path=tmp_path / "j.db") as jobs, \
                TranscriptCache(db_path=tmp_path / "c.db") as cache:
            metrics = ProviderMetrics()
            breaker = CircuitBreaker("faster_whisper", failure_threshold=1)
            worker = AsrWorker(
                jobs=jobs, cache=cache, downloader=_Dl(tmp_path),
                transcriber=_Tr(), breaker=breaker, metrics=metrics,
            )
            jobs.create_or_get(VIDEO_ID, ["es"])
            updated = worker.run_once()

            assert updated is not None
            assert updated["status"] == "completed"
            snap = metrics.snapshot()["faster_whisper"]
            assert snap["success"] == 1
            assert breaker.state == STATE_CLOSED

    def test_sin_breaker_comportamiento_fase2(
        self, tmp_path: Path,
    ) -> None:
        with JobStore(db_path=tmp_path / "j.db") as jobs, \
                TranscriptCache(db_path=tmp_path / "c.db") as cache:
            worker = AsrWorker(jobs=jobs, cache=cache)
            assert worker.breaker is None
            assert worker.metrics is None

    def test_error_generico_cuenta_como_fallo(self) -> None:
        breaker, _ = _breaker()

        def _boom() -> None:
            raise TranscriptError("bug")

        with pytest.raises(TranscriptError):
            breaker.call(_boom)
        assert breaker.failure_count == 1
