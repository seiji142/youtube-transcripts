"""Tests unitarios del parser seguro de URLs de YouTube."""
from __future__ import annotations

import pytest

from services.youtube_errors import InvalidYouTubeUrl
from services.youtube_urls import extract_video_id, is_valid_video_id

VALID_ID = "dQw4w9WgXcQ"
ANOTHER_ID = "abcDEF12345"


class TestExtractVideoIdValidas:
    @pytest.mark.parametrize("url", [
        f"https://www.youtube.com/watch?v={VALID_ID}",
        f"https://youtube.com/watch?v={VALID_ID}",
        f"http://www.youtube.com/watch?v={VALID_ID}",
        f"https://m.youtube.com/watch?v={VALID_ID}",
        f"https://youtu.be/{VALID_ID}",
        f"https://www.youtu.be/{VALID_ID}",
        f"https://www.youtube.com/shorts/{ANOTHER_ID}",
        f"https://www.youtube.com/embed/{ANOTHER_ID}",
        f"https://www.youtube.com/watch?v={VALID_ID}&t=620s",
        f"  https://www.youtube.com/watch?v={VALID_ID}  ",
    ])
    def test_urls_validas(self, url: str) -> None:
        expected = VALID_ID if VALID_ID in url else ANOTHER_ID
        assert extract_video_id(url) == expected


class TestExtractVideoIdInvalidas:
    @pytest.mark.parametrize("url,fragment", [
        ("", "vacía"),
        ("   ", "vacía"),
        ("not a url", "HTTP o HTTPS"),
        ("ftp://www.youtube.com/watch?v=dQw4w9WgXcQ", "HTTP o HTTPS"),
        ("https://evil.com/watch?v=dQw4w9WgXcQ", "host"),
        ("https://notyoutube.com/watch?v=dQw4w9WgXcQ", "host"),
        (f"https://www.youtube.com/watch?v={VALID_ID}&list=PLxyz", "playlists"),
        ("https://www.youtube.com/playlist?list=PLxyz", "playlists"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "directos"),
        ("https://www.youtube.com/watch?v=short", "inválido"),
        ("https://www.youtube.com/watch?v=", "inválido"),
        ("https://www.youtube.com/watch?v=abc@DEF12345", "inválido"),
        ("https://www.youtube.com/watch?v=abcDEF123456", "inválido"),
        ("https://www.youtube.com/watch", "inválido"),
        ("https://youtu.be/", "inválido"),
        (None, "vacía"),
        (12345, "vacía"),
    ])
    def test_urls_invalidas_lanzan_invalid_url(self, url: object, fragment: str) -> None:
        with pytest.raises(InvalidYouTubeUrl) as exc_info:
            extract_video_id(url)  # type: ignore[arg-type]
        assert exc_info.value.code == "invalid_url"
        assert fragment in exc_info.value.message


class TestIsValidVideoId:
    @pytest.mark.parametrize("vid", [VALID_ID, ANOTHER_ID, "aaaaaaaaaaa"])
    def test_ids_validos(self, vid: str) -> None:
        assert is_valid_video_id(vid)

    @pytest.mark.parametrize("vid", ["", "short", "abc@DEF1234", "a" * 12, None])
    def test_ids_invalidos(self, vid: object) -> None:
        assert not is_valid_video_id(vid)  # type: ignore[arg-type]
