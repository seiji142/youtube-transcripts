"""Tests de integración con red real de YouTube.

Se ejecutan solo con ``pytest -m integration`` (fuera de la suite default).
Videos públicos fijados y verificados el 21/09/2026.

Incluye reintentos con backoff ante HTTP 429 / IP bloqueada (riesgo
previsto en docs/TAREAS_YOUTUBE.md seccion 4).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.youtube_cache import TranscriptCache
from services.youtube_errors import NoCaptionsAvailable, VideoBlockedOrUnavailable
from services.youtube_service import TranscriptResult, YouTubeService

# Videos con captions en español (audio original puede ser otro idioma)
ES_VIDEOS = [
    "https://www.youtube.com/watch?v=gdZLi9oWNZg",  # BTS Dynamite (captions ES)
    "https://www.youtube.com/watch?v=09R8_2nJtjg",  # Maroon 5 Sugar (captions ES)
    "https://www.youtube.com/watch?v=5MgBikgcWnY",  # Josh Kaufman TEDxCSU (captions ES)
]

# Videos en inglés (idioma original EN)
EN_VIDEOS = [
    "https://www.youtube.com/watch?v=8S0FDjFBj8o",   # Will Stephen TEDx
    "https://www.youtube.com/watch?v=arj7oStGLkU",   # Tim Urban TED
    "https://www.youtube.com/watch?v=aircAruvnKk",   # 3Blue1Brown neural nets
]

# Video sin captions (captions deshabilitadas por el creador)
NO_CAPTIONS_VIDEO = "https://www.youtube.com/watch?v=ScMzIvxBSi4"

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 5.0


@pytest.fixture
def service(tmp_path: Path) -> YouTubeService:
    cache = TranscriptCache(db_path=tmp_path / "integration.db")
    return YouTubeService(cache=cache)


def _fetch_with_backoff(
    service: YouTubeService,
    url: str,
    languages: list[str] | None = None,
) -> TranscriptResult:
    """Llama get_transcript reintentando ante bloqueo 429 con backoff exponencial.

    Si el bloqueo persiste, hace ``pytest.skip`` (razón ambiental: rate limit
    de YouTube, no un bug del código).
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = service.get_transcript(url, languages=languages)
            if attempt > 0:
                time.sleep(1.0)
            return result
        except VideoBlockedOrUnavailable as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
                time.sleep(wait)
            else:
                pytest.skip(f"YouTube bloqueó la IP (rate limit): {exc.message}")
    raise AssertionError("unreachable")


def _assert_valid_result(result: TranscriptResult, lang_prefix: str) -> None:
    assert result.language is not None
    assert result.language.startswith(lang_prefix)
    assert result.source == "youtube_captions"
    assert result.track_type in {"manual", "auto"}
    assert result.text.strip()
    assert len(result.segments) > 0
    for seg in result.segments:
        assert seg.start >= 0
        assert seg.end >= seg.start
        assert seg.text is not None
    assert result.duration_seconds > 0
    assert result.duration_seconds <= 7200


@pytest.mark.integration
class TestCaptionsES:
    @pytest.mark.parametrize("url", ES_VIDEOS)
    def test_video_es_devuelve_texto_y_timestamps(
        self, service: YouTubeService, url: str,
    ) -> None:
        result = _fetch_with_backoff(service, url)
        _assert_valid_result(result, "es")


@pytest.mark.integration
class TestCaptionsEN:
    @pytest.mark.parametrize("url", EN_VIDEOS)
    def test_video_en_devuelve_texto_y_timestamps(
        self, service: YouTubeService, url: str,
    ) -> None:
        result = _fetch_with_backoff(service, url, languages=["en"])
        _assert_valid_result(result, "en")


@pytest.mark.integration
class TestSinCaptions:
    def test_video_sin_captions_lanza_no_captions(
        self, service: YouTubeService,
    ) -> None:
        with pytest.raises(NoCaptionsAvailable) as exc_info:
            _fetch_with_backoff(service, NO_CAPTIONS_VIDEO)
        assert exc_info.value.code == "no_captions"


@pytest.mark.integration
class TestCacheIntegracion:
    def test_segunda_llamada_usa_cache(self, service: YouTubeService) -> None:
        url = ES_VIDEOS[0]
        first = _fetch_with_backoff(service, url)
        assert first.segments

        # segunda llamada: debe salir de la cache (misma DB), sin tocar la API
        assert service.cache is not None
        entry = service.cache.get(
            first.video_id, "es+en", first.track_type,
        )
        assert entry is not None
        assert entry["segments"]

        # tercer servicio con la misma cache: no debe re-fetchear
        second = YouTubeService(cache=service.cache)
        result = second.get_transcript(url)
        assert result.text == first.text
        assert result.language == first.language
