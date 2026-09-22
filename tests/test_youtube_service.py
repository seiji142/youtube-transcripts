"""Tests unitarios del orquestador (sin red: API mockeada)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from youtube_transcript_api import NoTranscriptFound, RequestBlocked

from services.youtube_cache import TranscriptCache
from services.youtube_errors import (
    DurationExceeded,
    InvalidYouTubeUrl,
    NoCaptionsAvailable,
    VideoBlockedOrUnavailable,
)
from services.youtube_rate_limit import RateLimiter
from services.youtube_service import (
    TranscriptResult,
    TranscriptSegment,
    YouTubeService,
)

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIDEO_ID = "dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def _no_rate_limit_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los unitarios no deben esperar el RateLimiter real."""
    monkeypatch.setattr(RateLimiter, "acquire", lambda self: 0.0)


def _snippet(start: float, duration: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, duration=duration, text=text)


def _fetched(snippets: list[SimpleNamespace], lang: str = "es") -> SimpleNamespace:
    return SimpleNamespace(
        snippets=snippets,
        video_id=VIDEO_ID,
        language=lang,
        language_code=lang,
        is_generated=False,
        __iter__=lambda self: iter(snippets),
    )


class FakeFetched:
    def __init__(self, snippets: list[SimpleNamespace], lang: str = "es") -> None:
        self._snippets = snippets
        self.language_code = lang
        self.language = lang
        self.is_generated = False

    def __iter__(self):  # noqa: ANN201
        return iter(self._snippets)


class FakeTranscript:
    def __init__(self, snippets: list[SimpleNamespace], lang: str = "es",
                 is_generated: bool = False) -> None:
        self._snippets = snippets
        self.language_code = lang
        self.language = lang
        self.is_generated = is_generated

    def fetch(self, preserve_formatting: bool = False) -> FakeFetched:
        return FakeFetched(self._snippets, self.language_code)


class FakeTranscriptList:
    def __init__(
        self,
        manual: dict[str, FakeTranscript] | None = None,
        generated: dict[str, FakeTranscript] | None = None,
    ) -> None:
        self._manually_created_transcripts = manual or {}
        self._generated_transcripts = generated or {}


class FakeApi:
    def __init__(self, transcript_list: FakeTranscriptList | Exception) -> None:
        self._list = transcript_list

    def list(self, video_id: str) -> FakeTranscriptList:
        if isinstance(self._list, Exception):
            raise self._list
        return self._list


DEFAULT_SNIPPETS = [
    _snippet(0.0, 2.0, "hola "),
    _snippet(2.0, 3.0, "mundo"),
]


@pytest.fixture
def cache(tmp_path: Path) -> TranscriptCache:
    with TranscriptCache(db_path=tmp_path / "svc.db") as c:
        yield c


class TestTranscriptResult:
    def test_text_junta_segmentos(self) -> None:
        r = TranscriptResult(
            video_id=VIDEO_ID, language="es", source="youtube_captions",
            track_type="manual",
            segments=[
                TranscriptSegment(0.0, 2.0, "hola"),
                TranscriptSegment(2.0, 4.0, "mundo"),
            ],
        )
        assert r.text == "hola\nmundo"

    def test_duration_seconds_es_max_de_ends(self) -> None:
        r = TranscriptResult(
            video_id=VIDEO_ID, language="es", source="x", track_type="manual",
            segments=[TranscriptSegment(0, 5.0, "a"), TranscriptSegment(5.0, 12.5, "b")],
        )
        assert r.duration_seconds == 12.5

    def test_to_dict_completo(self) -> None:
        r = TranscriptResult(
            video_id=VIDEO_ID, language="es", source="youtube_captions",
            track_type="manual",
            segments=[TranscriptSegment(0.0, 2.0, "hola")],
        )
        d = r.to_dict()
        assert d["status"] == "completed"
        assert d["video_id"] == VIDEO_ID
        assert d["text"] == "hola"
        assert d["segments"] == [{"start": 0.0, "end": 2.0, "text": "hola"}]

    def test_to_dict_sin_timestamps(self) -> None:
        r = TranscriptResult(
            video_id=VIDEO_ID, language="es", source="x", track_type="auto",
            segments=[TranscriptSegment(0.0, 1.0, "x")],
        )
        d = r.to_dict(include_timestamps=False)
        assert "segments" not in d
        assert d["text"] == "x"


class TestSeleccionPistas:
    def test_prefiere_manual_sobre_auto(self) -> None:
        manual = FakeTranscript(DEFAULT_SNIPPETS, "es", is_generated=False)
        auto = FakeTranscript(DEFAULT_SNIPPETS, "es", is_generated=True)
        api = FakeApi(FakeTranscriptList(manual={"es": manual}, generated={"es": auto}))
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        result = svc.get_transcript(VALID_URL)
        assert result.track_type == "manual"
        assert result.language == "es"

    def test_prefiere_idioma_pedido(self) -> None:
        manual_en = FakeTranscript(DEFAULT_SNIPPETS, "en")
        manual_es = FakeTranscript(DEFAULT_SNIPPETS, "es")
        api = FakeApi(FakeTranscriptList(manual={"en": manual_en, "es": manual_es}))
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        result = svc.get_transcript(VALID_URL, languages=["es", "en"])
        assert result.language == "es"

    def test_fallback_a_auto_si_no_hay_manual(self) -> None:
        auto = FakeTranscript(DEFAULT_SNIPPETS, "es", is_generated=True)
        api = FakeApi(FakeTranscriptList(generated={"es": auto}))
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        result = svc.get_transcript(VALID_URL)
        assert result.track_type == "auto"

    def test_variante_por_prefijo_es419(self) -> None:
        manual = FakeTranscript(DEFAULT_SNIPPETS, "es-419")
        api = FakeApi(FakeTranscriptList(manual={"es-419": manual}))
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        result = svc.get_transcript(VALID_URL, languages=["es"])
        assert result.language == "es-419"

    def test_sin_pistas_lanza_no_captions(self) -> None:
        api = FakeApi(FakeTranscriptList())
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        with pytest.raises(NoCaptionsAvailable) as exc_info:
            svc.get_transcript(VALID_URL)
        assert exc_info.value.code == "no_captions"


class TestErroresMapeados:
    def test_url_invalida(self) -> None:
        svc = YouTubeService(api=FakeApi(FakeTranscriptList()))  # type: ignore[arg-type]
        with pytest.raises(InvalidYouTubeUrl):
            svc.get_transcript("https://evil.com/watch?v=dQw4w9WgXcQ")

    def test_request_blocked_mapea_a_blocked(self) -> None:
        api = FakeApi(RequestBlocked(VIDEO_ID))
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        with pytest.raises(VideoBlockedOrUnavailable) as exc_info:
            svc.get_transcript(VALID_URL)
        assert exc_info.value.code == "blocked"

    def test_no_transcript_found_mapea_a_no_captions(self) -> None:
        api = FakeApi(NoTranscriptFound(VIDEO_ID, "es", ["es"]))
        svc = YouTubeService(api=api)  # type: ignore[arg-type]
        with pytest.raises(NoCaptionsAvailable) as exc_info:
            svc.get_transcript(VALID_URL)
        assert exc_info.value.code == "no_captions"


class TestDuracion:
    def test_video_demasiado_largo(self) -> None:
        long_snippets = [_snippet(0.0, 7300.0, "charla larga")]
        tr = FakeTranscript(long_snippets, "es")
        api = FakeApi(FakeTranscriptList(manual={"es": tr}))
        svc = YouTubeService(api=api, max_duration_seconds=7200)  # type: ignore[arg-type]
        with pytest.raises(DurationExceeded) as exc_info:
            svc.get_transcript(VALID_URL)
        assert exc_info.value.code == "duration_exceeded"

    def test_video_dentro_de_limite(self) -> None:
        tr = FakeTranscript(DEFAULT_SNIPPETS, "es")
        api = FakeApi(FakeTranscriptList(manual={"es": tr}))
        svc = YouTubeService(api=api, max_duration_seconds=7200)  # type: ignore[arg-type]
        result = svc.get_transcript(VALID_URL)
        assert result.duration_seconds == 5.0


class TestCacheIntegracion:
    def test_primer_llamada_miss_segunda_hit(self, cache: TranscriptCache) -> None:
        tr = FakeTranscript(DEFAULT_SNIPPETS, "es")
        api = FakeApi(FakeTranscriptList(manual={"es": tr}))
        svc = YouTubeService(cache=cache, api=api)  # type: ignore[arg-type]

        first = svc.get_transcript(VALID_URL, languages=["es", "en"])
        assert first.track_type == "manual"
        assert first.segments[0].text == "hola"

        # segunda llamada: la API no debería tocar la red (se usa cache)
        cache_api = FakeApi(AssertionError("no debe llamar a la API"))
        svc2 = YouTubeService(cache=cache, api=cache_api)  # type: ignore[arg-type]
        second = svc2.get_transcript(VALID_URL, languages=["es", "en"])
        assert second.segments == first.segments
        assert second.language == first.language

    def test_cache_almacena_en_db(self, cache: TranscriptCache) -> None:
        tr = FakeTranscript(DEFAULT_SNIPPETS, "es")
        api = FakeApi(FakeTranscriptList(manual={"es": tr}))
        svc = YouTubeService(cache=cache, api=api)  # type: ignore[arg-type]
        svc.get_transcript(VALID_URL, languages=["es", "en"])
        entry = cache.get(VIDEO_ID, "es+en", "manual")
        assert entry is not None
        assert entry["segments"][0]["text"] == "hola"


class TestRateLimiterIntegracion:
    def test_rate_limiter_llamado_en_cache_miss(
        self, cache: TranscriptCache,
    ) -> None:
        tr = FakeTranscript(DEFAULT_SNIPPETS, "es")
        api = FakeApi(FakeTranscriptList(manual={"es": tr}))
        rl = RateLimiter(enabled=True, min_interval_seconds=0.0)
        calls: list[float] = []
        original = rl.acquire

        def spy() -> float:
            result = original()
            calls.append(result)
            return result

        rl.acquire = spy  # type: ignore[method-assign]
        svc = YouTubeService(cache=cache, api=api, rate_limiter=rl)  # type: ignore[arg-type]
        svc.get_transcript(VALID_URL, languages=["es", "en"])
        assert len(calls) == 1  # cache miss → 1 acquire

        # segundo service con misma cache: hit → NO debe llamar acquire
        rl2 = RateLimiter(enabled=True, min_interval_seconds=0.0)
        calls2: list[float] = []
        original2 = rl2.acquire

        def spy2() -> float:
            result = original2()
            calls2.append(result)
            return result

        rl2.acquire = spy2  # type: ignore[method-assign]
        svc2 = YouTubeService(cache=cache, api=api, rate_limiter=rl2)  # type: ignore[arg-type]
        svc2.get_transcript(VALID_URL, languages=["es", "en"])
        assert len(calls2) == 0  # cache hit → 0 acquire

    def test_rate_limiter_deshabilitable(self, cache: TranscriptCache) -> None:
        tr = FakeTranscript(DEFAULT_SNIPPETS, "es")
        api = FakeApi(FakeTranscriptList(manual={"es": tr}))
        rl = RateLimiter(enabled=False, min_interval_seconds=99.0)
        svc = YouTubeService(cache=cache, api=api, rate_limiter=rl)  # type: ignore[arg-type]
        # enabled=False no debe esperar (99s serían obvios si esperara)
        result = svc.get_transcript(VALID_URL, languages=["es", "en"])
        assert result.segments
