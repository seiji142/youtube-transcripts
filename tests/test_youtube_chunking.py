"""Tests del chunking de transcripciones (Fase 3, sin red)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.youtube_chunking import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_TOKENS,
    Chunk,
    chunk_transcript,
    est_tokens,
)

VIDEO_ID = "dQw4w9WgXcQ"


def make_segments(
    count: int,
    chars: int = 400,
    sentence_end: bool = True,
    start: float = 0.0,
    duration: float = 5.0,
) -> list[dict[str, Any]]:
    """Crea ``count`` segmentos de ~chars caracteres cada uno."""
    segments = []
    t = start
    for i in range(count):
        prefix = f"{i:04d} "
        text = prefix + "a" * (chars - len(prefix) - 1)
        if sentence_end:
            text += "."
        segments.append({"start": t, "end": t + duration, "text": text})
        t += duration
    return segments


@dataclass
class SegmentDC:
    """Segmento en formato dataclass (dominio)."""

    start: float
    end: float
    text: str


class TestEstTokens:
    def test_divide_por_cuatro(self) -> None:
        assert est_tokens("abcd" * 10) == 10

    def test_redondeo_hacia_arriba(self) -> None:
        assert est_tokens("abcde") == 2

    def test_vacio_es_cero(self) -> None:
        assert est_tokens("") == 0


class TestValidacion:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"min_tokens": 0},
            {"max_tokens": 0},
            {"min_tokens": 2000, "max_tokens": 1000},
            {"overlap": -0.1},
            {"overlap": 1.0},
        ],
    )
    def test_parametros_invalidos_lanzan_value_error(
        self, kwargs: dict[str, Any],
    ) -> None:
        with pytest.raises(ValueError):
            chunk_transcript(make_segments(3), **kwargs)


class TestCasosBasicos:
    def test_transcript_vacio_devuelve_lista_vacia(self) -> None:
        assert chunk_transcript([]) == []

    def test_segmentos_sin_texto_se_ignoran(self) -> None:
        segments = [
            {"start": 0.0, "end": 1.0, "text": "   "},
            {"start": 1.0, "end": 2.0, "text": ""},
        ]
        assert chunk_transcript(segments) == []

    def test_transcript_corto_es_un_chunk(self) -> None:
        segments = [
            {"start": 0.0, "end": 5.0, "text": "hola mundo."},
            {"start": 5.0, "end": 10.0, "text": "adios a todos."},
        ]

        chunks = chunk_transcript(segments)

        assert len(chunks) == 1
        assert chunks[0].index == 0
        assert chunks[0].start == 0.0
        assert chunks[0].end == 10.0
        assert chunks[0].text == "hola mundo.\nadios a todos."

    def test_acepta_segmentos_dataclass_del_dominio(self) -> None:
        segments = [
            SegmentDC(start=1.0, end=2.0, text="primera parte."),
            SegmentDC(start=2.0, end=3.0, text="segunda parte."),
        ]

        chunks = chunk_transcript(segments)

        assert len(chunks) == 1
        assert chunks[0].start == 1.0
        assert chunks[0].end == 3.0


class TestLimites:
    def test_respeta_max_tokens(self) -> None:
        segments = make_segments(20, chars=800)  # ~200 tokens c/u

        chunks = chunk_transcript(segments)

        assert len(chunks) > 1
        assert all(c.token_count <= DEFAULT_MAX_TOKENS for c in chunks)

    def test_tokens_estimados_no_superan_max_significativamente(self) -> None:
        segments = make_segments(20, chars=800)

        chunks = chunk_transcript(segments)

        for chunk in chunks:
            assert est_tokens(chunk.text) <= DEFAULT_MAX_TOKENS + 5

    def test_chunks_intermedios_alcanzan_min_tokens(self) -> None:
        segments = make_segments(20, chars=800)  # ~200 tokens c/u

        chunks = chunk_transcript(segments)

        for chunk in chunks[:-1]:
            assert chunk.token_count >= DEFAULT_MIN_TOKENS

    def test_cubre_todos_los_segmentos(self) -> None:
        segments = make_segments(30)

        chunks = chunk_transcript(segments)

        joined = "\n".join(c.text for c in chunks)
        for segment in segments:
            assert segment["text"] in joined


class TestFrontieraDeOracion:
    def test_recorta_hasta_ultimo_cue_que_cierra_oracion(self) -> None:
        # 4 cues de ~300 tokens; solo el primero cierra oración.
        segments = make_segments(4, chars=1200, sentence_end=False)
        segments[0]["text"] += "."

        chunks = chunk_transcript(
            segments, min_tokens=100, max_tokens=1000, overlap=0.0,
        )

        assert len(chunks) >= 2
        assert chunks[0].text == segments[0]["text"]
        assert chunks[0].token_count < 400  # recortó la cola sin oración

    def test_conserva_llenado_maximo_si_ningun_cue_cierra_oracion(self) -> None:
        segments = make_segments(15, chars=400, sentence_end=False)

        chunks = chunk_transcript(
            segments, min_tokens=100, max_tokens=1000, overlap=0.0,
        )

        # sin cue con terminador no hay frontera: se llena hasta max
        per_chunk = est_tokens(segments[0]["text"])
        assert chunks[0].token_count == 10 * per_chunk
        assert chunks[0].token_count == 1000

    def test_chunk_que_cierra_oracion_no_se_recorta(self) -> None:
        segments = make_segments(2, chars=800, sentence_end=True)

        chunks = chunk_transcript(
            segments, min_tokens=100, max_tokens=2000, overlap=0.0,
        )

        assert len(chunks) == 1
        assert chunks[0].text.endswith(".")


class TestSolapamiento:
    def test_chunk_siguiente_repite_cola_del_anterior(self) -> None:
        segments = make_segments(30, chars=400)  # ~100 tokens c/u

        chunks = chunk_transcript(segments)

        assert len(chunks) >= 2
        first_line_next = chunks[1].text.split("\n")[0]
        # con overlap ~12%, la última unidad (~10%) se repite
        assert first_line_next in [s["text"] for s in segments[:12]]

    def test_overlap_cero_no_repite_unidades(self) -> None:
        segments = make_segments(30, chars=400)

        chunks = chunk_transcript(segments, overlap=0.0)

        lines = [line for c in chunks for line in c.text.split("\n")]
        assert len(lines) == len(set(lines))

    def test_overlap_alto_termina_y_cubre(self) -> None:
        segments = make_segments(20, chars=400)

        chunks = chunk_transcript(segments, overlap=0.99)

        assert len(chunks) >= 2
        assert segments[-1]["text"] in chunks[-1].text


class TestSegmentosOversize:
    def test_cue_gigante_se_parte_en_oraciones(self) -> None:
        sentence = "palabra palabra palabra palabra. "  # 34 chars ≈ 9 tokens
        text = sentence * 500  # ~4500 tokens en una sola oración+...
        segments = [
            {"start": 0.0, "end": 120.0, "text": text.strip()},
        ]

        chunks = chunk_transcript(segments)

        assert len(chunks) > 1
        assert all(c.token_count <= DEFAULT_MAX_TOKENS for c in chunks)
        # el texto se conserva (concatenado sin espacios de sobra)
        assert "palabra" in chunks[0].text
        assert "palabra" in chunks[-1].text

    def test_cue_sin_oraciones_se_corta_duro_por_caracteres(self) -> None:
        text = "palabra " * 5000  # 40 000 chars sin terminadores
        segments = [{"start": 0.0, "end": 600.0, "text": text.strip()}]

        chunks = chunk_transcript(segments)

        assert len(chunks) == 10  # 40 000 chars / 4 000 por corte duro
        assert all(c.token_count <= DEFAULT_MAX_TOKENS for c in chunks)
        combined = "".join(c.text for c in chunks)
        assert combined == text.strip()

    def test_piezas_de_cue_gigante_reparten_el_tiempo(self) -> None:
        text = "frase con punto. " * 400  # muchas oraciones, un cue
        segments = [{"start": 10.0, "end": 210.0, "text": text.strip()}]

        chunks = chunk_transcript(segments)

        assert chunks[0].start == 10.0
        assert chunks[-1].end == 210.0
        starts = [c.start for c in chunks]
        assert starts == sorted(starts)


class TestMetadatos:
    def test_indices_secuenciales_y_tiempo_monotonico(self) -> None:
        segments = make_segments(25)

        chunks = chunk_transcript(segments)

        assert [c.index for c in chunks] == list(range(len(chunks)))
        starts = [c.start for c in chunks]
        assert starts == sorted(starts)

    def test_start_end_igual_primer_y_ultimo_segmento(self) -> None:
        segments = make_segments(25, start=100.0)

        chunks = chunk_transcript(segments)

        assert chunks[0].start == segments[0]["start"]
        assert chunks[-1].end == segments[-1]["end"]

    def test_to_dict_trae_los_campos(self) -> None:
        chunks = chunk_transcript([{"start": 0.0, "end": 1.0, "text": "hola."}])

        payload = chunks[0].to_dict()

        assert payload == {
            "index": 0,
            "text": "hola.",
            "start": 0.0,
            "end": 1.0,
            "token_count": est_tokens("hola."),
        }

    def test_chunk_es_dataclass(self) -> None:
        chunks = chunk_transcript([{"start": 0.0, "end": 1.0, "text": "hola."}])
        assert isinstance(chunks[0], Chunk)
