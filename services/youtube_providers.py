"""Proveedores de transcripción con interfaz común (Fase 4, E1).

Cada proveedor implementa ``TranscriptProvider.fetch`` y el servicio los
recorre en orden (el primero que tenga éxito gana). Un proveedor sin
material lanza ``NoCaptionsAvailable`` para ceder el turno al siguiente;
cualquier otro ``TranscriptError`` se propaga.

Proveedores:

- ``YouTubeTranscriptApiProvider`` — captions vía youtube-transcript-api.
- ``YtDlpSubtitleProvider`` — subtítulos vía yt-dlp (fallback Fase 2).
- ``FasterWhisperProvider`` — audio + ASR local (NO va en el pipeline
  síncrono por defecto: el servicio nunca bloquea en ASR; el worker
  durable sigue siendo la vía async — ver decisión E1 en
  ``docs/DECISIONES.md``).
- ``ExternalAsrProvider`` — adaptador opcional deshabilitado por defecto
  (sin API keys en v1).

``TranscriptSegment`` vive aquí para evitar imports circulares con
``youtube_service`` (que lo re-exporta por compatibilidad).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from youtube_transcript_api import (
    AgeRestricted,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptList,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)

from services.youtube_asr import FasterWhisperTranscriber
from services.youtube_audio import YtDlpAudioDownloader
from services.youtube_errors import (
    AsrFailed,
    DurationExceeded,
    NoCaptionsAvailable,
    TranscriptError,
    VideoBlockedOrUnavailable,
)
from services.youtube_rate_limit import RateLimiter
from services.youtube_subtitles import YtDlpSubtitles

MAX_DURATION_SECONDS = 7200  # 2 horas (límite v1, igual que el servicio)


@dataclass
class TranscriptSegment:
    """Segmento con timestamps normalizados."""

    start: float
    end: float
    text: str


@dataclass
class ProviderResult:
    """Resultado normalizado de un proveedor."""

    segments: list[TranscriptSegment] = field(default_factory=list)
    language: str | None = None
    source: str = ""
    track_type: str = ""

    @property
    def duration_seconds(self) -> float:
        if not self.segments:
            return 0.0
        return max(seg.end for seg in self.segments)


def _map_library_error(exc: Exception, video_id: str) -> TranscriptError:
    """Convierte excepciones de youtube-transcript-api en errores del dominio."""
    if isinstance(exc, (RequestBlocked, IpBlocked)):
        return VideoBlockedOrUnavailable(
            "YouTube bloqueó la solicitud (rate limit o IP)",
            video_id=video_id,
            suggestion="Reintentar más tarde; revisar circuit breaker (Fase 4)",
        )
    if isinstance(exc, (VideoUnavailable, InvalidVideoId, VideoUnplayable, AgeRestricted)):
        return VideoBlockedOrUnavailable(
            f"Video no disponible: {exc}",
            video_id=video_id,
            suggestion="Verificar que la URL corresponde a un video público",
        )
    if isinstance(exc, TranscriptsDisabled):
        return NoCaptionsAvailable(
            "El creador deshabilitó los captions para este video",
            video_id=video_id,
            suggestion="Sin captions: ASR local disponible en Fase 2",
        )
    if isinstance(exc, NoTranscriptFound):
        return NoCaptionsAvailable(
            "No hay captions en los idiomas solicitados",
            video_id=video_id,
            suggestion="Probar otros idiomas o usar ASR (Fase 2)",
        )
    if isinstance(exc, YouTubeTranscriptApiException):
        return VideoBlockedOrUnavailable(
            f"Error de YouTube: {exc}",
            video_id=video_id,
        )
    return TranscriptError(f"Error inesperado: {exc}", video_id=video_id)


def _select_track(
    transcript_list: TranscriptList,
    languages: tuple[str, ...] | list[str],
) -> tuple[Any, str, str]:
    """Elige la mejor pista: manual > auto, idiomas pedidos en orden.

    Devuelve (transcript, language_code, track_type).
    """
    manual = dict(getattr(transcript_list, "_manually_created_transcripts", {}))
    generated = dict(getattr(transcript_list, "_generated_transcripts", {}))

    def _pick(pool: dict[str, Any]) -> tuple[Any, str] | None:
        for lang in languages:
            if lang in pool:
                return pool[lang], lang
        # variante por prefijo (es vs es-419, en vs en-US)
        for lang in languages:
            for code, tr in pool.items():
                if code.split("-")[0] == lang.split("-")[0]:
                    return tr, code
        if pool:
            code = next(iter(pool))
            return pool[code], code
        return None

    for pool, track_type in ((manual, "manual"), (generated, "auto")):
        picked = _pick(pool)
        if picked is not None:
            return picked[0], picked[1], track_type

    raise NoCaptionsAvailable(
        "No hay captions disponibles en este video",
        suggestion="Sin captions: ASR local disponible en Fase 2",
    )


class TranscriptProvider(ABC):
    """Interfaz común de proveedores de transcripción."""

    name: str = "base"
    enabled: bool = True

    @abstractmethod
    def fetch(
        self, video_id: str, languages: tuple[str, ...] | list[str],
    ) -> ProviderResult:
        """Devuelve la transcripción o lanza ``TranscriptError``.

        Sin material: ``NoCaptionsAvailable`` (cede el turno).
        """


class YouTubeTranscriptApiProvider(TranscriptProvider):
    """Captions vía youtube-transcript-api (primera ruta del pipeline)."""

    name = "youtube_captions"

    def __init__(
        self,
        api: YouTubeTranscriptApi | None = None,
        rate_limiter: RateLimiter | None = None,
        enabled: bool = True,
    ) -> None:
        self.api = api or YouTubeTranscriptApi()
        self.rate_limiter = rate_limiter
        self.enabled = enabled

    def fetch(
        self, video_id: str, languages: tuple[str, ...] | list[str],
    ) -> ProviderResult:
        # Prevención 429: el limiter vive en el proveedor que toca la red.
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        try:
            transcript_list = self.api.list(video_id)
            transcript, language_code, track_type = _select_track(
                transcript_list, languages,
            )
            fetched = transcript.fetch()
        except NoCaptionsAvailable:
            raise
        except TranscriptError:
            raise
        except Exception as exc:  # noqa: BLE001 — mapeamos al dominio
            raise _map_library_error(exc, video_id) from exc

        segments = [
            TranscriptSegment(
                start=float(snippet.start),
                end=float(snippet.start) + float(snippet.duration),
                text=snippet.text.strip(),
            )
            for snippet in fetched
        ]
        return ProviderResult(
            segments=segments,
            language=language_code,
            source="youtube_captions",
            track_type=track_type,
        )


class YtDlpSubtitleProvider(TranscriptProvider):
    """Subtítulos vía yt-dlp (fallback cuando no hay captions)."""

    name = "yt_dlp_subtitles"

    def __init__(
        self,
        subtitles: YtDlpSubtitles | None = None,
        enabled: bool = True,
    ) -> None:
        self.subtitles = subtitles if subtitles is not None else YtDlpSubtitles()
        self.enabled = enabled

    def fetch(
        self, video_id: str, languages: tuple[str, ...] | list[str],
    ) -> ProviderResult:
        try:
            subtitle_result = self.subtitles.fetch(video_id, languages)
        except TranscriptError:
            raise
        except Exception as exc:  # noqa: BLE001 — mapeamos al dominio
            raise _map_library_error(exc, video_id) from exc

        segments = [
            TranscriptSegment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=str(seg["text"]).strip(),
            )
            for seg in subtitle_result.segments
        ]
        return ProviderResult(
            segments=segments,
            language=subtitle_result.language,
            source=subtitle_result.source,
            track_type=subtitle_result.track_type,
        )


class FasterWhisperProvider(TranscriptProvider):
    """Audio + ASR local faster-whisper (vía síncrona, no durable).

    No participa del pipeline síncrono del servicio por defecto: un
    ``get_transcript`` nunca debe bloquear minutos en ASR (para eso
    existe el worker con jobs durables). Útil para health checks,
    scripts y futuros usos con enable explícito.
    """

    name = "faster_whisper"

    def __init__(
        self,
        downloader: Any | None = None,
        transcriber: Any | None = None,
        max_duration_seconds: int = MAX_DURATION_SECONDS,
        rate_limiter: RateLimiter | None = None,
        enabled: bool = True,
    ) -> None:
        self.downloader = (
            downloader if downloader is not None else YtDlpAudioDownloader()
        )
        self.transcriber = (
            transcriber if transcriber is not None else FasterWhisperTranscriber()
        )
        self.max_duration_seconds = max_duration_seconds
        self.rate_limiter = rate_limiter
        self.enabled = enabled

    def fetch(
        self, video_id: str, languages: tuple[str, ...] | list[str],
    ) -> ProviderResult:
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        audio = self.downloader.download(video_id)
        try:
            if audio.duration is not None and audio.duration > self.max_duration_seconds:
                raise DurationExceeded(
                    f"El video dura {audio.duration:.0f}s "
                    f"(máximo {self.max_duration_seconds}s)",
                    video_id=video_id,
                    suggestion="Los videos mayores a 2h no están soportados en v1",
                )
            # Autodetect de idioma (language=None), igual que el worker.
            asr = self.transcriber.transcribe(audio.path, language=None)
        finally:
            self.downloader.cleanup(audio)

        segments = [
            TranscriptSegment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=str(seg["text"]).strip(),
            )
            for seg in asr.segments
        ]
        if not segments:
            raise AsrFailed(
                "ASR no produjo segmentos (posible video sin habla)",
                video_id=video_id,
            )
        return ProviderResult(
            segments=segments,
            language=asr.language,
            source="faster_whisper",
            track_type="asr",
        )


class ExternalAsrProvider(TranscriptProvider):
    """Adaptador opcional para ASR externo (fuera del v1).

    Deshabilitado por defecto: v1 es 100% gratis/offline sin API keys.
    La interfaz queda lista para Fase 4+ si se configura un endpoint.
    """

    name = "external_asr"

    def __init__(self, enabled: bool = False, **config: Any) -> None:
        self.enabled = enabled
        self.config = dict(config)

    def fetch(
        self, video_id: str, languages: tuple[str, ...] | list[str],
    ) -> ProviderResult:
        raise TranscriptError(
            "Proveedor ASR externo no configurado (opcional, fuera del v1)",
            video_id=video_id,
            suggestion="Habilitar con configuración explícita o usar ASR local",
        )


def default_providers(
    api: YouTubeTranscriptApi | None = None,
    rate_limiter: RateLimiter | None = None,
    subtitles: YtDlpSubtitles | None = None,
    enable_subtitle_fallback: bool = True,
) -> list[TranscriptProvider]:
    """Pipeline síncrono por defecto: captions → subtítulos yt-dlp.

    El ASR (local o externo) no participa: el servicio síncrono nunca
    bloquea en transcripción pesada (decisión E1).
    """
    return [
        YouTubeTranscriptApiProvider(api=api, rate_limiter=rate_limiter),
        YtDlpSubtitleProvider(
            subtitles=subtitles, enabled=enable_subtitle_fallback,
        ),
    ]
