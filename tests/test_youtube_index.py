"""Tests del índice FTS5 de chunks (Fase 3, SQLite en tmp, sin red)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.youtube_index import (
    MAX_TOP_K,
    TranscriptIndex,
    build_match_query,
)

VIDEO_ID = "dQw4w9WgXcQ"
VIDEO_ID_2 = "abcdefghijk"


def make_segments(count: int = 10, marker: str = "alpha") -> list[dict[str, Any]]:
    """Segmentos cortos con una palabra distintiva ``marker``."""
    segments = []
    for i in range(count):
        segments.append(
            {
                "start": float(i * 5),
                "end": float(i * 5 + 5),
                "text": f"{marker} numero {i} de la transcripcion.",
            }
        )
    return segments


@pytest.fixture
def index(tmp_path: Path) -> TranscriptIndex:
    idx = TranscriptIndex(db_path=tmp_path / "index.db")
    yield idx
    idx.close()


class TestBuildMatchQuery:
    def test_tokens_se_escapan_entre_comillas(self) -> None:
        assert build_match_query("hola mundo") == '"hola" OR "mundo"'

    def test_operadores_fts5_se_tratan_como_texto(self) -> None:
        query = build_match_query('foo OR "bar" NEAR/x *')
        assert query == '"foo" OR "OR" OR "bar" OR "NEAR/x"'

    def test_terminos_de_solo_puntuacion_se_descartan(self) -> None:
        assert build_match_query("hola * () ...") == '"hola"'

    def test_duplicados_se_descartan(self) -> None:
        assert build_match_query("hola hola hola") == '"hola"'

    def test_query_sin_terminos_lanza_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_match_query('   ""  ')

    def test_tope_de_terminos(self) -> None:
        query = " ".join(f"t{i}" for i in range(50))
        built = build_match_query(query)
        assert built.count(" OR ") == 31  # max_terms = 32


class TestIndexTranscript:
    def test_devuelve_cantidad_de_chunks(self, index: TranscriptIndex) -> None:
        count = index.index_transcript(VIDEO_ID, "es", "manual", make_segments())

        assert count >= 1
        assert index.is_indexed(VIDEO_ID, "es", "manual")

    def test_reindexar_es_idempotente(self, index: TranscriptIndex) -> None:
        segments = make_segments()
        first = index.index_transcript(VIDEO_ID, "es", "manual", segments)
        second = index.index_transcript(VIDEO_ID, "es", "manual", segments)

        assert first == second
        rows = index._conn.execute(  # noqa: SLF001 — inspección de test
            "SELECT COUNT(*) AS n FROM transcript_chunks WHERE video_id = ?",
            (VIDEO_ID,),
        ).fetchone()
        assert rows["n"] == first

    def test_claves_distintas_coexisten(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        index.index_transcript(VIDEO_ID, "en", "manual", make_segments(marker="beta"))

        assert index.is_indexed(VIDEO_ID, "es", "manual")
        assert index.is_indexed(VIDEO_ID, "en", "manual")

    def test_transcript_vacio_indexa_cero_chunks(self, index: TranscriptIndex) -> None:
        count = index.index_transcript(VIDEO_ID, "es", "manual", [])
        assert count == 0

    def test_ensure_indexed_indexa_una_vez(
        self, index: TranscriptIndex,
    ) -> None:
        segments = make_segments()

        first = index.ensure_indexed(VIDEO_ID, "es", "manual", segments)
        second = index.ensure_indexed(VIDEO_ID, "es", "manual", segments)

        assert first is True
        assert second is False


class TestSchema:
    def test_schema_idempotente_al_reabrir(self, tmp_path: Path) -> None:
        path = tmp_path / "index.db"
        idx = TranscriptIndex(db_path=path)
        idx.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        idx.close()

        reopened = TranscriptIndex(db_path=path)
        try:
            assert reopened.is_indexed(VIDEO_ID, "es", "manual")
            results = reopened.search(VIDEO_ID, "alpha")
            assert results
        finally:
            reopened.close()

    def test_fts_sincronizado_tras_reindex(
        self, index: TranscriptIndex,
    ) -> None:
        segments = make_segments(120)
        index.index_transcript(VIDEO_ID, "es", "manual", segments)
        index.index_transcript(VIDEO_ID, "es", "manual", segments)  # reindex

        # sin duplicados: el FTS no debe devolver la misma fila dos veces
        results = index.search(VIDEO_ID, "alpha", top_k=MAX_TOP_K)
        assert len(results) > 1
        ids = [r["chunk_id"] for r in results]
        assert len(ids) == len(set(ids))


class TestSearch:
    def test_encuentra_chunk_relevante(self, index: TranscriptIndex) -> None:
        segments = make_segments(10, marker="alpha")
        segments[3]["text"] = "charlando sobre el clima y el zafiro azul."
        index.index_transcript(VIDEO_ID, "es", "manual", segments)

        results = index.search(VIDEO_ID, "zafiro")

        assert len(results) == 1
        assert results[0]["chunk_index"] == 0  # transcript corto = 1 chunk
        assert "zafiro" in results[0]["text"]
        assert results[0]["video_id"] == VIDEO_ID
        assert isinstance(results[0]["score"], float)

    def test_ordena_por_relevancia_bm25(self, index: TranscriptIndex) -> None:
        segments = make_segments(10, marker="alpha")
        index.index_transcript(VIDEO_ID, "es", "manual", segments)

        results = index.search(VIDEO_ID, "alpha", top_k=5)

        scores = [r["score"] for r in results]
        assert scores == sorted(scores)  # bm25: más negativo = mejor

    def test_top_k_limita_resultados(self, index: TranscriptIndex) -> None:
        # transcript largo → varios chunks, todos con "alpha"
        segments = make_segments(120, marker="alpha")
        index.index_transcript(VIDEO_ID, "es", "manual", segments)

        results = index.search(VIDEO_ID, "alpha", top_k=2)

        assert len(results) == 2

    @pytest.mark.parametrize("top_k", [0, -1, MAX_TOP_K + 1])
    def test_top_k_invalido_lanza_value_error(
        self, index: TranscriptIndex, top_k: int,
    ) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        with pytest.raises(ValueError):
            index.search(VIDEO_ID, "alpha", top_k=top_k)

    def test_query_vacia_lanza_value_error(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        with pytest.raises(ValueError):
            index.search(VIDEO_ID, '""')

    def test_query_con_caracteres_especiales_no_crash(
        self, index: TranscriptIndex,
    ) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())

        results = index.search(VIDEO_ID, 'foo " OR * () NEAR:')

        assert isinstance(results, list)

    def test_sin_coincidencias_devuelve_vacio(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())

        assert index.search(VIDEO_ID, "zzzzzznoexiste") == []

    def test_busqueda_filtrada_por_video(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments(marker="alpha"))
        index.index_transcript(
            VIDEO_ID_2, "es", "manual", make_segments(marker="gamma"),
        )

        results = index.search(VIDEO_ID, "gamma")

        assert results == []
        results_a = index.search(VIDEO_ID, "alpha")
        assert all(r["video_id"] == VIDEO_ID for r in results_a)

    def test_transcripcion_sin_indexar_devuelve_vacio(
        self, index: TranscriptIndex,
    ) -> None:
        assert index.search(VIDEO_ID, "alpha") == []

    def test_timestamps_preservados_en_resultado(
        self, index: TranscriptIndex,
    ) -> None:
        segments = make_segments(10, marker="alpha")
        index.index_transcript(VIDEO_ID, "es", "manual", segments)

        results = index.search(VIDEO_ID, "alpha", top_k=1)

        # transcript corto → 1 chunk que cubre los 10 segmentos (0..50s)
        assert results[0]["start"] == 0.0
        assert results[0]["end"] == 50.0


class TestDelete:
    def test_delete_de_una_clave(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        index.index_transcript(VIDEO_ID, "en", "manual", make_segments(marker="beta"))

        index.delete(VIDEO_ID, lang="es", track_type="manual")

        assert not index.is_indexed(VIDEO_ID, "es", "manual")
        assert index.is_indexed(VIDEO_ID, "en", "manual")

    def test_delete_de_un_video_completo(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        index.index_transcript(VIDEO_ID_2, "es", "manual", make_segments())

        index.delete(VIDEO_ID)

        assert not index.is_indexed(VIDEO_ID, "es", "manual")
        assert index.is_indexed(VIDEO_ID_2, "es", "manual")

    def test_clear_de_todo(self, index: TranscriptIndex) -> None:
        index.index_transcript(VIDEO_ID, "es", "manual", make_segments())
        index.index_transcript(VIDEO_ID_2, "es", "manual", make_segments())

        index.clear()

        assert not index.is_indexed(VIDEO_ID, "es", "manual")
        assert index.search(VIDEO_ID, "alpha") == []

    def test_delete_deja_libre_para_reindexar(
        self, index: TranscriptIndex,
    ) -> None:
        segments = make_segments()
        index.index_transcript(VIDEO_ID, "es", "manual", segments)
        index.delete(VIDEO_ID)

        count = index.index_transcript(VIDEO_ID, "es", "manual", segments)

        assert count >= 1
        assert index.search(VIDEO_ID, "alpha")
