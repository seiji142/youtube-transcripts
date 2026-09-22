"""Rate limiter preventivo para llamadas a YouTube.

Previene HTTP 429 / IpBlocked por volumen (incidente 21/09/2026:
~25 videos en ráfaga sin pausa → bloqueo). Umbral YouTube no
publicado; consenso comunidad: ≥1s entre requests.

Defaults: 1s mínimo entre requests + máx 10 req / 60s.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    """Limita la tasa de llamadas a YouTube (prevención, no reacción).

    Args:
        min_interval_seconds: espera mínima entre llamadas consecutivas.
        max_requests: máximo de llamadas en la ventana.
        window_seconds: duración de la ventana (segundos).
        enabled: si es False, ``acquire()`` no espera (tests/mock).
    """

    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        max_requests: int = 10,
        window_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds no puede ser negativo")
        if max_requests < 1:
            raise ValueError("max_requests debe ser >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds debe ser >= 1")

        self.min_interval_seconds = min_interval_seconds
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.enabled = enabled

        self._lock = threading.Lock()
        self._last_acquire: float | None = None
        self._window_start: float | None = None
        self._window_count: int = 0

    def acquire(self) -> float:
        """Bloquea hasta que toque la siguiente llamada.

        Devuelve los segundos que esperó (0.0 si no esperó ni estaba
        deshabilitado).
        """
        if not self.enabled:
            return 0.0

        waited = 0.0
        with self._lock:
            now = time.monotonic()

            # 1) intervalo mínimo entre llamadas consecutivas
            if self._last_acquire is not None:
                since_last = now - self._last_acquire
                if since_last < self.min_interval_seconds:
                    sleep_for = self.min_interval_seconds - since_last
                    time.sleep(sleep_for)
                    waited += sleep_for
                    now = time.monotonic()

            # 2) ventana: máx N req por window_seconds
            if self._window_start is None or now - self._window_start >= self.window_seconds:
                self._window_start = now
                self._window_count = 0

            if self._window_count >= self.max_requests:
                sleep_for = self.window_seconds - (now - self._window_start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                    waited += sleep_for
                    now = time.monotonic()
                self._window_start = now
                self._window_count = 0

            self._last_acquire = now
            self._window_count += 1

        return waited

    def reset(self) -> None:
        """Reinicia el estado (útil en tests)."""
        with self._lock:
            self._last_acquire = None
            self._window_start = None
            self._window_count = 0
