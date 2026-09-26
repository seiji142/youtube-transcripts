"""Verificación real D2 — Fase 2 cierre: video sin captions → ASR small.

Flujo completo con herramientas REALES de mcp_server (sin mocks):
  1. youtube_transcript(URL) → processing (encola job ASR)
  2. _worker.run_once() → descarga audio real + faster-whisper small
  3. youtube_transcript_status → completed
  4. youtube_transcript_read → texto con timestamps
  5. audio temporal eliminado (criterio §8)

NOTA HISTÓRICA: script archivado desde Temp (sesión 23/09). Requiere
red/FFmpeg/estado de la época; no re-ejecutar como verificación actual.
"""
from __future__ import annotations

import glob
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# FFmpeg: refrescar PATH (winget lo agregó tras iniciar opencode)
_bins = glob.glob(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin")
)
if _bins:
    os.environ["PATH"] = _bins[-1] + os.pathsep + os.environ.get("PATH", "")

URL = "https://www.youtube.com/watch?v=ScMzIvxBSi4"
VIDEO_ID = "ScMzIvxBSi4"


def main() -> None:
    from mcp_server import (
        _cache,
        _jobs,
        _worker,
        youtube_transcript,
        youtube_transcript_read,
        youtube_transcript_status,
    )
    from services.youtube_audio import TEMP_PREFIX

    t0 = time.time()

    print("[1/5] youtube_transcript (captions + subtítulos + encolado)...")
    payload = youtube_transcript(URL)
    print(f"      {payload}")
    if payload["status"] not in ("processing", "completed"):
        raise SystemExit(f"FAIL: se esperaba processing/completed → {payload}")
    job_id = payload.get("job_id") or f"{VIDEO_ID}:es+en"

    if payload["status"] == "processing":
        print("[2/5] worker.run_once() — descarga audio + ASR small (puede tardar)...")
        job = _worker.run_once()
        if job is None:
            raise SystemExit("FAIL: worker no encontró el job recién encolado")
        print(
            f"      status={job['status']} stage={job['stage']} "
            f"attempts={job['attempts']} error={job.get('error_code')}"
        )
        if job["status"] != "completed":
            raise SystemExit(
                f"FAIL: job no completó: {job.get('error_code')} "
                f"{job.get('error_message')}"
            )
    else:
        print("[2/5] job ya completed (corrida previa) — saltando worker")

    print("[3/5] youtube_transcript_status...")
    status = youtube_transcript_status(job_id=job_id)
    print(f"      {status}")
    if status["status"] != "completed":
        raise SystemExit(f"FAIL: status != completed → {status}")

    print("[4/5] youtube_transcript_read (rango 0..60s, max 600 chars)...")
    reading = youtube_transcript_read(VIDEO_ID, start=0.0, end=60.0, max_chars=600)
    print(f"      language={reading.get('language')} source={reading.get('source')}")
    print(f"      chars={reading.get('chars')} truncated={reading.get('truncated')}")
    preview = reading.get("text", "")[:400]
    print(f"      text[:400]= {preview!r}")
    if reading["status"] != "completed" or not reading.get("text", "").strip():
        raise SystemExit(f"FAIL: lectura vacía o error → {reading}")

    # chequeo extra: la transcripción completa quedó en caché
    entry = _cache.get_any(VIDEO_ID)
    if entry is None or entry.get("source") != "faster_whisper":
        raise SystemExit(f"FAIL: caché sin resultado ASR → {entry}")

    print("[5/5] audio temporal limpio...")
    leftovers = [
        p for p in glob.glob(os.path.join(os.environ.get("TEMP", ""), f"{TEMP_PREFIX}*"))
        if VIDEO_ID in p and os.path.isdir(p)
    ]
    if leftovers:
        raise SystemExit(f"FAIL: temporales huérfanos → {leftovers}")
    print("      OK sin restos de audio")

    elapsed = time.time() - t0
    print(
        f"VERIFY PASS en {elapsed:.0f}s | language={reading.get('language')} "
        f"| segments_total={len(entry['segments'])}"
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("VERIFY FAIL")
        sys.exit(1)
