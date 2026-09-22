"""Tests del RateLimiter preventivo (sin red)."""
from __future__ import annotations

import time

import pytest

from services.youtube_rate_limit import RateLimiter


class TestConfig:
    def test_defaults(self) -> None:
        rl = RateLimiter()
        assert rl.min_interval_seconds == 1.0
        assert rl.max_requests == 10
        assert rl.window_seconds == 60
        assert rl.enabled is True

    @pytest.mark.parametrize("kwargs", [
        {"min_interval_seconds": -1},
        {"max_requests": 0},
        {"window_seconds": 0},
    ])
    def test_config_invalida_lanza_value_error(self, kwargs: dict) -> None:
        with pytest.raises(ValueError):
            RateLimiter(**kwargs)


class TestDeshabilitado:
    def test_no_espera(self) -> None:
        rl = RateLimiter(min_interval_seconds=10.0, enabled=False)
        start = time.monotonic()
        for _ in range(5):
            waited = rl.acquire()
            assert waited == 0.0
        elapsed = time.monotonic() - start
        assert elapsed < 0.5


class TestMinInterval:
    def test_respeta_intervalo_minimo(self) -> None:
        rl = RateLimiter(min_interval_seconds=0.2, max_requests=100, window_seconds=60)
        start = time.monotonic()
        rl.acquire()  # primera: no espera
        rl.acquire()  # segunda: debe esperar ~0.2s
        rl.acquire()  # tercera: debe esperar ~0.2s
        elapsed = time.monotonic() - start
        assert elapsed >= 0.35  # ~0.4s esperado, margen

    def test_primera_llamada_no_espera(self) -> None:
        rl = RateLimiter(min_interval_seconds=5.0)
        start = time.monotonic()
        waited = rl.acquire()
        elapsed = time.monotonic() - start
        assert waited == 0.0
        assert elapsed < 0.1


class TestVentana:
    def test_excede_max_requests_y_espera_ventana(self) -> None:
        rl = RateLimiter(
            min_interval_seconds=0.0,
            max_requests=3,
            window_seconds=1,
        )
        start = time.monotonic()
        rl.acquire()
        rl.acquire()
        rl.acquire()
        # 4ª debe esperar a que pase la ventana (1s)
        rl.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9

    def test_reset_reinicia_estado(self) -> None:
        rl = RateLimiter(min_interval_seconds=10.0)
        rl.acquire()
        rl.reset()
        start = time.monotonic()
        waited = rl.acquire()
        assert waited == 0.0
        assert time.monotonic() - start < 0.1
