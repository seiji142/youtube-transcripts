"""Errores estructurados del pipeline de transcripts de YouTube.

Cada error expone un ``code`` estable para que la capa MCP/consumidora
pueda reaccionar sin parsear mensajes. El requisito clave es distinguir
siempre "sin captions" de "acceso bloqueado".
"""
from __future__ import annotations

from typing import Any


class TranscriptError(Exception):
    """Base de todos los errores del dominio youtube-transcripts."""

    code: str = "transcript_error"

    def __init__(self, message: str, video_id: str | None = None,
                 suggestion: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.video_id = video_id
        self.suggestion = suggestion

    def to_dict(self) -> dict[str, Any]:
        """Representación estructurada para respuestas MCP."""
        payload: dict[str, Any] = {
            "status": "error",
            "code": self.code,
            "message": self.message,
        }
        if self.video_id is not None:
            payload["video_id"] = self.video_id
        if self.suggestion is not None:
            payload["suggestion"] = self.suggestion
        return payload


class InvalidYouTubeUrl(TranscriptError):
    """URL malformada, host no permitido, playlist o directo."""

    code = "invalid_url"


class NoCaptionsAvailable(TranscriptError):
    """El video no tiene captions (ni manuales ni automáticas)."""

    code = "no_captions"


class VideoBlockedOrUnavailable(TranscriptError):
    """Bloqueo, rate limit (429) o video no disponible."""

    code = "blocked"


class DurationExceeded(TranscriptError):
    """El video supera la duración máxima permitida (2h en v1)."""

    code = "duration_exceeded"
