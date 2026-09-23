"""Tests del ASR faster-whisper (sin red ni modelo real: inyectado)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.youtube_asr import (
    DEFAULT_BEAM_SIZE,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_MODEL_SIZE,
    DEFAULT_VAD_FILTER,
    AsrResult,
    FasterWhisperTranscriber,
)
from services.youtube_errors import AsrFailed


def _seg(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, text=text)


class FakeModel:
    """Doble de WhisperModel: devuelve segmentos fijos o falla."""

    def __init__(
        self,
        segments: list[SimpleNamespace] | None = None,
        info: SimpleNamespace | None = None,
        error: Exception | None = None,
    ) -> None:
        self._segments = segments if segments is not None else [
            _seg(0.0, 1.5, "Hola mundo"),
            _seg(1.5, 3.0, "Esto es una prueba"),
        ]
        self._info = info or SimpleNamespace(
            language="es", language_probability=0.97,
        )
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def transcribe(
        self, path: str, language: str | None = None,
        beam_size: int | None = None, vad_filter: bool | None = None,
    ) -> tuple[Any, Any]:
        self.calls.append({
            "path": path, "language": language,
            "beam_size": beam_size, "vad_filter": vad_filter,
        })
        if self._error is not None:
            raise self._error
        return iter(self._segments), self._info


class TestConfig:
    def test_defaults_según_plan(self) -> None:
        t = FasterWhisperTranscriber()
        assert t.model_size == DEFAULT_MODEL_SIZE == "small"
        assert t.device == DEFAULT_DEVICE == "cpu"
        assert t.compute_type == DEFAULT_COMPUTE_TYPE == "int8"
        assert t.beam_size == DEFAULT_BEAM_SIZE == 5
        assert t.vad_filter is DEFAULT_VAD_FILTER is True

    def test_model_no_se_carga_al_importar(self) -> None:
        t = FasterWhisperTranscriber()
        assert t._model is None  # lazy: sin descarga hasta transcribe()


class TestTranscribe:
    def test_archivo_inexistente_da_asr_failed(self, tmp_path: Path) -> None:
        t = FasterWhisperTranscriber(model=FakeModel())

        with pytest.raises(AsrFailed) as exc:
            t.transcribe(tmp_path / "no_existe.wav")

        assert exc.value.code == "asr_failed"

    def test_happy_path_devuelve_segmentos(self, tmp_path: Path) -> None:
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"RIFF")
        model = FakeModel()
        t = FasterWhisperTranscriber(model=model)

        result = t.transcribe(audio)

        assert isinstance(result, AsrResult)
        assert result.language == "es"
        assert result.language_probability == 0.97
        assert result.source == "faster_whisper"
        assert result.model_size == "small"
        assert len(result.segments) == 2
        assert result.segments[0] == {
            "start": 0.0, "end": 1.5, "text": "Hola mundo",
        }
        assert result.text == "Hola mundo\nEsto es una prueba"

    def test_params_reenviados_al_modelo(self, tmp_path: Path) -> None:
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"RIFF")
        model = FakeModel()
        t = FasterWhisperTranscriber(model=model)

        t.transcribe(audio, language="es")

        call = model.calls[0]
        assert call["language"] == "es"
        assert call["beam_size"] == 5
        assert call["vad_filter"] is True

    def test_fallo_del_modelo_mapea_a_asr_failed(self, tmp_path: Path) -> None:
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"RIFF")
        model = FakeModel(error=RuntimeError("cuda exploded"))
        t = FasterWhisperTranscriber(model=model)

        with pytest.raises(AsrFailed) as exc:
            t.transcribe(audio)

        assert "cuda exploded" in exc.value.message

    def test_segmentos_vacios_da_asr_failed(self, tmp_path: Path) -> None:
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"RIFF")
        model = FakeModel(segments=[])
        t = FasterWhisperTranscriber(model=model)

        with pytest.raises(AsrFailed) as exc:
            t.transcribe(audio)

        assert "no produjo segmentos" in exc.value.message

    def test_language_autodetect_por_default(self, tmp_path: Path) -> None:
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"RIFF")
        model = FakeModel()
        t = FasterWhisperTranscriber(model=model)

        t.transcribe(audio)

        assert model.calls[0]["language"] is None
