"""Orquestador de transcripciones de YouTube.

Pipeline: URL validada → caché → proveedores en orden
(``YouTubeTranscriptApiProvider`` → ``YtDlpSubtitleProvider``; el
primero que tenga éxito gana — Fase 4, E1). Sin material en ningún
proveedor: ``NoCaptionsAvailable`` (la capa MCP encola ASR).
Selección de pistas: manual > automática, idioma pedido > original.
Límite de duración 2h.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi

from services.youtube_breaker import CircuitBreaker, ProviderMetrics
from services.youtube_cache import TranscriptCache
from services.youtube_errors import (
    DurationExceeded,
    NoCaptionsAvailable,
    ProviderUnavailable,
    TranscriptError,
)
from services.youtube_providers import (
    ProviderResult,
    TranscriptProvider,
    TranscriptSegment,
    _map_library_error,
    _select_track,
    default_providers,
)
from services.youtube_rate_limit import RateLimiter
from services.youtube_subtitles import YtDlpSubtitles
from services.youtube_urls import extract_video_id

MAX_DURATION_SECONDS = 7200  # 2 horas
DEFAULT_LANGUAGES = ("es", "en")

__all__ = [
    "TranscriptSegment",
    "TranscriptResult",
    "YouTubeService",
    "MAX_DURATION_SECONDS",
    "DEFAULT_LANGUAGES",
    "ProviderResult",
    "TranscriptProvider",
    "_map_library_error",
    "_select_track",
]


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


class YouTubeService:
    """Extrae transcripciones recorriendo los proveedores en orden."""

    def __init__(
        self,
        cache: TranscriptCache | None = None,
        languages: tuple[str, ...] = DEFAULT_LANGUAGES,
        max_duration_seconds: int = MAX_DURATION_SECONDS,
        api: YouTubeTranscriptApi | None = None,
        rate_limiter: RateLimiter | None = None,
        subtitles: YtDlpSubtitles | None = None,
        enable_subtitle_fallback: bool = True,
        providers: list[TranscriptProvider] | None = None,
        breakers: dict[str, CircuitBreaker] | None = None,
        metrics: ProviderMetrics | None = None,
        enable_breaker: bool = True,
    ) -> None:
        self.cache = cache
        self.languages = languages
        self.max_duration_seconds = max_duration_seconds
        self._api = api or YouTubeTranscriptApi()
        # Rate limiter preventivo (1s / 10-min); None o enabled=False
        # para tests unitarios con mock. Vive en el proveedor que toca
        # la red; se conserva aquí por compatibilidad (mcp_server y
        # tests lo comparten con el worker).
        self.rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()
        # Fallback yt-dlp (Fase 2): inyectable para tests; se desactiva
        # con enable_subtitle_fallback=False para no depender de red.
        self._subtitles = subtitles if subtitles is not None else YtDlpSubtitles()
        self._enable_subtitle_fallback = enable_subtitle_fallback
        # Pipeline (Fase 4, E1): inyectable para tests; por defecto
        # captions → subtítulos con los componentes de arriba.
        self.providers = (
            providers
            if providers is not None
            else default_providers(
                api=self._api,
                rate_limiter=self.rate_limiter,
                subtitles=self._subtitles,
                enable_subtitle_fallback=enable_subtitle_fallback,
            )
        )
        # Resiliencia (Fase 4, E2): un breaker por proveedor + métricas
        # compartidas; desactivable con enable_breaker=False (tests).
        self.metrics = metrics if metrics is not None else ProviderMetrics()
        self.breakers = (
            breakers
            if breakers is not None
            else {p.name: CircuitBreaker(p.name) for p in self.providers}
        )
        self.enable_breaker = enable_breaker

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

        # Pipeline de proveedores (Fase 4, E1+E2): el primero que tenga
        # éxito gana; NoCaptionsAvailable cede el turno al siguiente;
        # el breaker abierto salta el proveedor (fail fast).
        last_empty: NoCaptionsAvailable | None = None
        rejected: list[str] = []
        for provider in self.providers:
            if not provider.enabled:
                continue
            breaker = self.breakers.get(provider.name) if self.enable_breaker else None
            if breaker is not None and not breaker.allow():
                self.metrics.record(provider.name, "rejected")
                rejected.append(provider.name)
                continue
            started = time.perf_counter()
            try:
                fetched = provider.fetch(video_id, langs)
            except NoCaptionsAvailable as exc:
                self.metrics.record(
                    provider.name, "empty", time.perf_counter() - started,
                )
                if breaker is not None:
                    breaker.record_success()
                last_empty = exc
                continue
            except TranscriptError as exc:
                self.metrics.record(
                    provider.name, "failure", time.perf_counter() - started,
                    error_code=exc.code,
                )
                if breaker is not None:
                    breaker.record_failure()
                raise
            self.metrics.record(
                provider.name, "success", time.perf_counter() - started,
            )
            if breaker is not None:
                breaker.record_success()
            return self._store_result(video_id, lang_key, fetched)

        if rejected and last_empty is None:
            raise ProviderUnavailable(
                f"Proveedores no disponibles: {', '.join(rejected)} "
                "(circuit breaker abierto)",
                video_id=video_id,
                suggestion="Esperar al cooldown y reintentar",
            )
        raise last_empty or NoCaptionsAvailable(
            "No hay captions disponibles en este video",
            video_id=video_id,
            suggestion="Sin captions: ASR local disponible en Fase 2",
        )

    def _store_result(
        self, video_id: str, lang_key: str, fetched: ProviderResult,
    ) -> TranscriptResult:
        """Valida duración, cachea y devuelve el resultado normalizado."""
        result = TranscriptResult(
            video_id=video_id,
            language=fetched.language,
            source=fetched.source,
            track_type=fetched.track_type,
            segments=fetched.segments,
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
                video_id, lang_key, result.track_type,
                segments=[asdict(s) for s in result.segments],
                language_code=result.language,
                source=result.source,
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
