"""Circuit breaker + métricas por proveedor (Fase 4, E2).

El breaker es la **red de seguridad** tras 429/bloqueos, no la
prevención primaria (esa es el ``RateLimiter`` de Fase 1, ver TAREAS
§4 incidente 429). Cada proveedor del pipeline tiene su propio
breaker: tras ``failure_threshold`` fallos en ``window_seconds``, el
breaker abre y las llamadas fallan rápido con ``ProviderUnavailable``
durante ``cooldown_seconds`` (con jitter ±``jitter_ratio`` para no
reintentar en manada). Una llamada de prueba (half-open) que tiene
éxito lo cierra; si falla, reabre.

``NoCaptionsAvailable`` ("vacío") cuenta como **éxito** para el
breaker: el proveedor respondió, solo no tenía material.

El backoff con jitter vive aquí (cooldown), no en ``JobStore``: el
backoff de jobs es determinista a propósito (sus tests fijan valores
exactos) — ver decisión E2 en ``docs/DECISIONES.md``.
"""
from __future__ import annotations

import random
import threading
import time
from typing import Any, Callable, TypeVar

from services.youtube_errors import NoCaptionsAvailable, ProviderUnavailable

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_WINDOW_SECONDS = 60.0
DEFAULT_COOLDOWN_SECONDS = 300.0
DEFAULT_JITTER_RATIO = 0.2

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"

T = TypeVar("T")


class CircuitBreaker:
    """Breaker por proveedor (thread-safe, reloj y RNG inyectables)."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        jitter_ratio: float = DEFAULT_JITTER_RATIO,
        clock: Callable[[], float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold debe ser >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds debe ser > 0")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds debe ser > 0")
        if not 0.0 <= jitter_ratio < 1.0:
            raise ValueError("jitter_ratio debe estar en [0, 1)")
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.jitter_ratio = jitter_ratio
        self._clock = clock or time.monotonic
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._failures: list[float] = []
        self._state = STATE_CLOSED
        self._opened_at = 0.0
        self._cooldown = cooldown_seconds

    @property
    def state(self) -> str:
        """Estado actual (promueve half-open si venció el cooldown)."""
        with self._lock:
            self._maybe_half_open()
            return self._state

    @property
    def failure_count(self) -> int:
        """Fallos dentro de la ventana actual."""
        with self._lock:
            self._prune()
            return len(self._failures)

    def allow(self) -> bool:
        """True si la llamada puede pasar (closed o half-open vencido)."""
        with self._lock:
            self._maybe_half_open()
            return self._state in (STATE_CLOSED, STATE_HALF_OPEN)

    def record_success(self) -> None:
        """Éxito (o "vacío"): cierra el breaker y limpia fallos."""
        with self._lock:
            self._failures.clear()
            self._state = STATE_CLOSED

    def record_failure(self) -> None:
        """Fallo: abre el breaker si alcanza el umbral en ventana."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._failures.append(now)
            if self._state == STATE_HALF_OPEN or len(self._failures) >= self.failure_threshold:
                self._open(now)

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Ejecuta ``fn`` bajo el breaker o lanza ``ProviderUnavailable``.

        ``NoCaptionsAvailable`` cuenta como éxito (el proveedor
        respondió) y se propaga igual que cualquier otro error.
        """
        if not self.allow():
            raise ProviderUnavailable(
                f"Proveedor {self.name} temporalmente deshabilitado "
                "(circuit breaker abierto)",
                suggestion="Reintentar cuando cierre el cooldown",
            )
        try:
            result = fn(*args, **kwargs)
        except NoCaptionsAvailable:
            self.record_success()
            raise
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def _prune(self, now: float | None = None) -> None:
        cutoff = (now if now is not None else self._clock()) - self.window_seconds
        self._failures = [ts for ts in self._failures if ts > cutoff]

    def _maybe_half_open(self) -> None:
        if self._state == STATE_OPEN and self._clock() - self._opened_at >= self._cooldown:
            self._state = STATE_HALF_OPEN

    def _open(self, now: float) -> None:
        self._state = STATE_OPEN
        self._opened_at = now
        jitter = 1.0 + self._rng.uniform(-self.jitter_ratio, self.jitter_ratio)
        self._cooldown = self.cooldown_seconds * jitter


class ProviderMetrics:
    """Contadores por proveedor + último error (thread-safe, en memoria)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, dict[str, Any]] = {}

    def record(
        self,
        provider: str,
        outcome: str,
        latency_s: float = 0.0,
        error_code: str | None = None,
    ) -> None:
        """Registra una llamada: ``success`` | ``empty`` | ``failure`` | ``rejected``."""
        with self._lock:
            stats = self._stats.setdefault(provider, self._blank())
            stats["calls"] += 1
            if outcome == "success":
                stats["success"] += 1
            elif outcome == "empty":
                stats["empties"] += 1
            elif outcome == "failure":
                stats["failures"] += 1
                stats["last_error"] = error_code
            elif outcome == "rejected":
                stats["rejected"] += 1
            stats["last_latency_s"] = latency_s

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Copia del estado actual por proveedor."""
        with self._lock:
            return {name: dict(stats) for name, stats in self._stats.items()}

    @staticmethod
    def _blank() -> dict[str, Any]:
        return {
            "calls": 0,
            "success": 0,
            "empties": 0,
            "failures": 0,
            "rejected": 0,
            "last_error": None,
            "last_latency_s": 0.0,
        }
