"""Orquestador de transcripciones de YouTube (Fase 1: solo captions).

Pipeline Fase 1: URL validada → caché → youtube-transcript-api.
Selección de pistas: manual > automática, idioma pedido > original.
Límite de duración 2h. Sin ASR (eso es Fase 2).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
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

from services.youtube_cache import TranscriptCache
from services.youtube_errors import (
    DurationExceeded,
    NoCaptionsAvailable,
    TranscriptError,
    VideoBlockedOrUnavailable,
)
from services.youtube_urls import extract_video_id

MAX_DURATION_SECONDS = 7200  # 2 horas
DEFAULT_LANGUAGES = ("es", "en")


@dataclass
class TranscriptSegment:
    """Segmento con timestamps normalizados."""

    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    """Resultado normalizado de una transcripción."""

    video_id: str
    language: str | None
    source: str
    track_type: str
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(seg.text for seg in self.segments)

    @property
    def duration_seconds(self) -> float:
        if not self.segments:
            return 0.0
        return max(seg.end for seg in self.segments)

    def to_dict(self, include_timestamps: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "completed",
            "video_id": self.video_id,
            "language": self.language,
            "source": self.source,
            "track_type": self.track_type,
            "duration_seconds": self.duration_seconds,
            "text": self.text,
        }
        if include_timestamps:
            payload["segments"] = [asdict(seg) for seg in self.segments]
        return payload


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


class YouTubeService:
    """Extrae transcripciones con captions (Fase 1)."""

    def __init__(
        self,
        cache: TranscriptCache | None = None,
        languages: tuple[str, ...] = DEFAULT_LANGUAGES,
        max_duration_seconds: int = MAX_DURATION_SECONDS,
        api: YouTubeTranscriptApi | None = None,
    ) -> None:
        self.cache = cache
        self.languages = languages
        self.max_duration_seconds = max_duration_seconds
        self._api = api or YouTubeTranscriptApi()

    def get_transcript(
        self,
        url: str,
        languages: list[str] | None = None,
        include_timestamps: bool = True,
    ) -> TranscriptResult:
        """Extrae la transcripción de un video público de YouTube.

        Lanza:
            InvalidYouTubeUrl | NoCaptionsAvailable |
            VideoBlockedOrUnavailable | DurationExceeded | TranscriptError
        """
        video_id = extract_video_id(url)
        langs = tuple(languages) if languages else self.languages
        lang_key = "+".join(langs)

        if self.cache is not None:
            for track_type in ("manual", "auto"):
                cached = self.cache.get(video_id, lang_key, track_type)
                if cached is not None:
                    return self._result_from_cache(video_id, cached)

        try:
            transcript_list = self._api.list(video_id)
            transcript, language_code, track_type = _select_track(
                transcript_list, langs,
            )
            fetched = transcript.fetch()
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

        result = TranscriptResult(
            video_id=video_id,
            language=language_code,
            source="youtube_captions",
            track_type=track_type,
            segments=segments,
        )

        if result.duration_seconds > self.max_duration_seconds:
            raise DurationExceeded(
                f"El video dura {result.duration_seconds:.0f}s "
                f"(máximo {self.max_duration_seconds}s)",
                video_id=video_id,
                suggestion="Los videos mayores a 2h no están soportados en v1",
            )

        if self.cache is not None:
            self.cache.set(
                video_id, lang_key, track_type,
                segments=[asdict(s) for s in segments],
                language_code=language_code,
                source="youtube_captions",
            )

        return result

    @staticmethod
    def _result_from_cache(video_id: str, cached: dict[str, Any]) -> TranscriptResult:
        segments = [
            TranscriptSegment(
                start=float(s["start"]),
                end=float(s["end"]),
                text=s["text"],
            )
            for s in cached["segments"]
        ]
        return TranscriptResult(
            video_id=video_id,
            language=cached.get("language_code"),
            source=cached.get("source") or "youtube_captions",
            track_type=cached.get("track_type") or "manual",
            segments=segments,
        )
