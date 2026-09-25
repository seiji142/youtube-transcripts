"""Tests de resúmenes jerárquicos extractivos (Fase 4 E3, sin red)."""
from __future__ import annotations

from typing import Any

import pytest

from services.youtube_summarize import (
    SummaryResult,
    summarize_transcript,
)


def make_segments(
    texts: list[str], start: float = 0.0, duration: float = 10.0,
) -> list[dict[str, Any]]:
    segments = []
    t = start
    for text in texts:
        segments.append({"start": t, "end": t + duration, "text": text})
        t += duration
    return segments


LONG_TEXTS = [
    "El motor cachimbo es muy rápido y eficiente para la ciudad.",
    "La batería dura tres días con uso intensivo del motor cachimbo.",
    "Hablamos del clima soleado de la costa mediterránea.",
    "El motor cachimbo necesita poco mantenimiento anual.",
    "La costa mediterránea tiene playas excelentes en verano.",
    "Resumiendo el motor cachimbo conviene por precio y consumo.",
]


class TestValidacion:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_sections": 0},
            {"max_sections": 11},
            {"sentences_per_section": 0},
            {"sentences_per_section": 6},
        ],
    )
    def test_parametros_invalidos(self, kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            summarize_transcript(make_segments(LONG_TEXTS), **kwargs)


class TestCasosBasicos:
    def test_vacio_devuelve_resumen_vacio(self) -> None:
        result = summarize_transcript([])

        assert isinstance(result, SummaryResult)
        assert result.sections == []
        assert result.overall == []

    def test_segmentos_sin_texto_se_ignoran(self) -> None:
        result = summarize_transcript([
            {"start": 0.0, "end": 1.0, "text": "   "},
        ])

        assert result.sections == []
        assert result.overall == []

    def test_overall_trae_las_mejores_oraciones(self) -> None:
        result = summarize_transcript(
            make_segments(LONG_TEXTS), sentences_per_section=2,
        )

        assert len(result.overall) == 2
        joined = " ".join(s.text for s in result.overall)
        # "motor cachimbo" es el término dominante del documento
        assert "cachimbo" in joined

    def test_overall_ordenado_por_tiempo(self) -> None:
        result = summarize_transcript(
            make_segments(LONG_TEXTS), sentences_per_section=3,
        )

        starts = [s.text for s in result.overall]
        assert len(starts) == 3
        times = [s.start for s in result.overall]
        assert times == sorted(times)


class TestSecciones:
    def test_respeta_max_sections(self) -> None:
        result = summarize_transcript(
            make_segments(LONG_TEXTS), max_sections=2,
        )

        assert len(result.sections) == 2
        assert result.sections[0].index == 0
        assert result.sections[1].index == 1

    def test_secciones_cubren_la_duracion(self) -> None:
        segments = make_segments(LONG_TEXTS, duration=10.0)  # 0..60s
        result = summarize_transcript(segments, max_sections=3)

        assert result.sections[0].start == 0.0
        assert result.sections[-1].end == 60.0
        for section in result.sections:
            assert section.end > section.start

    def test_sentences_por_seccion_acotadas(self) -> None:
        result = summarize_transcript(
            make_segments(LONG_TEXTS * 3),
            max_sections=2, sentences_per_section=1,
        )

        for section in result.sections:
            assert len(section.sentences) <= 1

    def test_oraciones_conservan_timestamps(self) -> None:
        result = summarize_transcript(make_segments(LONG_TEXTS, start=100.0))

        for section in result.sections:
            for sentence in section.sentences:
                assert sentence.start >= 100.0
        for sentence in result.overall:
            assert sentence.start >= 100.0

    def test_seccion_prefiere_oraciones_de_su_tramo(self) -> None:
        texts = (
            ["El motor cachimbo domina la primera parte del video."]
            + ["Relleno neutro sin palabras clave relevantes."] * 4
            + ["El motor cachimbo domina la última parte del video."]
            + ["Relleno neutro sin palabras clave relevantes."] * 4
        )
        result = summarize_transcript(
            make_segments(texts, duration=10.0),
            max_sections=2, sentences_per_section=1,
        )

        assert len(result.sections) == 2
        assert "primera parte" in result.sections[0].sentences[0].text
        assert "última parte" in result.sections[1].sentences[0].text


class TestToDict:
    def test_estructura(self) -> None:
        result = summarize_transcript(
            make_segments(LONG_TEXTS[:3]), max_sections=1,
        )

        payload = result.to_dict()

        assert len(payload["sections"]) == 1
        section = payload["sections"][0]
        assert {"index", "start", "end", "sentences"} <= set(section)
        assert all(
            {"text", "start", "end"} <= set(s) for s in section["sentences"]
        )
        assert all({"text", "start", "end"} <= set(s) for s in payload["overall"])
