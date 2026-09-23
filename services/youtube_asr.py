"""ASR local con faster-whisper (Fase 2, bloque C).

Transcribe archivos de audio (WAV u otros contenedores soportados por
PyAV) a segmentos ``{start, end, text}`` con el modelo ``small`` en
CPU con compute type ``int8`` — sin API keys ni servicios externos.

El modelo se carga de forma perezosa (lazy) la primera vez que se
invoca ``transcribe()``, para no penalizar al importar el módulo ni a
los tests unitarios (que inyectan un modelo falso).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.youtube_errors import AsrFailed

DEFAULT_MODEL_SIZE = "small"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_BEAM_SIZE = 5
DEFAULT_VAD_FILTER = True
_SOURCE = "faster_whisper"


@dataclass
class AsrResult:
    """Resultado normalizado del ASR local."""

    language: str | None
    segments: list[dict[str, Any]]
    source: str = _SOURCE
    model_size: str = DEFAULT_MODEL_SIZE
    language_probability: float | None = None

    @property
    def text(self) -> str:
        return "\n".join(seg["text"] for seg in self.segments)


class FasterWhisperTranscriber:
    """Transcriptor local basado en faster-whisper.

    Args:
        model_size: Modelo Whisper (default ``small`` según plan).
        device: ``cpu`` | ``cuda`` (v1: solo cpu documentado).
        compute_type: Cuantización (``int8`` en CPU).
        model: Modelo inyectado para tests (cualquier objeto con
            ``.transcribe(path, ...) -> (iterador, info)``).
        download_root: Directorio de descarga del modelo (opcional).
    """

    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        model: Any | None = None,
        download_root: str | None = None,
        beam_size: int = DEFAULT_BEAM_SIZE,
        vad_filter: bool = DEFAULT_VAD_FILTER,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._download_root = download_root
        self._model = model

    @property
    def model(self) -> Any:
        """Carga perezosa del modelo (solo en el primer ``transcribe``)."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover — dependencia fija en requirements
                raise AsrFailed(
                    "faster-whisper no está instalado",
                    suggestion="pip install faster-whisper (ver requirements.txt)",
                ) from exc
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self._download_root,
            )
        return self._model

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = None,
    ) -> AsrResult:
        """Transcribe un archivo de audio a segmentos con timestamps.

        Args:
            audio_path: Ruta al archivo de audio (WAV preferido).
            language: Código ISO para forzar idioma; None = autodetect.

        Lanza:
            AsrFailed — archivo inexistente, fallo del modelo o sin segmentos.
        """
        path = Path(audio_path)
        if not path.is_file():
            raise AsrFailed(
                f"Archivo de audio no encontrado: {path.name}",
                suggestion="Verificar la descarga de audio previa",
            )

        try:
            segments_iter, info = self.model.transcribe(
                str(path),
                language=language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
            )
            segments = [
                {
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": str(seg.text).strip(),
                }
                for seg in segments_iter
            ]
        except AsrFailed:
            raise
        except Exception as exc:  # noqa: BLE001 — mapeamos al dominio
            raise AsrFailed(
                f"faster-whisper falló: {exc}",
                suggestion="Revisar FFmpeg/audio y espacio en disco del modelo",
            ) from exc

        if not segments:
            raise AsrFailed(
                "El ASR no produjo segmentos (audio vacío o sin habla)",
                suggestion="Verificar que el video tenga habla audible",
            )

        return AsrResult(
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            segments=segments,
            model_size=self.model_size,
        )
