"""Fallback de subtítulos vía yt-dlp (Fase 2).

Cuando ``youtube-transcript-api`` no encuentra captions, este módulo
lista y descarga subtítulos (VTT) del video usando la API de yt-dlp
(sin ``shell=True``; la librería se invoca en-process).

El parser VTT soporta cues multi-línea, timestamps con/sin horas,
marcas inline de auto-captions (``<c>``, ``<00:00:01.000>``) y el
modo "rolling" de YouTube (texto que se repite y crece cue a cue).
"""
from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from services.youtube_errors import NoCaptionsAvailable, VideoBlockedOrUnavailable

_SOURCE = "yt_dlp_subtitles"
_REQUEST_TIMEOUT = 30

_TIMING_RE = re.compile(
    r"(?:(?P<h1>\d{1,}):)?(?P<m1>\d{2}):(?P<s1>\d{2})[.,](?P<ms1>\d{3})"
    r"\s*-->\s*"
    r"(?:(?P<h2>\d{1,}):)?(?P<m2>\d{2}):(?P<s2>\d{2})[.,](?P<ms2>\d{3})",
)
_TAG_RE = re.compile(r"<[^>]+>")
_SKIP_DIRECTIVES = ("NOTE", "STYLE", "REGION")


@dataclass
class SubtitleResult:
    """Subtítulo descargado y normalizado (segmentos crudos)."""

    language: str
    track_type: str  # "manual" | "auto"
    segments: list[dict[str, Any]]
    source: str = _SOURCE


def _ts_to_seconds(hours: str | None, minutes: str, seconds: str, millis: str) -> float:
    h = int(hours) if hours else 0
    return h * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def _clean_text(raw: str) -> str:
    """Elimina marcas inline de VTT/YouTube y normaliza espacios."""
    no_tags = _TAG_RE.sub(" ", raw)
    return " ".join(no_tags.split())


def _iter_cue_blocks(content: str) -> list[str]:
    """Divide VTT en bloques de cue (timing + texto), omitiendo directivas."""
    blocks: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if stripped.startswith(_SKIP_DIRECTIVES):
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if stripped == "WEBVTT" or stripped.startswith(("Kind:", "Language:")):
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def parse_vtt(content: str, rolling: bool = False) -> list[dict[str, Any]]:
    """Parsea contenido WebVTT a segmentos ``{start, end, text}``.

    Args:
        content: Cuerpo VTT completo.
        rolling: Si True, aplica deduplicación de auto-captions de
            YouTube (cada cue repite el texto anterior y lo extiende).
    """
    cues: list[tuple[float, float, str]] = []

    for block in _iter_cue_blocks(content):
        lines = block.splitlines()
        timing_idx = None
        timing_match = None
        for i, line in enumerate(lines):
            match = _TIMING_RE.search(line)
            if match:
                timing_idx = i
                timing_match = match
                break
        if timing_idx is None or timing_match is None:
            continue

        start = _ts_to_seconds(
            timing_match.group("h1"), timing_match.group("m1"),
            timing_match.group("s1"), timing_match.group("ms1"),
        )
        end = _ts_to_seconds(
            timing_match.group("h2"), timing_match.group("m2"),
            timing_match.group("s2"), timing_match.group("ms2"),
        )
        text = _clean_text("\n".join(lines[timing_idx + 1:]))
        if text:
            cues.append((start, end, text))

    if not rolling:
        return [
            {"start": s, "end": e, "text": t}
            for s, e, t in cues
        ]

    segments: list[dict[str, Any]] = []
    for start, end, text in cues:
        if segments:
            prev = segments[-1]
            if text == prev["text"]:
                prev["end"] = end
                continue
            if text.startswith(prev["text"]):
                prev["end"] = end
                prev["text"] = text
                continue
            if prev["text"].startswith(text):
                prev["end"] = max(prev["end"], end)
                continue
        segments.append({"start": start, "end": end, "text": text})
    return segments


def _pick_track(
    manual: dict[str, Any],
    auto: dict[str, Any],
    languages: tuple[str, ...],
) -> tuple[str, str] | None:
    """Elige pista: manual > auto, idiomas pedidos > variante por prefijo > cualquiera."""
    for pool, track_type in ((manual, "manual"), (auto, "auto")):
        if not pool:
            continue
        for lang in languages:
            if lang in pool:
                return lang, track_type
        for lang in languages:
            for code in pool:
                if code.split("-")[0] == lang.split("-")[0]:
                    return code, track_type
        code = next(iter(pool))
        return code, track_type
    return None


def _best_vtt_url(formats: list[dict[str, Any]]) -> str:
    """Prefiere formato ``vtt``; si no, el primero con URL."""
    for fmt in formats:
        if fmt.get("ext") == "vtt" and fmt.get("url"):
            return str(fmt["url"])
    for fmt in formats:
        if fmt.get("url"):
            return str(fmt["url"])
    raise NoCaptionsAvailable("El subtítulo no tiene URL descargable")


class YtDlpSubtitles:
    """Cliente de subtítulos de YouTube basado en yt-dlp."""

    def __init__(self, ydl_options: dict[str, Any] | None = None) -> None:
        self._base_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        if ydl_options:
            self._base_opts.update(ydl_options)

    def list_tracks(
        self, video_id: str, languages: tuple[str, ...] = ("es", "en"),
    ) -> tuple[str, str] | None:
        """Devuelve ``(language, track_type)`` de la mejor pista disponible o None."""
        info = self._extract(video_id)
        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        return _pick_track(manual, auto, languages)

    def fetch(
        self, video_id: str, languages: tuple[str, ...] = ("es", "en"),
    ) -> SubtitleResult:
        """Descarga y parsea el mejor subtítulo del video.

        Lanza:
            NoCaptionsAvailable | VideoBlockedOrUnavailable
        """
        info = self._extract(video_id)
        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}

        picked = _pick_track(manual, auto, languages)
        if picked is None:
            raise NoCaptionsAvailable(
                "yt-dlp no encontró subtítulos (ni manuales ni automáticos)",
                video_id=video_id,
                suggestion="Sin subtítulos: ASR local (faster-whisper) en Fase 2",
            )

        lang, track_type = picked
        pool = manual if track_type == "manual" else auto
        url = _best_vtt_url(pool[lang])
        content = self._download_text(url)
        segments = parse_vtt(content, rolling=(track_type == "auto"))
        if not segments:
            raise NoCaptionsAvailable(
                "El subtítulo descargado no contiene cues válidos",
                video_id=video_id,
                suggestion="Probar otro idioma o usar ASR (Fase 2)",
            )

        return SubtitleResult(
            language=lang,
            track_type=track_type,
            segments=segments,
        )

    def _extract(self, video_id: str) -> dict[str, Any]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with YoutubeDL(self._base_opts) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
        except (DownloadError, ExtractorError) as exc:
            raise VideoBlockedOrUnavailable(
                f"yt-dlp no pudo inspeccionar el video: {exc}",
                video_id=video_id,
                suggestion="Verificar que el video sea público y esté disponible",
            ) from exc
        if not isinstance(info, dict):
            raise VideoBlockedOrUnavailable(
                "yt-dlp devolvió metadatos inválidos",
                video_id=video_id,
            )
        return info

    @staticmethod
    def _download_text(url: str) -> str:
        request = urllib.request.Request(  # noqa: S310 — URL de CDN de YouTube vía yt-dlp
            url,
            headers={"User-Agent": "youtube-transcripts/0.1"},
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")
