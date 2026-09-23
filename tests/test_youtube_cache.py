"""Tests de la caché SQLite de transcripts."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from services.youtube_cache import TranscriptCache

SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "hola"},
    {"start": 2.5, "end": 5.0, "text": "mundo"},
]


@pytest.fixture
def cache(tmp_path: Path) -> TranscriptCache:
    with TranscriptCache(db_path=tmp_path / "test.db") as c:
        yield c


class TestCacheBasica:
    def test_miss_inicio(self, cache: TranscriptCache) -> None:
        assert cache.get("vid12345678", "es", "manual") is None

    def test_set_y_get(self, cache: TranscriptCache) -> None:
        cache.set(
            "vid12345678", "es", "manual",
            SEGMENTS, language_code="es", source="youtube_captions",
        )
        entry = cache.get("vid12345678", "es", "manual")
        assert entry is not None
        assert entry["video_id"] == "vid12345678"
        assert entry["lang"] == "es"
        assert entry["track_type"] == "manual"
        assert entry["language_code"] == "es"
        assert entry["source"] == "youtube_captions"
        assert entry["segments"] == SEGMENTS
        assert "fetched_at" in entry

    def test_clave_compuesta(self, cache: TranscriptCache) -> None:
        """Distinta combinación video_id+lang+track_type son entradas distintas."""
        cache.set("vid12345678", "es", "manual", SEGMENTS)
        cache.set("vid12345678", "en", "manual", SEGMENTS)
        cache.set("vid12345678", "es", "auto", SEGMENTS)
        cache.set("otro_video12", "es", "manual", SEGMENTS)

        assert cache.get("vid12345678", "es", "manual") is not None
        assert cache.get("vid12345678", "en", "manual") is not None
        assert cache.get("vid12345678", "es", "auto") is not None
        assert cache.get("vid12345678", "en", "auto") is None
        assert cache.get("otro_video12", "es", "manual") is not None
        assert cache.get("no_existe123", "es", "manual") is None

    def test_replace_sobrescribe(self, cache: TranscriptCache) -> None:
        cache.set("vid12345678", "es", "manual", SEGMENTS, source="a")
        cache.set("vid12345678", "es", "manual", SEGMENTS, source="b")
        entry = cache.get("vid12345678", "es", "manual")
        assert entry is not None
        assert entry["source"] == "b"

    def test_delete(self, cache: TranscriptCache) -> None:
        cache.set("vid12345678", "es", "manual", SEGMENTS)
        cache.delete("vid12345678", "es", "manual")
        assert cache.get("vid12345678", "es", "manual") is None

    def test_clear(self, cache: TranscriptCache) -> None:
        cache.set("vid12345678", "es", "manual", SEGMENTS)
        cache.set("otro_video12", "en", "auto", SEGMENTS)
        cache.clear()
        assert cache.get("vid12345678", "es", "manual") is None
        assert cache.get("otro_video12", "en", "auto") is None


class TestGetAny:
    def test_devuelve_entrada_existente(self, cache: TranscriptCache) -> None:
        cache.set(
            "vid12345678", "es+en", "asr",
            SEGMENTS, language_code="es", source="faster_whisper",
        )
        entry = cache.get_any("vid12345678")
        assert entry is not None
        assert entry["track_type"] == "asr"
        assert entry["source"] == "faster_whisper"
        assert entry["segments"] == SEGMENTS

    def test_video_sin_entradas_devuelve_none(self, cache: TranscriptCache) -> None:
        assert cache.get_any("no_existe123") is None

    def test_prefiere_la_mas_reciente(self, cache: TranscriptCache) -> None:
        cache.set("vid12345678", "es", "manual", SEGMENTS, source="viejo")
        cache.set("vid12345678", "es+en", "asr", SEGMENTS, source="nuevo")
        entry = cache.get_any("vid12345678")
        assert entry is not None
        assert entry["source"] == "nuevo"

    def test_expirada_devuelve_none_y_purga(self, tmp_path: Path) -> None:
        with TranscriptCache(db_path=tmp_path / "t.db", ttl=timedelta(seconds=-1)) as c:
            c.set("vid12345678", "es", "manual", SEGMENTS)
            assert c.get_any("vid12345678") is None
            row = c._conn.execute(
                "SELECT COUNT(*) AS n FROM transcripts"
            ).fetchone()
            assert row["n"] == 0


class TestTTL:
    def test_entrada_fresca_persiste(self, tmp_path: Path) -> None:
        with TranscriptCache(db_path=tmp_path / "t.db", ttl=timedelta(days=7)) as c:
            c.set("vid12345678", "es", "manual", SEGMENTS)
            assert c.get("vid12345678", "es", "manual") is not None

    def test_entrada_expirada_se_elimina(self, tmp_path: Path) -> None:
        with TranscriptCache(db_path=tmp_path / "t.db", ttl=timedelta(seconds=-1)) as c:
            c.set("vid12345678", "es", "manual", SEGMENTS)
            assert c.get("vid12345678", "es", "manual") is None
            # la entrada expirada se purga
            row = c._conn.execute(
                "SELECT COUNT(*) AS n FROM transcripts"
            ).fetchone()
            assert row["n"] == 0

    def test_ttl_configurable(self, tmp_path: Path) -> None:
        with TranscriptCache(db_path=tmp_path / "t.db", ttl=timedelta(hours=1)) as c:
            assert c.ttl == timedelta(hours=1)
