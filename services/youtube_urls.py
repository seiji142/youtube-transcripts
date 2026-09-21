"""Parser seguro de URLs de YouTube.

Extrae el video_id de URLs públicas validando esquema, host whitelist,
ausencia de playlists/directos y formato de ID de 11 caracteres.
No usa subprocess ni shell=True: solo urllib.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from services.youtube_errors import InvalidYouTubeUrl

YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
})

_VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")


def _fail(message: str) -> None:
    raise InvalidYouTubeUrl(message)


def extract_video_id(url: str) -> str:
    """Devuelve el video_id de una URL de YouTube pública.

    Acepta /watch?v=, youtu.be/, /shorts/, /embed/.
    Rechaza playlists (?list=), directos (/live/), hosts no permitidos
    y IDs que no tengan 11 caracteres válidos.
    """
    if not isinstance(url, str) or not url.strip():
        _fail("La URL está vacía")

    parsed = urlparse(url.strip())

    if parsed.scheme not in {"http", "https"}:
        _fail("La URL debe utilizar HTTP o HTTPS")

    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        _fail("El host no pertenece a YouTube")

    query = parse_qs(parsed.query)
    if "list" in query:
        _fail("Las playlists no están soportadas en v1")

    path = parsed.path or ""

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = path.strip("/").split("/")[0] if path.strip("/") else ""
    elif path.startswith("/live/"):
        _fail("Los directos no están soportados en v1")
    elif path == "/watch":
        video_id = query.get("v", [""])[0]
    elif path.startswith("/shorts/"):
        parts = path.split("/")
        video_id = parts[2] if len(parts) > 2 else ""
    elif path.startswith("/embed/"):
        parts = path.split("/")
        video_id = parts[2] if len(parts) > 2 else ""
    else:
        _fail("Formato de URL de YouTube no reconocido")

    if not _VIDEO_ID_RE.fullmatch(video_id):
        _fail("ID de video inválido (se esperan 11 caracteres alfanuméricos, - o _)")

    return video_id


def is_valid_video_id(video_id: str) -> bool:
    """Indica si una cadena tiene formato de video_id de YouTube."""
    return isinstance(video_id, str) and bool(_VIDEO_ID_RE.fullmatch(video_id))
