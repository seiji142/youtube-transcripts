"""Tests del servidor MCP (registro de tools, sin red)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import mcp_server
from mcp_server import (
    mcp,
    youtube_transcript,
    youtube_transcript_read,
    youtube_transcript_status,
)
from services.youtube_cache import TranscriptCache
from services.youtube_errors import InvalidYouTubeUrl, NoCaptionsAvailable
from services.youtube_jobs import JobStore

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIDEO_ID = "dQw4w9WgXcQ"


@pytest.fixture
def jobs_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    store = JobStore(db_path=tmp_path / "jobs.db")
    monkeypatch.setattr(mcp_server, "_jobs", store)
    yield store
    store.close()


@pytest.fixture
def cache_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TranscriptCache:
    cache = TranscriptCache(db_path=tmp_path / "cache.db")
    monkeypatch.setattr(mcp_server, "_cache", cache)
    yield cache
    cache.close()


def _mock_no_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: Any, **kwargs: Any) -> None:
        raise NoCaptionsAvailable("sin captions", video_id=VIDEO_ID)

    monkeypatch.setattr(mcp_server._service, "get_transcript", _raise)


class TestRegistroTools:
    def test_tool_registrada(self) -> None:
        async def _names() -> list[str]:
            tools = await mcp.list_tools()
            return [t.name for t in tools]

        names = asyncio.run(_names())
        assert "youtube_transcript" in names

    def test_tools_fase2_registradas(self) -> None:
        async def _names() -> list[str]:
            tools = await mcp.list_tools()
            return [t.name for t in tools]

        names = asyncio.run(_names())
        assert "youtube_transcript_status" in names
        assert "youtube_transcript_read" in names

    def test_service_usa_cache(self) -> None:
        assert mcp_server._service is not None
        assert mcp_server._service.cache is mcp_server._cache

    def test_service_tiene_fallback_subtitles(self) -> None:
        assert mcp_server._service._enable_subtitle_fallback is True
        assert mcp_server._service._subtitles is not None

    def test_worker_comparte_rate_limiter(self) -> None:
        assert mcp_server._worker.rate_limiter is mcp_server._service.rate_limiter
        assert mcp_server._worker.jobs is mcp_server._jobs


class TestYoutubeTranscriptTool:
    def test_url_invalida_devuelve_error_estructurado(self) -> None:
        payload = youtube_transcript("https://evil.com/watch?v=dQw4w9WgXcQ")
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_url"
        assert "message" in payload

    def test_url_vacia_devuelve_error(self) -> None:
        payload = youtube_transcript("")
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_url"

    def test_payload_error_es_dict(self) -> None:
        payload: dict[str, Any] = youtube_transcript("ftp://x/y")
        assert isinstance(payload, dict)
        assert payload["code"] == "invalid_url"

    def test_lanzamiento_directo_de_dominio(self) -> None:
        """La tool captura TranscriptError y no propaga excepciones."""
        with pytest.raises(InvalidYouTubeUrl):
            # el servicio sí lanza; la tool lo atrapa — aquí probamos el servicio
            mcp_server._service.get_transcript("not-a-url")

    def test_fallback_subtitles_inyectable_en_service(self) -> None:
        """YouTubeService acepta enable_subtitle_fallback para tests sin red."""
        from services.youtube_service import YouTubeService
        svc = YouTubeService(enable_subtitle_fallback=False)
        assert svc._enable_subtitle_fallback is False


class TestEnqueueAsr:
    def test_no_captions_devuelve_processing_con_job_id(
        self, jobs_store: JobStore, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_no_captions(monkeypatch)

        payload = youtube_transcript(VALID_URL)

        assert payload["status"] == "processing"
        assert payload["job_id"] == f"{VIDEO_ID}:es+en"
        assert payload["video_id"] == VIDEO_ID
        job = jobs_store.get(job_id=payload["job_id"])
        assert job is not None
        assert job["status"] == "pending"

    def test_encola_idempotente(
        self, jobs_store: JobStore, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_no_captions(monkeypatch)

        first = youtube_transcript(VALID_URL)
        second = youtube_transcript(VALID_URL)

        assert first["job_id"] == second["job_id"]
        assert jobs_store.get(video_id=VIDEO_ID) is not None

    def test_job_completado_devuelve_transcripcion_desde_cache(
        self, jobs_store: JobStore, cache_store: TranscriptCache,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_no_captions(monkeypatch)
        job = jobs_store.create_or_get(VIDEO_ID, ["es", "en"])
        claimed = jobs_store.claim_next()
        assert claimed is not None
        jobs_store.mark_completed(claimed["job_id"])
        cache_store.set(
            VIDEO_ID, "es+en", "asr",
            segments=[{"start": 0.0, "end": 1.0, "text": "hola asr"}],
            language_code="es", source="faster_whisper",
        )

        payload = youtube_transcript(VALID_URL)

        assert payload["status"] == "completed"
        assert payload["text"] == "hola asr"
        assert payload["source"] == "faster_whisper"
        assert payload["track_type"] == "asr"
        assert jobs_store.get(job_id=job["job_id"])["status"] == "completed"

    def test_job_completado_sin_cache_se_reencola(
        self, jobs_store: JobStore, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_no_captions(monkeypatch)
        jobs_store.create_or_get(VIDEO_ID, ["es", "en"])
        claimed = jobs_store.claim_next()
        assert claimed is not None
        jobs_store.mark_completed(claimed["job_id"])

        payload = youtube_transcript(VALID_URL)

        assert payload["status"] == "processing"
        job = jobs_store.get(job_id=claimed["job_id"])
        assert job is not None
        assert job["status"] == "pending"
        assert job["attempts"] == 0


class TestStatusTool:
    def test_sin_args_da_invalid_request(self) -> None:
        payload = youtube_transcript_status()
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_request"

    def test_job_inexistente(self) -> None:
        payload = youtube_transcript_status(job_id="nope:es")
        assert payload["status"] == "error"
        assert payload["code"] == "job_not_found"

    def test_url_invalida_devuelve_error_de_url(self) -> None:
        payload = youtube_transcript_status(url="https://evil.com/watch?v=x")
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_url"

    def test_job_pending_es_processing(
        self, jobs_store: JobStore,
    ) -> None:
        jobs_store.create_or_get(VIDEO_ID, ["es", "en"])

        payload = youtube_transcript_status(url=VALID_URL)

        assert payload["status"] == "processing"
        assert payload["job_status"] == "pending"
        assert payload["job_id"] == f"{VIDEO_ID}:es+en"
        assert payload["attempts"] == 0

    def test_job_failed_devuelve_error_con_codigo(
        self, jobs_store: JobStore,
    ) -> None:
        jobs_store.create_or_get(VIDEO_ID, ["es", "en"])
        claimed = jobs_store.claim_next()
        assert claimed is not None
        jobs_store.mark_failed(
            claimed["job_id"], "duration_exceeded", "video >2h", terminal=True,
        )

        payload = youtube_transcript_status(job_id=claimed["job_id"])

        assert payload["status"] == "error"
        assert payload["code"] == "duration_exceeded"
        assert payload["message"] == "video >2h"

    def test_job_completed_indica_tool_de_lectura(
        self, jobs_store: JobStore,
    ) -> None:
        jobs_store.create_or_get(VIDEO_ID, ["es", "en"])
        claimed = jobs_store.claim_next()
        assert claimed is not None
        jobs_store.mark_completed(claimed["job_id"])

        payload = youtube_transcript_status(job_id=claimed["job_id"])

        assert payload["status"] == "completed"
        assert payload["read_with"] == "youtube_transcript_read"


class TestReadTool:
    SEGMENTS = [
        {"start": 0.0, "end": 5.0, "text": "inicio"},
        {"start": 5.0, "end": 10.0, "text": "medio"},
        {"start": 10.0, "end": 15.0, "text": "final"},
    ]

    def _seed(self, cache: TranscriptCache) -> None:
        cache.set(
            VIDEO_ID, "es+en", "manual",
            segments=self.SEGMENTS,
            language_code="es", source="youtube_captions",
        )

    def test_sin_transcripcion_da_not_found(self, cache_store: TranscriptCache) -> None:
        payload = youtube_transcript_read(VIDEO_ID)
        assert payload["status"] == "error"
        assert payload["code"] == "not_found"

    def test_rango_en_segundos_filtra_segmentos(
        self, cache_store: TranscriptCache,
    ) -> None:
        self._seed(cache_store)

        payload = youtube_transcript_read(VIDEO_ID, start=6.0, end=9.0)

        assert payload["status"] == "completed"
        assert [s["text"] for s in payload["segments"]] == ["medio"]
        assert payload["range"] == {"start": 6.0, "end": 9.0}
        assert payload["text"] == "medio"
        assert payload["language"] == "es"

    def test_start_en_0_hasta_el_final(self, cache_store: TranscriptCache) -> None:
        self._seed(cache_store)

        payload = youtube_transcript_read(VIDEO_ID)

        assert len(payload["segments"]) == 3
        assert payload["truncated"] is False

    def test_max_chars_recorta_y_marca_truncated(
        self, cache_store: TranscriptCache,
    ) -> None:
        self._seed(cache_store)

        payload = youtube_transcript_read(VIDEO_ID, max_chars=4)

        # siempre al menos 1 segmento aunque supere el tope
        assert len(payload["segments"]) == 1
        assert payload["segments"][0]["text"] == "inicio"
        assert payload["truncated"] is True

    def test_rango_sin_segmentos_devuelve_vacio(
        self, cache_store: TranscriptCache,
    ) -> None:
        self._seed(cache_store)

        payload = youtube_transcript_read(VIDEO_ID, start=100.0)

        assert payload["status"] == "completed"
        assert payload["segments"] == []
        assert payload["text"] == ""

    def test_sin_timestamps_omite_segmentos(
        self, cache_store: TranscriptCache,
    ) -> None:
        self._seed(cache_store)

        payload = youtube_transcript_read(VIDEO_ID, include_timestamps=False)

        assert "segments" not in payload
        assert payload["text"].startswith("inicio")

    @pytest.mark.parametrize(
        ("kwargs",),
        [
            ({"start": -1.0},),
            ({"start": 5.0, "end": 5.0},),
            ({"start": 5.0, "end": 4.0},),
            ({"max_chars": 0},),
        ],
    )
    def test_ranges_invalidos(
        self, cache_store: TranscriptCache, kwargs: dict[str, Any],
    ) -> None:
        self._seed(cache_store)
        payload = youtube_transcript_read(VIDEO_ID, **kwargs)
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_range"
