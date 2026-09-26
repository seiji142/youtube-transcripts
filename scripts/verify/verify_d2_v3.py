"""Verificación real D2 (v3) — E2E con candidato sin captions Y con habla.

Búsqueda por fecha de subida (sp=CAI%3D), filtrado: subs y
automatic_captions vacíos, duración 45..900s. E2E real vía tools de
mcp_server hasta obtener texto con idioma detectado español.

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
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emojis en consola Win

_bins = glob.glob(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin")
)
if _bins:
    os.environ["PATH"] = _bins[-1] + os.pathsep + os.environ.get("PATH", "")

MIN_DURATION = 45
MAX_DURATION = 900
PROBE_GAP_SECONDS = 1.3
MAX_PROBES = 10
MAX_CANDIDATES = 3
MAX_E2E = 3

SEARCH_URLS = [
    "https://www.youtube.com/results?search_query=vlog+personal+espanol&sp=CAI%3D",
    "https://www.youtube.com/results?search_query=shorts+hablando&sp=CAI%3D",
    "https://www.youtube.com/results?search_query=opinion+espanol&sp=CAI%3D",
]


def find_candidates() -> list[dict]:
    from yt_dlp import YoutubeDL

    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
    }
    seen: set[str] = set()
    fresh: list[str] = []
    for url in SEARCH_URLS:
        with YoutubeDL(flat_opts) as ydl:
            result = ydl.extract_info(url, download=False)
        for entry in (result or {}).get("entries") or []:
            vid = entry.get("id")
            duration = entry.get("duration")
            if not vid or vid in seen or len(vid) != 11:
                continue
            seen.add(vid)
            if duration is None:
                continue
            if not (MIN_DURATION <= float(duration) <= MAX_DURATION):
                continue
            fresh.append(vid)
        time.sleep(PROBE_GAP_SECONDS)

    print(f"[search] {len(fresh)} candidatos por duración {MIN_DURATION}-{MAX_DURATION}s")

    probes = 0
    candidates: list[dict] = []
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        for vid in fresh:
            if probes >= MAX_PROBES or len(candidates) >= MAX_CANDIDATES:
                break
            probes += 1
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            time.sleep(PROBE_GAP_SECONDS)
            subs = info.get("subtitles") or {}
            autos = info.get("automatic_captions") or {}
            title = (info.get("title") or "")[:60]
            upload = info.get("upload_date")
            dur = info.get("duration")
            if subs or autos:
                print(f"[probe {probes}] {vid} {upload} — CON captions, skip ({title})")
                continue
            print(f"[probe {probes}] {vid} {upload} dur={dur}s — SIN captions ✓ ({title})")
            candidates.append({"id": vid, "title": title, "duration": dur, "upload": upload})

    candidates.sort(key=lambda c: c["duration"] or 9999)
    return candidates


def run_e2e(video_id: str) -> bool:
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


def main() -> None:
    print("[1/2] buscando candidatos sin captions (orden por subida)...")
    candidates = find_candidates()
    if not candidates:
        raise SystemExit("FAIL: ningún candidato sin captions en el presupuesto")
    print(f"      {len(candidates)} candidato(s): {[c['id'] for c in candidates]}")

    print("[2/2] E2E real (hasta 3 candidatos)...")
    for candidate in candidates[:MAX_E2E]:
        print(f"  → {candidate['id']} dur={candidate['duration']}s {candidate['title']!r}")
        if run_e2e(candidate["id"]):
            print(f"VERIFY PASS video={candidate['id']} title={candidate['title']!r}")
            return
    raise SystemExit("FAIL: ningún candidato completó E2E con español")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("VERIFY FAIL")
        sys.exit(1)
