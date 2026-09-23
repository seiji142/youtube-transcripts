"""Tests de la descarga solo-audio (sin red: YoutubeDL mockeado)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from yt_dlp.utils import DownloadError

from services import youtube_audio
from services.youtube_audio import YtDlpAudioDownloader
from services.youtube_errors import AudioDownloadFailed

VALID_ID = "dQw4w9WgXcQ"


class FakeYoutubeDL:
    """Doble de yt_dlp.YoutubeDL: graba opts y escribe un WAV falso."""

    last_opts: dict[str, Any] | None = None
    fail: bool = False
    duration: float | None = 42.0

    def __init__(self, opts: dict[str, Any] | None = None) -> None:
        self.opts = opts or {}
        FakeYoutubeDL.last_opts = self.opts

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        if FakeYoutubeDL.fail:
            raise DownloadError("network boom")
        video_id = url.split("v=")[1]
        outtmpl = self.opts["outtmpl"]
        wav = Path(
            outtmpl.replace("%(id)s", video_id).replace("%(ext)s", "wav")
        )
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"RIFF0000WAVE")
        return {"id": video_id, "duration": FakeYoutubeDL.duration}


@pytest.fixture(autouse=True)
def _fake_ydl(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeYoutubeDL.last_opts = None
    FakeYoutubeDL.fail = False
    FakeYoutubeDL.duration = 42.0
    monkeypatch.setattr(youtube_audio, "YoutubeDL", FakeYoutubeDL)


class TestDownload:
    def test_video_id_invalido_se_rechaza(self, tmp_path: Path) -> None:
        downloader = YtDlpAudioDownloader(base_dir=tmp_path, ffmpeg_location="C:/ffmpeg.exe")

        with pytest.raises(AudioDownloadFailed) as exc:
            downloader.download("no-valid")

        assert exc.value.code == "audio_download_failed"
        assert list(tmp_path.iterdir()) == []

    def test_sin_ffmpeg_da_error_con_sugerencia(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(youtube_audio, "find_ffmpeg", lambda: None)
        downloader = YtDlpAudioDownloader(base_dir=tmp_path)

        with pytest.raises(AudioDownloadFailed) as exc:
            downloader.download(VALID_ID)

        assert "FFmpeg no está instalado" in exc.value.message
        assert "winget" in (exc.value.suggestion or "")

    def test_descarga_happy_path(self, tmp_path: Path) -> None:
        downloader = YtDlpAudioDownloader(base_dir=tmp_path, ffmpeg_location="C:/ffmpeg.exe")

        result = downloader.download(VALID_ID)

        assert result.video_id == VALID_ID
        assert result.path.is_file()
        assert result.path.suffix == ".wav"
        assert result.work_dir.parent == tmp_path
        assert VALID_ID in result.work_dir.name
        assert result.duration == 42.0
        downloader.cleanup(result)
        assert not result.work_dir.exists()

    def test_opts_seguras_bestaudio_y_outtmpl_controlado(self, tmp_path: Path) -> None:
        downloader = YtDlpAudioDownloader(base_dir=tmp_path, ffmpeg_location="C:/ffmpeg.exe")

        downloader.download(VALID_ID)

        opts = FakeYoutubeDL.last_opts
        assert opts is not None
        assert opts["format"] == "bestaudio/best"
        assert opts["noplaylist"] is True
        assert opts["ffmpeg_location"] == "C:/ffmpeg.exe"
        assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
        assert opts["postprocessors"][0]["preferredcodec"] == "wav"
        # outtmpl vive bajo el work_dir aislado y usa plantilla interna
        assert opts["outtmpl"].startswith(str(tmp_path))
        assert "%(id)s.%(ext)s" in opts["outtmpl"]

    def test_fallo_de_red_limpia_temporal(self, tmp_path: Path) -> None:
        FakeYoutubeDL.fail = True
        downloader = YtDlpAudioDownloader(base_dir=tmp_path, ffmpeg_location="C:/ffmpeg.exe")

        with pytest.raises(AudioDownloadFailed) as exc:
            downloader.download(VALID_ID)

        assert exc.value.video_id == VALID_ID
        assert list(tmp_path.iterdir()) == []

    def test_ffmpeg_sin_salida_da_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoOutputYoutubeDL(FakeYoutubeDL):
            def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
                video_id = url.split("v=")[1]
                # simula extractor que no escribe nada (postproceso falló)
                return {"id": video_id, "duration": None}

        monkeypatch.setattr(youtube_audio, "YoutubeDL", NoOutputYoutubeDL)
        downloader = YtDlpAudioDownloader(base_dir=tmp_path, ffmpeg_location="C:/ffmpeg.exe")

        with pytest.raises(AudioDownloadFailed) as exc:
            downloader.download(VALID_ID)

        assert "no produjo ningún archivo" in exc.value.message
        assert list(tmp_path.iterdir()) == []

    def test_cleanup_es_idempotente(self, tmp_path: Path) -> None:
        downloader = YtDlpAudioDownloader(base_dir=tmp_path, ffmpeg_location="C:/ffmpeg.exe")
        result = downloader.download(VALID_ID)

        downloader.cleanup(result)
        downloader.cleanup(result)  # segunda vez: no debe fallar

        assert not result.work_dir.exists()
