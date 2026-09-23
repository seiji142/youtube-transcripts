"""Tests del JobStore (SQLite en tmp, sin red)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.youtube_jobs import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    JobStore,
    make_job_id,
)

VIDEO_ID = "dQw4w9WgXcQ"
LANGS = ["es", "en"]
LANG_KEY = "es+en"
T0 = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    s = JobStore(db_path=tmp_path / "jobs.db", backoff_base_seconds=30.0)
    yield s
    s.close()


class TestCreateOrGet:
    def test_crea_pending_con_job_id_idempotente(self, store: JobStore) -> None:
        job = store.create_or_get(VIDEO_ID, LANGS, now=T0)

        assert job["job_id"] == make_job_id(VIDEO_ID, LANG_KEY)
        assert job["job_id"] == f"{VIDEO_ID}:es+en"
        assert job["status"] == STATUS_PENDING
        assert job["stage"] == "queued"
        assert job["attempts"] == 0
        assert job["languages"] == LANGS

    def test_segunda_llamada_devuelve_mismo_job(self, store: JobStore) -> None:
        first = store.create_or_get(VIDEO_ID, LANGS, now=T0)
        second = store.create_or_get(VIDEO_ID, LANGS, now=T0 + timedelta(seconds=5))

        assert first["job_id"] == second["job_id"]
        assert second["attempts"] == 0
        assert second["created_at"] == first["created_at"]

    def test_jobs_distintos_por_lang_key(self, store: JobStore) -> None:
        a = store.create_or_get(VIDEO_ID, ["es"], now=T0)
        b = store.create_or_get(VIDEO_ID, ["en"], now=T0)

        assert a["job_id"] != b["job_id"]

    def test_job_completed_no_se_reencola(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None
        store.mark_completed(job["job_id"], now=T0)

        again = store.create_or_get(VIDEO_ID, LANGS, now=T0)

        assert again["status"] == STATUS_COMPLETED

    def test_job_failed_se_resetea_a_pending(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None
        store.mark_failed(job["job_id"], "asr_failed", "boom", now=T0, terminal=True)

        again = store.create_or_get(VIDEO_ID, LANGS, now=T0)

        assert again["status"] == STATUS_PENDING
        assert again["attempts"] == 0
        assert again["error_code"] is None


class TestClaimNext:
    def test_claim_toma_pending_e_incrementa_attempts(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)

        job = store.claim_next(now=T0)

        assert job is not None
        assert job["status"] == STATUS_PROCESSING
        assert job["attempts"] == 1
        assert job["heartbeat_at"] is not None

    def test_claim_vacio_devuelve_none(self, store: JobStore) -> None:
        assert store.claim_next(now=T0) is None

    def test_claim_ignora_job_no_vencido(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None
        store.mark_failed(
            job["job_id"], "blocked", "429",
            now=T0, terminal=False,
        )  # backoff 30s → next_attempt = T0+30s

        assert store.claim_next(now=T0 + timedelta(seconds=10)) is None
        assert store.claim_next(now=T0 + timedelta(seconds=31)) is not None

    def test_claim_orden_fifo_por_vencimiento(self, store: JobStore) -> None:
        store.create_or_get("aaaaaaaaaaa", ["es"], now=T0)
        store.create_or_get("bbbbbbbbbbb", ["es"], now=T0 + timedelta(seconds=1))

        first = store.claim_next(now=T0 + timedelta(seconds=2))
        second = store.claim_next(now=T0 + timedelta(seconds=2))

        assert first is not None and first["video_id"] == "aaaaaaaaaaa"
        assert second is not None and second["video_id"] == "bbbbbbbbbbb"


class TestHeartbeatYEstados:
    def test_heartbeat_actualiza_stage(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None

        store.heartbeat(job["job_id"], now=T0 + timedelta(seconds=5),
                        stage="transcribing")

        updated = store.get(job_id=job["job_id"])
        assert updated is not None
        assert updated["stage"] == "transcribing"
        assert updated["heartbeat_at"] == (
            T0 + timedelta(seconds=5)
        ).isoformat(timespec="microseconds")

    def test_mark_completed(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None

        store.mark_completed(job["job_id"], now=T0)

        done = store.get(job_id=job["job_id"])
        assert done is not None
        assert done["status"] == STATUS_COMPLETED
        assert done["stage"] == "done"


class TestMarkFailed:
    def test_retryable_programa_backoff_exponencial(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None

        failed = store.mark_failed(job["job_id"], "blocked", "429", now=T0)

        assert failed["status"] == STATUS_PENDING
        assert failed["attempts"] == 1
        assert failed["error_code"] == "blocked"
        next_at = failed["next_attempt_at"]
        # backoff base 30s * 2^0 = 30s
        expected = (T0 + timedelta(seconds=30)).isoformat(timespec="microseconds")
        assert next_at == expected

    def test_backoff_duplica_en_segundo_intento(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None
        store.mark_failed(job["job_id"], "blocked", "x", now=T0)

        job2 = store.claim_next(now=T0 + timedelta(seconds=31))
        assert job2 is not None
        failed2 = store.mark_failed(job2["job_id"], "blocked", "x",
                                    now=T0 + timedelta(seconds=31))

        # backoff 30s * 2^1 = 60s
        expected = (
            T0 + timedelta(seconds=31 + 60)
        ).isoformat(timespec="microseconds")
        assert failed2["next_attempt_at"] == expected
        assert failed2["attempts"] == 2

    def test_terminal_falla_aunque_queden_intentos(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None

        failed = store.mark_failed(
            job["job_id"], "duration_exceeded", ">2h", now=T0, terminal=True,
        )

        assert failed["status"] == STATUS_FAILED
        assert failed["attempts"] == 1

    def test_se_agota_tras_max_attempts(self, store: JobStore) -> None:
        job_id = None
        now = T0
        for _ in range(3):
            store.create_or_get(VIDEO_ID, LANGS, now=now)
            job = store.claim_next(now=now)
            assert job is not None
            job_id = job["job_id"]
            failed = store.mark_failed(job_id, "blocked", "x", now=now)
            now = now + timedelta(seconds=120)
        assert job_id is not None

        assert failed["status"] == STATUS_FAILED
        assert failed["attempts"] == 3

    def test_job_inexistente_lanza_keyerror(self, store: JobStore) -> None:
        with pytest.raises(KeyError):
            store.mark_failed("nope:es", "blocked", "x", now=T0)


class TestGetYRequeue:
    def test_get_por_job_id(self, store: JobStore) -> None:
        created = store.create_or_get(VIDEO_ID, LANGS, now=T0)

        found = store.get(job_id=created["job_id"])

        assert found is not None
        assert found["video_id"] == VIDEO_ID

    def test_get_por_video_devuelve_ultimo(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, ["es"], now=T0)
        store.create_or_get(VIDEO_ID, ["en"], now=T0 + timedelta(seconds=1))

        found = store.get(video_id=VIDEO_ID)

        assert found is not None
        assert found["languages"] == ["en"]

    def test_get_inexistente_devuelve_none(self, store: JobStore) -> None:
        assert store.get(job_id="nope") is None

    def test_get_sin_args_lanza_value_error(self, store: JobStore) -> None:
        with pytest.raises(ValueError):
            store.get()

    def test_requeue_resetea_job_completado(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None
        store.mark_completed(job["job_id"], now=T0)

        reset = store.requeue(job["job_id"], now=T0)

        assert reset["status"] == STATUS_PENDING
        assert reset["attempts"] == 0


class TestReclaimStale:
    def test_processing_viejo_vuelve_a_pending(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None

        recovered = store.reclaim_stale(now=T0 + timedelta(seconds=901))

        assert recovered == 1
        reclaimed = store.get(job_id=job["job_id"])
        assert reclaimed is not None
        assert reclaimed["status"] == STATUS_PENDING
        assert reclaimed["stage"] == "reclaimed"
        # attempts del intento muerto no se resetea
        assert reclaimed["attempts"] == 1

    def test_processing_fresco_no_toca(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)
        job = store.claim_next(now=T0)
        assert job is not None

        recovered = store.reclaim_stale(now=T0 + timedelta(seconds=10))

        assert recovered == 0
        untouched = store.get(job_id=job["job_id"])
        assert untouched is not None
        assert untouched["status"] == STATUS_PROCESSING

    def test_pending_no_toca(self, store: JobStore) -> None:
        store.create_or_get(VIDEO_ID, LANGS, now=T0)

        assert store.reclaim_stale(now=T0 + timedelta(days=1)) == 0
