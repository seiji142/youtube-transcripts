"""Verificación real Fase 3: youtube_transcript_search sobre video cacheado.

Criterio §8: la búsqueda devuelve fragmentos citados con &t=, no la
transcripción entera. Usa el transcript real en caché de data/youtube.db.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_server import youtube_transcript_search  # noqa: E402
from services.youtube_index import TranscriptIndex  # noqa: E402

URL = "https://www.youtube.com/watch?v=1m7fTsJzoao"
VIDEO_ID = "1m7fTsJzoao"
DURATION = 566.06
FULL_CHARS = 6431


def check(payload: dict, label: str, failures: list[str]) -> None:
    print(f"--- {label} ---")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload.get("status") != "completed":
        failures.append(f"{label}: status={payload.get('status')}")
        return
    results = payload.get("results", [])
    if payload.get("count", 0) < 1:
        failures.append(f"{label}: sin resultados")
    for row in results:
        if "&t=" not in row["url"]:
            failures.append(f"{label}: url sin cita &t=")
        seconds = int(row["url"].rsplit("&t=", 1)[1].rstrip("s"))
        if not 0 <= seconds <= int(DURATION):
            failures.append(f"{label}: segundos fuera de rango: {seconds}")
        if len(row["text"]) >= FULL_CHARS:
            failures.append(f"{label}: chunk = transcript entero")
        if not row["text"].strip():
            failures.append(f"{label}: text vacío")


def main() -> int:
    failures: list[str] = []

    check(youtube_transcript_search(URL, "azulejos", top_k=3), "azulejos", failures)
    check(
        youtube_transcript_search(URL, "mermelada naranja", top_k=2),
        "mermelada naranja",
        failures,
    )

    index = TranscriptIndex(db_path=ROOT / "data" / "youtube.db")
    try:
        rows = index._conn.execute(  # noqa: SLF001
            "SELECT chunk_index, start, end, token_count "
            "FROM transcript_chunks WHERE video_id = ? ORDER BY chunk_index",
            (VIDEO_ID,),
        ).fetchall()
        print("--- chunks indexados ---")
        for row in rows:
            print(dict(row))
        if len(rows) < 2:
            failures.append("se esperaban >=2 chunks en un video de 566s")
        for row in rows:
            if not 500 <= row["token_count"] <= 1000:
                failures.append(
                    f"chunk {row['chunk_index']}: tokens "
                    f"{row['token_count']} fuera de [500,1000]"
                )
    finally:
        index.close()

    print("FAILURES:", failures if failures else "ninguna — VERIFICACIÓN OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
