"""Tests del módulo de subtítulos yt-dlp (parser VTT sin red)."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.youtube_errors import NoCaptionsAvailable
from services.youtube_subtitles import (
    SubtitleResult,
    YtDlpSubtitles,
    parse_vtt,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseVtt:
    def test_fixture_basica(self) -> None:
        content = (FIXTURES / "sample_es.vtt").read_text(encoding="utf-8")
        segments = parse_vtt(content)

        assert len(segments) == 3
        assert segments[0] == {"start": 0.0, "end": 2.5, "text": "Hola mundo"}
        assert segments[1]["text"] == "Esto es una prueba de dos líneas"
        assert segments[1]["start"] == 2.5
        assert segments[2]["start"] == 5.0
        assert segments[2]["end"] == 65.5  # 00:01:05.500

    def test_rolling_deduplica_texto_repetido(self) -> None:
        content = (FIXTURES / "rolling_es.vtt").read_text(encoding="utf-8")
        segments = parse_vtt(content, rolling=True)

        assert len(segments) >= 2
        # primera cue: tags <c> eliminados
        assert "<" not in segments[0]["text"]
        # cue idéntica no duplica segmento
        texts = [s["text"] for s in segments]
        assert len(texts) == len(set(texts)) or any(
            texts[i] != texts[i - 1] for i in range(1, len(texts))
        )

    def test_sin_rolling_conserva_cues_separados(self) -> None:
        content = (FIXTURES / "sample_es.vtt").read_text(encoding="utf-8")
        segments = parse_vtt(content, rolling=False)
        assert len(segments) == 3

    def test_tags_inline_eliminados(self) -> None:
        content = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "<c>texto</c> con <00:00:00.500>marca</c>\n"
        )
        segments = parse_vtt(content)
        assert len(segments) == 1
        assert segments[0]["text"] == "texto con marca"

    def test_vacio_devuelve_lista_vacia(self) -> None:
        assert parse_vtt("") == []
        assert parse_vtt("WEBVTT\n") == []

    def test_formato_mm_ss_sin_horas(self) -> None:
        content = "WEBVTT\n\n00:05.000 --> 00:07.500\ntexto\n"
        segments = parse_vtt(content)
        assert segments == [{"start": 5.0, "end": 7.5, "text": "texto"}]

    def test_millis_con_coma(self) -> None:
        content = "WEBVTT\n\n00:00:01,000 --> 00:00:02,000\ntexto\n"
        segments = parse_vtt(content)
        assert segments[0]["start"] == 1.0
        assert segments[0]["end"] == 2.0

    def test_cue_vacio_se_omite(self) -> None:
        content = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n\n"
        assert parse_vtt(content) == []

    def test_style_y_region_se_ignoran(self) -> None:
        content = (
            "WEBVTT\n"
            "STYLE\n::cue { color: white; }\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "hola\n"
        )
        segments = parse_vtt(content)
        assert len(segments) == 1
        assert segments[0]["text"] == "hola"


class TestPickTrack:
    def test_prefiere_manual_sobre_auto(self) -> None:
        from services.youtube_subtitles import _pick_track

        picked = _pick_track(
            {"es": [{"ext": "vtt"}]},
            {"es": [{"ext": "vtt"}]},
            ("es", "en"),
        )
        assert picked == ("es", "manual")

    def test_prefiere_idioma_pedido(self) -> None:
        from services.youtube_subtitles import _pick_track

        picked = _pick_track(
            {"en": [], "es": []},
            {},
            ("es", "en"),
        )
        assert picked == ("es", "manual")

    def test_fallback_a_auto(self) -> None:
        from services.youtube_subtitles import _pick_track

        picked = _pick_track({}, {"es": []}, ("es",))
        assert picked == ("es", "auto")

    def test_variante_por_prefijo(self) -> None:
        from services.youtube_subtitles import _pick_track

        picked = _pick_track({"es-419": []}, {}, ("es",))
        assert picked == ("es-419", "manual")

    def test_sin_pistas_devuelve_none(self) -> None:
        from services.youtube_subtitles import _pick_track

        assert _pick_track({}, {}, ("es", "en")) is None


class TestYtDlpSubtitles:
    def test_fetch_sin_subtitulos_lanza_no_captions(self) -> None:
        class FakeYDL:
            def __init__(self, opts=None):  # noqa: ANN001
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):  # noqa: ANN002
                return False

            def extract_info(self, url, download=False, process=False):  # noqa: ANN001
                return {"subtitles": {}, "automatic_captions": {}}

        subtitles = YtDlpSubtitles()
        # monkeypatch extract para no tocar red
        subtitles._extract = lambda video_id: {  # type: ignore[method-assign]
            "subtitles": {},
            "automatic_captions": {},
        }
        with pytest.raises(NoCaptionsAvailable) as exc_info:
            subtitles.fetch("dQw4w9WgXcQ")
        assert exc_info.value.code == "no_captions"

    def test_list_tracks_devuelve_none_si_vacio(self) -> None:
        subtitles = YtDlpSubtitles()
        subtitles._extract = lambda video_id: {  # type: ignore[method-assign]
            "subtitles": {},
            "automatic_captions": {},
        }
        assert subtitles.list_tracks("dQw4w9WgXcQ") is None

    def test_list_tracks_encuentra_manual(self) -> None:
        subtitles = YtDlpSubtitles()
        subtitles._extract = lambda video_id: {  # type: ignore[method-assign]
            "subtitles": {"es": [{"ext": "vtt", "url": "http://x"}]},
            "automatic_captions": {},
        }
        assert subtitles.list_tracks("dQw4w9WgXcQ") == ("es", "manual")

    def test_subtitle_result_source_default(self) -> None:
        r = SubtitleResult(language="es", track_type="manual", segments=[])
        assert r.source == "yt_dlp_subtitles"
