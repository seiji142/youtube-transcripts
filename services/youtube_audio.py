"""Descarga de solo-audio con yt-dlp + FFmpeg (Fase 2, bloque C).

Cuando no existen captions ni subtítulos, la ruta ASR necesita el audio
del video. Este módulo descarga ``bestaudio`` con la API en-process de
yt-dlp (sin ``shell=True``) y convierte a WAV 16 kHz mono con FFmpeg
(postprocesador ``FFmpegExtractAudio``).

Garantías de seguridad:
- El ``outtmpl`` se construye internamente a partir de un video_id
  validado; el usuario no controla rutas de salida ni flags de yt-dlp.
- Cada descarga vive en un directorio temporal aislado (``mkdtemp``);
  ``cleanup()`` elimina el árbol completo.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from services.youtube_errors import AudioDownloadFailed

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_AUDIO_EXTS = {".wav", ".m4a", ".mp3", ".webm", ".opus", ".ogg", ".aac", ".flac"}
TEMP_PREFIX = "youtube_transcripts_"


def find_ffmpeg() -> str | None:
    """Devuelve la ruta absoluta de ``ffmpeg`` en PATH o None."""
    return shutil.which("ffmpeg")


@dataclass
class AudioDownloadResult:
    """Audio descargado y convertido, listo para ASR."""

    video_id: str
    path: Path
    work_dir: Path
    ext: str
    duration: float | None = None


class YtDlpAudioDownloader:
    """Descarga solo-audio de YouTube a un temporal aislado.

    Args:
        base_dir: Directorio base para temporales (default: temp del SO).
        ffmpeg_location: Ruta a ffmpeg/binario; autodetecta con None.
        ydl_options: Overrides de yt-dlp — solo para tests/inyección.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        ffmpeg_location: str | None = None,
        ydl_options: dict[str, Any] | None = None,
    ) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else Path(
            tempfile.gettempdir()
        )
        self._ffmpeg_location = ffmpeg_location if ffmpeg_location is not None else find_ffmpeg()
        self._extra_opts: dict[str, Any] = dict(ydl_options or {})

    @property
    def ffmpeg_location(self) -> str | None:
        return self._ffmpeg_location

    def download(self, video_id: str) -> AudioDownloadResult:
        """Descarga y convierte el audio del video a WAV.

        Lanza:
            AudioDownloadFailed — ID inválido, sin FFmpeg o fallo de red.
        """
        if not _VIDEO_ID_RE.match(video_id):
            raise AudioDownloadFailed(
                "video_id inválido para descarga de audio",
                video_id=video_id,
                suggestion="Usar IDs de 11 caracteres [A-Za-z0-9_-]",
            )
        if self._ffmpeg_location is None:
            raise AudioDownloadFailed(
                "FFmpeg no está instalado o no está en PATH",
                video_id=video_id,
                suggestion="Instalar con: winget install Gyan.FFmpeg",
            )

        self._base_dir.mkdir(parents=True, exist_ok=True)
        work_dir = Path(
            tempfile.mkdtemp(prefix=f"{TEMP_PREFIX}{video_id}_", dir=self._base_dir)
        )

        opts = self._build_opts(work_dir)
        url = f"https://www.youtube.com/watch?v={video_id}"
        duration: float | None = None

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            if isinstance(info, dict) and info.get("duration") is not None:
                duration = float(info["duration"])
        except (DownloadError, ExtractorError) as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise AudioDownloadFailed(
                f"yt-dlp no pudo descargar el audio: {exc}",
                video_id=video_id,
                suggestion="Verificar que el video sea público y esté disponible",
            ) from exc
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

        path = self._locate_audio(work_dir, video_id)
        return AudioDownloadResult(
            video_id=video_id,
            path=path,
            work_dir=work_dir,
            ext=path.suffix.lstrip(".").lower(),
            duration=duration,
        )

    def cleanup(self, result: AudioDownloadResult) -> None:
        """Elimina el directorio temporal de una descarga (idempotente)."""
        shutil.rmtree(result.work_dir, ignore_errors=True)

    def _build_opts(self, work_dir: Path) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": self._ffmpeg_location,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "wav"},
            ],
        }
        opts.update(self._extra_opts)
        return opts

    @staticmethod
    def _locate_audio(work_dir: Path, video_id: str) -> Path:
        wav = work_dir / f"{video_id}.wav"
        if wav.is_file():
            return wav
        fallbacks = sorted(
            p for p in work_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _AUDIO_EXTS
        )
        if fallbacks:
            return fallbacks[0]
        shutil.rmtree(work_dir, ignore_errors=True)
        raise AudioDownloadFailed(
            "FFmpeg no produjo ningún archivo de audio",
            video_id=video_id,
            suggestion="Verificar instalación de FFmpeg y formato bestaudio",
        )
