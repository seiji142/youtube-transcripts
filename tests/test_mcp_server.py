"""Tests del servidor MCP (registro de tools, sin red)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

import mcp_server
from mcp_server import mcp, youtube_transcript
from services.youtube_errors import InvalidYouTubeUrl


class TestRegistroTools:
    def test_tool_registrada(self) -> None:
        async def _names() -> list[str]:
            tools = await mcp.list_tools()
            return [t.name for t in tools]

        names = asyncio.run(_names())
        assert "youtube_transcript" in names

    def test_service_usa_cache(self) -> None:
        assert mcp_server._service is not None
        assert mcp_server._service.cache is mcp_server._cache

    def test_service_tiene_fallback_subtitles(self) -> None:
        assert mcp_server._service._enable_subtitle_fallback is True
        assert mcp_server._service._subtitles is not None


class TestYoutubeTranscriptTool:
    def test_url_invalida_devuelve_error_estructurado(self) -> None:
        payload = youtube_transcript("https://evil.com/watch?v=dQw4w9WgXcQ")
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_url"
        assert "message" in payload

    def test_url_vacia_devuelve_error(self) -> None:
        payload = youtube_transcript("")
        assert payload["status"] == "error"
        assert payload["code"] == "invalid_url"

    def test_payload_error_es_dict(self) -> None:
        payload: dict[str, Any] = youtube_transcript("ftp://x/y")
        assert isinstance(payload, dict)
        assert payload["code"] == "invalid_url"

    def test_lanzamiento_directo_de_dominio(self) -> None:
        """La tool captura TranscriptError y no propaga excepciones."""
        with pytest.raises(InvalidYouTubeUrl):
            # el servicio sí lanza; la tool lo atrapa — aquí probamos el servicio
            mcp_server._service.get_transcript("not-a-url")

    def test_fallback_subtitles_inyectable_en_service(self) -> None:
        """YouTubeService acepta enable_subtitle_fallback para tests sin red."""
        from services.youtube_service import YouTubeService
        svc = YouTubeService(enable_subtitle_fallback=False)
        assert svc._enable_subtitle_fallback is False
