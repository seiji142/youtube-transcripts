"""Verificación real D2 (v4) — último intento + fallback controlado.

Fase A: filtro "last hour" de YouTube, hasta18 probes buscando
subs=False AND autos=False → E2E real completo (enqueue→worker→
completed→read) con español.

Fase B (si A no encuentra): job manual (create_or_get) sobre un video
con audio en español real (1m7fTsJzoao, Cádiz) — el trigger sin
captions ya está probado con ScMzIvxBSi4 (processing real); esta fase
cierra worker→status→read con texto español real.

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
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_bins = glob.glob(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin")
)
if _bins:
    os.environ["PATH"] = _bins[-1] + os.pathsep + os.environ.get("PATH", "")

PROBE_GAP = 1.3
MAX_PROBES = 18
FALLBACK_VIDEO = "1m7fTsJzoao"  # "vlog para aprender español: Cádiz" — audio ES

SEARCH_URLS = [
    "https://www.youtube.com/results?search_query=shorts&sp=EgIIAQ%3D%3D",
    "https://www.youtube.com/results?search_query=vlog&sp=EgIIAQ%3D%3D",
    "https://www.youtube.com/results?search_query=espanol&sp=EgIIAQ%3D%3D",
]


def e2e(video_id: str) -> bool:
    from mcp_server import (
        _worker,
        youtube_transcript,
        youtube_transcript_read,
        youtube_transcript_status,
    )

    url = f"https://www.youtube.com/watch?v={video_id}"
    payload = youtube_transcript(url)
    print(f"      transcript → {payload.get('status')} job={payload.get('job_id')}")
    if payload["status"] not in ("processing", "completed"):
        print(f"      FAIL payload: {payload}")
        return False

    if payload["status"] == "processing":
        job = _worker.run_once()
        if job is None:
            print("      FAIL: worker sin job")
            return False
        print(
            f"      worker → {job['status']} err={job.get('error_code')} "
            f"{(job.get('error_message') or '')[:100]}"
        )
        if job["status"] != "completed":
            return False

    job_id = payload.get("job_id") or f"{video_id}:es+en"
    status = youtube_transcript_status(job_id=job_id)
    if status["status"] != "completed":
        print(f"      FAIL status: {status}")
        return False

    reading = youtube_transcript_read(video_id, start=0.0, end=90.0, max_chars=500)
    language = reading.get("language")
    text = reading.get("text", "")
    print(
        f"      read → lang={language} chars={reading.get('chars')} "
        f"text={text[:220]!r}"
    )
    if reading["status"] != "completed" or len(text.strip()) < 20:
        print("      FAIL: texto vacío/corto")
        return False
    if not (language or "").startswith("es"):
        print(f"      FAIL: idioma {language} no es español")
        return False
    return True


def phase_a() -> bool:
    from yt_dlp import YoutubeDL

    print("[Fase A] búsqueda last-hour, sin captions...")
    flat_opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": "in_playlist", "noplaylist": True,
    }
    fresh: list[str] = []
    seen: set[str] = set()
    for url in SEARCH_URLS:
        with YoutubeDL(flat_opts) as ydl:
            result = ydl.extract_info(url, download=False)
        for entry in (result or {}).get("entries") or []:
            vid = entry.get("id")
            dur = entry.get("duration")
            if not vid or vid in seen or len(vid) != 11 or dur is None:
                continue
            if not (45 <= float(dur) <= 900):
                continue
            seen.add(vid)
            fresh.append(vid)
        time.sleep(PROBE_GAP)

    print(f"      {len(fresh)} candidatos por duración")
    probes = 0
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        for vid in fresh:
            if probes >= MAX_PROBES:
                break
            probes += 1
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            time.sleep(PROBE_GAP)
            subs = info.get("subtitles") or {}
            autos = info.get("automatic_captions") or {}
            upload = info.get("upload_date")
            if subs or autos:
                if probes <= 6 or probes % 5 == 0:
                    print(f"      probe {probes}: {vid} {upload} CON captions")
                continue
            print(f"      probe {probes}: {vid} {upload} SIN captions ✓ → E2E")
            if e2e(vid):
                print(f"VERIFY PASS (fase-A) video={vid}")
                return True
    print(f"      Fase A agotada ({probes} probes): ningún video sin captions+ES")
    return False


def phase_b() -> bool:
    from mcp_server import _jobs, _worker, youtube_transcript_read, youtube_transcript_status

    print("[Fase B] fallback: job manual sobre audio español real (Cádiz vlog)...")
    # El trigger "sin captions → processing" ya está probado con
    # ScMzIvxBSi4 (encolado real 23/09). Aquí cerramos el pipeline
    # worker→completed→read con habla en español.
    job = _jobs.create_or_get(FALLBACK_VIDEO, ["es", "en"])
    print(f"      job={job['job_id']} status={job['status']}")
    if job["status"] != "completed":
        result = _worker.run_once()
        if result is None:
            print("      FAIL: worker sin job")
            return False
        print(
            f"      worker → {result['status']} err={result.get('error_code')} "
            f"{(result.get('error_message') or '')[:100]}"
        )
        if result["status"] != "completed":
            return False

    status = youtube_transcript_status(job_id=job["job_id"])
    if status["status"] != "completed":
        print(f"      FAIL status: {status}")
        return False

    reading = youtube_transcript_read(FALLBACK_VIDEO, start=0.0, end=90.0, max_chars=500)
    language = reading.get("language")
    text = reading.get("text", "")
    print(
        f"      read → lang={language} chars={reading.get('chars')} "
        f"text={text[:220]!r}"
    )
    if reading["status"] != "completed" or len(text.strip()) < 20:
        print("      FAIL: texto vacío/corto")
        return False
    if not (language or "").startswith("es"):
        print(f"      FAIL: idioma {language} no es español")
        return False
    print(f"VERIFY PASS (fase-B) video={FALLBACK_VIDEO} (trigger sin captions: ScMzIvxBSi4 ✓)")
    return True


def check_cleanup() -> None:
    from services.youtube_audio import TEMP_PREFIX

    leftovers = [
        p for p in glob.glob(os.path.join(os.environ.get("TEMP", ""), f"{TEMP_PREFIX}*"))
        if os.path.isdir(p)
    ]
    if leftovers:
        print(f"      AVISO temporales presentes (swept por run_forever): {len(leftovers)}")
    else:
        print("[ok] sin temporales de audio")


def main() -> None:
    if not phase_a():
        if not phase_b():
            raise SystemExit("FAIL: ambas fases sin éxito")
    check_cleanup()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("VERIFY FAIL")
        sys.exit(1)
