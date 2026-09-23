"""Servidor MCP propio de youtube-transcripts.

Tools (Fase 2):
- ``youtube_transcript`` — extracción síncrona (captions → subtítulos);
  sin captions encola un job ASR y responde ``processing`` (D1).
- ``youtube_transcript_status`` — estado de un job ASR.
- ``youtube_transcript_read`` — lectura paginada por rango en segundos
  (D3: ``start``/``end`` en segundos + ``max_chars`` como tope).

Al arrancar (``main``) lanza el worker ASR como thread daemon en el
mismo proceso (decisión D1). Independiente de brain-ai-01. stdio.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from services.youtube_cache import TranscriptCache
from services.youtube_errors import NoCaptionsAvailable, TranscriptError
from services.youtube_jobs import JobStore
from services.youtube_service import YouTubeService
from services.youtube_urls import extract_video_id
from services.youtube_worker import AsrWorker

mcp = MCPServer(
    name="youtube-transcripts",
    description="Transcripciones de videos públicos de YouTube con timestamps",
    version="0.1.0",
)

DB_PATH = Path("data") / "youtube.db"

_cache = TranscriptCache(db_path=DB_PATH)
_service = YouTubeService(cache=_cache)
_jobs = JobStore(db_path=DB_PATH)
_worker = AsrWorker(
    jobs=_jobs,
    cache=_cache,
    rate_limiter=_service.rate_limiter,
)

_CLIENT_STATUS = {
    "pending": "processing",
    "processing": "processing",
    "completed": "completed",
    "failed": "error",
}


def _enqueue_asr(url: str, languages: list[str] | None) -> dict[str, Any]:
    """Encola (o consulta) el job ASR para un video sin captions."""
    video_id = extract_video_id(url)
    langs = list(languages) if languages else list(_service.languages)
    job = _jobs.create_or_get(video_id, langs)

    if job["status"] == "completed":
        entry = _cache.get(video_id, job["lang_key"], "asr")
        if entry is not None:
            result = YouTubeService._result_from_cache(video_id, entry)  # noqa: SLF001
            return result.to_dict()
        # Completado pero el resultado ya no está (TTL): re-encolar.
        job = _jobs.requeue(job["job_id"])

    return {
        "status": "processing",
        "job_id": job["job_id"],
        "video_id": video_id,
        "detail": "Sin captions: transcripción ASR local en cola",
        "poll_with": "youtube_transcript_status",
    }


@mcp.tool(
    name="youtube_transcript",
    description=(
        "Extrae la transcripción (con timestamps) de un video público de "
        "YouTube a partir de su URL. Si no hay captions ni subtítulos, "
        "encola un job de ASR local y devuelve status=processing con "
        "job_id (consultar con youtube_transcript_status). Rechaza "
        "playlists, directos y videos >2h."
    ),
)
def youtube_transcript(
    url: str,
    languages: list[str] | None = None,
    include_timestamps: bool = True,
) -> dict[str, Any]:
    """Devuelve la transcripción, un processing con job_id o un error.

    Args:
        url: URL pública de YouTube (watch, youtu.be, shorts, embed).
        languages: Idiomas preferidos en orden. Default ["es", "en"].
        include_timestamps: Si es False, omite el arreglo de segmentos.
    """
    try:
        result = _service.get_transcript(
            url=url,
            languages=languages,
            include_timestamps=include_timestamps,
        )
        return result.to_dict(include_timestamps=include_timestamps)
    except NoCaptionsAvailable:
        try:
            return _enqueue_asr(url, languages)
        except TranscriptError as exc:
            return exc.to_dict()
    except TranscriptError as exc:
        return exc.to_dict()
    except Exception as exc:  # noqa: BLE001 — nunca crashear el servidor
        return {
            "status": "error",
            "code": "transcript_error",
            "message": f"Error inesperado: {exc}",
        }


@mcp.tool(
    name="youtube_transcript_status",
    description=(
        "Estado de un job de transcripción ASR. Acepta job_id (devuelto "
        "por youtube_transcript) o la URL del video. status: processing | "
        "completed | error."
    ),
)
def youtube_transcript_status(
    job_id: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Consulta el estado de un job ASR.

    Args:
        job_id: Job devuelto por youtube_transcript (processing).
        url: URL del video como alternativa al job_id.
    """
    if not job_id and not url:
        return {
            "status": "error",
            "code": "invalid_request",
            "message": "Proporcionar job_id o url",
        }

    try:
        if job_id:
            job = _jobs.get(job_id=job_id)
        else:
            video_id = extract_video_id(url or "")
            job = _jobs.get(video_id=video_id)
    except TranscriptError as exc:
        return exc.to_dict()

    if job is None:
        return {
            "status": "error",
            "code": "job_not_found",
            "message": "No existe job para ese job_id/video",
        }

    payload: dict[str, Any] = {
        "status": _CLIENT_STATUS.get(job["status"], "error"),
        "job_status": job["status"],
        "job_id": job["job_id"],
        "video_id": job["video_id"],
        "stage": job["stage"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
    }
    if job["status"] == "failed":
        payload["code"] = job["error_code"] or "transcript_error"
        payload["message"] = job["error_message"] or "Job fallido"
    elif job["status"] == "completed":
        payload["detail"] = "Transcripción disponible"
        payload["read_with"] = "youtube_transcript_read"
    return payload


@mcp.tool(
    name="youtube_transcript_read",
    description=(
        "Lee un tramo de la transcripción de un video ya extraída "
        "(captions o ASR). start/end en SEGUNDOS (rango del video), "
        "max_chars tope de caracteres del texto devuelto (mínimo 1 "
        "segmento). Ideal para videos largos sin devolver todo el texto."
    ),
)
def youtube_transcript_read(
    video_id: str,
    start: float = 0.0,
    end: float | None = None,
    max_chars: int = 4000,
    include_timestamps: bool = True,
) -> dict[str, Any]:
    """Devuelve los segmentos de un rango [start, end) en segundos.

    Args:
        video_id: ID de 11 caracteres del video.
        start: Inicio en segundos (inclusive).
        end: Fin en segundos (exclusive); None = hasta el final.
        max_chars: Tope de caracteres; siempre al menos 1 segmento.
        include_timestamps: Si es False, omite start/end por segmento.
    """
    if start < 0:
        return {
            "status": "error",
            "code": "invalid_range",
            "message": "start no puede ser negativo",
        }
    if end is not None and end <= start:
        return {
            "status": "error",
            "code": "invalid_range",
            "message": "end debe ser mayor que start",
        }
    if max_chars < 1:
        return {
            "status": "error",
            "code": "invalid_range",
            "message": "max_chars debe ser >= 1",
        }

    entry = _cache.get_any(video_id)
    if entry is None:
        return {
            "status": "error",
            "code": "not_found",
            "message": "No hay transcripción para ese video",
            "video_id": video_id,
        }

    taken: list[dict[str, Any]] = []
    truncated = False
    total = 0
    segments = entry["segments"]
    for index, seg in enumerate(segments):
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        if seg_end <= start:
            continue
        if end is not None and seg_start >= end:
            break
        text = str(seg["text"])
        extra = len(text) + (1 if taken else 0)
        if taken and total + extra > max_chars:
            truncated = True
            break
        taken.append(seg)
        total += extra
        if total >= max_chars and index < len(segments) - 1:
            # cabe exacto pero queda más material → informar corte
            remaining = segments[index + 1:]
            if any(
                float(s["end"]) > start
                and (end is None or float(s["start"]) < end)
                for s in remaining
            ):
                truncated = True

    text = "\n".join(str(seg["text"]) for seg in taken)
    payload: dict[str, Any] = {
        "status": "completed",
        "video_id": video_id,
        "language": entry.get("language_code"),
        "source": entry.get("source"),
        "range": {"start": start, "end": end},
        "chars": len(text),
        "truncated": truncated,
        "text": text,
    }
    if include_timestamps:
        payload["segments"] = [
            {
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": str(seg["text"]),
            }
            for seg in taken
        ]
    return payload


def main() -> None:
    """Punto de entrada: worker daemon + stdio transport."""
    if os.environ.get("YOUTUBE_WORKER", "1") != "0":
        threading.Thread(
            target=_worker.run_forever,
            kwargs={"poll_interval": 2.0},
            daemon=True,
            name="youtube-asr-worker",
        ).start()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
