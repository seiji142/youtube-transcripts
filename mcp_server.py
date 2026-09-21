"""Servidor MCP propio de youtube-transcripts.

Expone la tool ``youtube_transcript`` (Fase 1: solo captions).
Independiente de brain-ai-01. Transporte: stdio.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from services.youtube_cache import TranscriptCache
from services.youtube_errors import TranscriptError
from services.youtube_service import YouTubeService

mcp = MCPServer(
    name="youtube-transcripts",
    description="Transcripciones de videos públicos de YouTube con timestamps",
    version="0.1.0",
)

_cache = TranscriptCache(db_path=Path("data") / "youtube.db")
_service = YouTubeService(cache=_cache)


@mcp.tool(
    name="youtube_transcript",
    description=(
        "Extrae la transcripción (con timestamps) de un video público de "
        "YouTube a partir de su URL. Solo captions en Fase 1 (sin ASR). "
        "Rechaza playlists, directos y videos >2h."
    ),
)
def youtube_transcript(
    url: str,
    languages: list[str] | None = None,
    include_timestamps: bool = True,
) -> dict[str, Any]:
    """Devuelve la transcripción o un error estructurado.

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
    except TranscriptError as exc:
        return exc.to_dict()
    except Exception as exc:  # noqa: BLE001 — nunca crashear el servidor
        return {
            "status": "error",
            "code": "transcript_error",
            "message": f"Error inesperado: {exc}",
        }


def main() -> None:
    """Punto de entrada: stdio transport para opencode/claude/etc."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
