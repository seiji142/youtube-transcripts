"""Tests de la interfaz TranscriptProvider (Fase 4 E1, sin red)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from youtube_transcript_api import RequestBlocked

from services.youtube_cache import TranscriptCache
from services.youtube_errors import (
    AsrFailed,
    DurationExceeded,
    NoCaptionsAvailable,
    TranscriptError,
    VideoBlockedOrUnavailable,
)
from services.youtube_providers import (
    ExternalAsrProvider,
    FasterWhisperProvider,
    ProviderResult,
    TranscriptProvider,
    TranscriptSegment,
    YtDlpSubtitleProvider,
    YouTubeTranscriptApiProvider,
    default_providers,
)
from services.youtube_rate_limit import RateLimiter
from services.youtube_service import YouTubeService

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def _no_rate_limit_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los unitarios no deben esperar el RateLimiter real."""
    monkeypatch.setattr(RateLimiter, "acquire", lambda self: 0.0)


def _snippet(start: float, duration: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, duration=duration, text=text)


class _FakeFetched:
    def __init__(self, snippets: list[SimpleNamespace], lang: str = "es") -> None:
        self._snippets = snippets
        self.language_code = lang

    def __iter__(self):  # noqa: ANN201
        return iter(self._snippets)


class _FakeTranscript:
    def __init__(self, snippets: list[SimpleNamespace], lang: str = "es") -> None:
        self._snippets = snippets
        self.language_code = lang

    def fetch(self) -> _FakeFetched:
        return _FakeFetched(self._snippets, self.language_code)


class _FakeTranscriptList:
    def __init__(self, manual: dict | None = None) -> None:
        self._manually_created_transcripts = manual or {}
        self._generated_transcripts = {}


class _FakeApi:
    def __init__(self, transcript_list: Any) -> None:
        self._list = transcript_list

    def list(self, video_id: str) -> Any:
        if isinstance(self._list, Exception):
            raise self._list
        return self._list


class _FakeSubtitles:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls = 0

    def fetch(self, video_id: str, languages: Any) -> Any:
        self.calls += 1
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeDownloader:
    def __init__(self, duration: float | None = 19.0) -> None:
        self._duration = duration
        self.cleaned: list[Any] = []

    def download(self, video_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            path=Path("fake.wav"), duration=self._duration, work_dir=Path("."),
        )

    def cleanup(self, result: Any) -> None:
        self.cleaned.append(result)


class _FakeTranscriber:
    def __init__(self, segments: list[dict] | None = None) -> None:
        self._segments = (
            segments
            if segments is not None
            else [{"start": 0.0, "end": 1.0, "text": "hola asr"}]
        )

    def transcribe(self, path: Any, language: Any = None) -> SimpleNamespace:
        return SimpleNamespace(segments=self._segments, language="es")


class _EmptyProvider(TranscriptProvider):
    name = "empty"

    def fetch(self, video_id: str, languages: Any) -> ProviderResult:
        raise NoCaptionsAvailable("vacío", video_id=video_id)


class _OkProvider(TranscriptProvider):
    name = "ok"

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls = 0

    def fetch(self, video_id: str, languages: Any) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            segments=[TranscriptSegment(0.0, 1.0, "hola")],
            language="es", source="ok", track_type="manual",
        )


class TestProviderResult:
    def test_duration_seconds_es_max_de_ends(self) -> None:
        result = ProviderResult(
            segments=[TranscriptSegment(0.0, 5.0, "a"), TranscriptSegment(5.0, 12.5, "b")],
        )
        assert result.duration_seconds == 12.5

    def test_duration_vacia_es_cero(self) -> None:
        assert ProviderResult().duration_seconds == 0.0

    def test_interfaz_abstracta_no_instanciable(self) -> None:
        with pytest.raises(TypeError):
            TranscriptProvider()  # type: ignore[abstract]


class TestCaptionsProvider:
    def test_happy_path_devuelve_segmentos(self) -> None:
        api = _FakeApi(_FakeTranscriptList(
            manual={"es": _FakeTranscript([_snippet(0.0, 2.0, "hola ")])},
        ))
        provider = YouTubeTranscriptApiProvider(api=api)  # type: ignore[arg-type]

        result = provider.fetch(VIDEO_ID, ["es"])

        assert result.source == "youtube_captions"
        assert result.track_type == "manual"
        assert result.language == "es"
        assert [(s.start, s.end, s.text) for s in result.segments] == [(0.0, 2.0, "hola")]

    def test_nombre_del_proveedor(self) -> None:
        provider = YouTubeTranscriptApiProvider(api=_FakeApi(_FakeTranscriptList()))
        assert provider.name == "youtube_captions"
        assert provider.enabled is True

    def test_sin_pistas_lanza_no_captions(self) -> None:
        provider = YouTubeTranscriptApiProvider(api=_FakeApi(_FakeTranscriptList()))

        with pytest.raises(NoCaptionsAvailable):
            provider.fetch(VIDEO_ID, ["es"])

    def test_bloqueo_se_mapea_y_propaga(self) -> None:
        provider = YouTubeTranscriptApiProvider(api=_FakeApi(RequestBlocked("boom")))

        with pytest.raises(VideoBlockedOrUnavailable):
            provider.fetch(VIDEO_ID, ["es"])

    def test_rate_limiter_se_invoca(self, tmp_path: Path) -> None:
        calls: list[str] = []

        class _RL:
            def acquire(self) -> float:
                calls.append("x")
                return 0.0

        provider = YouTubeTranscriptApiProvider(
            api=_FakeApi(_FakeTranscriptList(
                manual={"es": _FakeTranscript([_snippet(0.0, 1.0, "hola")])},
            )),
            rate_limiter=_RL(),  # type: ignore[arg-type]
        )
        provider.fetch(VIDEO_ID, ["es"])
        assert calls == ["x"]


class TestSubtitlesProvider:
    def test_happy_path(self) -> None:
        subs = _FakeSubtitles(SimpleNamespace(
            segments=[{"start": 1.0, "end": 2.0, "text": "sub"}],
            language="es", source="yt_dlp_subtitles", track_type="auto",
        ))
        provider = YtDlpSubtitleProvider(subtitles=subs)  # type: ignore[arg-type]

        result = provider.fetch(VIDEO_ID, ["es"])

        assert result.source == "yt_dlp_subtitles"
        assert result.track_type == "auto"
        assert result.segments[0].text == "sub"
        assert subs.calls == 1

    def test_error_de_dominio_propaga(self) -> None:
        subs = _FakeSubtitles(NoCaptionsAvailable("nada", video_id=VIDEO_ID))
        provider = YtDlpSubtitleProvider(subtitles=subs)  # type: ignore[arg-type]

        with pytest.raises(NoCaptionsAvailable):
            provider.fetch(VIDEO_ID, ["es"])


class TestAsrProvider:
    def test_happy_path_con_fakes(self) -> None:
        downloader = _FakeDownloader(duration=19.0)
        provider = FasterWhisperProvider(
            downloader=downloader, transcriber=_FakeTranscriber(),
        )

        result = provider.fetch(VIDEO_ID, ["es"])

        assert result.source == "faster_whisper"
        assert result.track_type == "asr"
        assert result.language == "es"
        assert result.segments[0].text == "hola asr"
        assert len(downloader.cleaned) == 1  # cleanup siempre

    def test_duracion_excedida_y_limpia(self) -> None:
        downloader = _FakeDownloader(duration=99999.0)
        provider = FasterWhisperProvider(
            downloader=downloader, transcriber=_FakeTranscriber(),
            max_duration_seconds=7200,
        )

        with pytest.raises(DurationExceeded):
            provider.fetch(VIDEO_ID, ["es"])
        assert len(downloader.cleaned) == 1

    def test_sin_segmentos_lanza_asr_failed(self) -> None:
        provider = FasterWhisperProvider(
            downloader=_FakeDownloader(), transcriber=_FakeTranscriber(segments=[]),
        )

        with pytest.raises(AsrFailed):
            provider.fetch(VIDEO_ID, ["es"])


class TestExternalProvider:
    def test_deshabilitado_por_defecto(self) -> None:
        provider = ExternalAsrProvider()
        assert provider.enabled is False
        assert provider.name == "external_asr"

    def test_fetch_lanza_error_configurable(self) -> None:
        provider = ExternalAsrProvider(enabled=True)

        with pytest.raises(TranscriptError):
            provider.fetch(VIDEO_ID, ["es"])


class TestPipelineServicio:
    def test_orden_primero_que_gana(self) -> None:
        empty = _EmptyProvider()
        ok = _OkProvider()
        svc = YouTubeService(cache=None, providers=[empty, ok])

        result = svc.get_transcript(
            f"https://www.youtube.com/watch?v={VIDEO_ID}",
        )

        assert result.source == "ok"
        assert ok.calls == 1

    def test_proveedor_deshabilitado_se_omite(self) -> None:
        ok = _OkProvider(enabled=False)
        svc = YouTubeService(cache=None, providers=[ok])

        with pytest.raises(NoCaptionsAvailable):
            svc.get_transcript(
                f"https://www.youtube.com/watch?v={VIDEO_ID}",
            )
        assert ok.calls == 0

    def test_sin_proveedores_con_material_lanza_no_captions(self) -> None:
        svc = YouTubeService(cache=None, providers=[_EmptyProvider()])

        with pytest.raises(NoCaptionsAvailable):
            svc.get_transcript(
                f"https://www.youtube.com/watch?v={VIDEO_ID}",
            )

    def test_error_de_bloqueo_no_pasa_al_siguiente(self) -> None:
        class _Blocked(TranscriptProvider):
            name = "blocked"

            def fetch(self, video_id: str, languages: Any) -> ProviderResult:
                raise VideoBlockedOrUnavailable("bloqueo", video_id=video_id)

        ok = _OkProvider()
        svc = YouTubeService(cache=None, providers=[_Blocked(), ok])

        with pytest.raises(VideoBlockedOrUnavailable):
            svc.get_transcript(
                f"https://www.youtube.com/watch?v={VIDEO_ID}",
            )
        assert ok.calls == 0

    def test_default_providers_usa_componentes_inyectados(self) -> None:
        api = _FakeApi(_FakeTranscriptList())
        subs = _FakeSubtitles(NoCaptionsAvailable("nada", video_id=VIDEO_ID))

        svc = YouTubeService(cache=None, api=api, subtitles=subs)  # type: ignore[arg-type]

        assert len(svc.providers) == 2
        assert svc.providers[0].api is api
        assert svc.providers[1].subtitles is subs
        assert svc.providers[1].enabled is True

    def test_enable_subtitle_fallback_desactiva_proveedor(self) -> None:
        svc = YouTubeService(cache=None, enable_subtitle_fallback=False)

        assert svc.providers[1].enabled is False
        assert svc._enable_subtitle_fallback is False

    def test_resultado_se_cachea_con_source_del_proveedor(
        self, tmp_path: Path,
    ) -> None:
        with TranscriptCache(db_path=tmp_path / "c.db") as cache:
            svc = YouTubeService(cache=cache, providers=[_OkProvider()])
            result = svc.get_transcript(
                f"https://www.youtube.com/watch?v={VIDEO_ID}",
            )

            assert result.source == "ok"
            entry = cache.get(VIDEO_ID, "es+en", "manual")
            assert entry is not None
            assert entry["source"] == "ok"


class TestDefaultProviders:
    def test_pipeline_sincrono_sin_asr(self) -> None:
        providers = default_providers(enable_subtitle_fallback=True)

        assert [p.name for p in providers] == [
            "youtube_captions", "yt_dlp_subtitles",
        ]

    def test_tipos(self) -> None:
        providers = default_providers()
        assert isinstance(providers[0], YouTubeTranscriptApiProvider)
        assert isinstance(providers[1], YtDlpSubtitleProvider)
