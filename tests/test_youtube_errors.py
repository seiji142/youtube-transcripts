"""Tests para los errores estructurados del dominio."""
from __future__ import annotations

import pytest

from services.youtube_errors import (
    DurationExceeded,
    InvalidYouTubeUrl,
    NoCaptionsAvailable,
    TranscriptError,
    VideoBlockedOrUnavailable,
)


class TestTranscriptError:
    def test_base_code(self) -> None:
        err = TranscriptError("algo falló")
        assert err.code == "transcript_error"

    def test_to_dict_minimo(self) -> None:
        err = TranscriptError("algo falló")
        payload = err.to_dict()
        assert payload == {
            "status": "error",
            "code": "transcript_error",
            "message": "algo falló",
        }

    def test_to_dict_con_video_id_y_sugerencia(self) -> None:
        err = NoCaptionsAvailable(
            "sin captions",
            video_id="dQw4w9WgXcQ",
            suggestion="Usar ASR en Fase 2",
        )
        payload = err.to_dict()
        assert payload["code"] == "no_captions"
        assert payload["video_id"] == "dQw4w9WgXcQ"
        assert payload["suggestion"] == "Usar ASR en Fase 2"

    def test_es_exception(self) -> None:
        with pytest.raises(TranscriptError):
            raise TranscriptError("x")


class TestCodigos:
    def test_codigos_estables(self) -> None:
        assert InvalidYouTubeUrl("x").code == "invalid_url"
        assert NoCaptionsAvailable("x").code == "no_captions"
        assert VideoBlockedOrUnavailable("x").code == "blocked"
        assert DurationExceeded("x").code == "duration_exceeded"

    def test_no_captions_distinto_de_blocked(self) -> None:
        """Requisito clave: sin captions y bloqueado deben distinguirse."""
        assert (
            NoCaptionsAvailable("x").code
            != VideoBlockedOrUnavailable("x").code
        )
