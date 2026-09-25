"""Chunking de transcripciones para el índice FTS5 (Fase 3).

Divide los segmentos de una transcripción en chunks de ~500-1000 tokens
con solapamiento del 10-15% y timestamps, sin cortar frases cuando se
puede evitar.

Tokens: estimación ``ceil(len(text) / 4)`` (chars/4) — decisión de
Fase 3 registrada en ``docs/DECISIONES.md``: sin dependencias de
tokenizer, suficiente para fijar tamaño de chunk.

Unidades de packing: cada segmento (cue) es una unidad atómica. Un
segmento mayor que ``max_tokens`` se parte en oraciones y, si una
oración sigue siendo gigante, a corte duro por caracteres — cada pieza
conserva el rango temporal del segmento original (repartido por
proporción de caracteres).

Corte en frontera de oración (best-effort): si el chunk llenado no cierra
una oración, se recorta la cola hasta el último cue que sí la cierre sin
bajar de ``min_tokens``; si no existe, se conserva el llenado máximo. La
granularidad de los cues limita esto.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_MIN_TOKENS = 500
DEFAULT_MAX_TOKENS = 1000
DEFAULT_OVERLAP = 0.12  # 12% (ventana 10-15%)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_SENTENCE_END_RE = re.compile(r"[.!?…][\"'»”)\]]*\s*$")


def est_tokens(text: str) -> int:
    """Estimación de tokens: ``ceil(len(text) / 4)`` (chars/4)."""
    return math.ceil(len(text) / 4) if text else 0


def _ends_sentence(text: str) -> bool:
    """True si el texto cierra una oración (terminador final)."""
    return bool(_SENTENCE_END_RE.search(text.strip()))


def _split_sentences(text: str) -> list[str]:
    """Parte ``text`` en oraciones conservando los terminadores."""
    parts = [p for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p]
    return parts if parts else [text]


def _field(segment: Any, name: str) -> Any:
    """Lee un campo de un segmento dict o dataclass (formato caché/dominio)."""
    if isinstance(segment, Mapping):
        return segment[name]
    return getattr(segment, name)


@dataclass(frozen=True)
class Chunk:
    """Fragmento de transcripción con timestamps para citas ``&t=``."""

    index: int
    text: str
    start: float
    end: float
    token_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "token_count": self.token_count,
        }


@dataclass(frozen=True)
class _Unit:
    """Unidad atómica de packing: un cue o una pieza de un cue gigante."""

    start: float
    end: float
    text: str


def _build_units(segments: Sequence[Any], max_tokens: int) -> list[_Unit]:
    """Normaliza segmentos en unidades; parte los cues > max_tokens."""
    units: list[_Unit] = []
    for segment in segments:
        text = str(_field(segment, "text")).strip()
        if not text:
            continue
        start = float(_field(segment, "start"))
        end = float(_field(segment, "end"))
        if est_tokens(text) <= max_tokens:
            units.append(_Unit(start=start, end=end, text=text))
            continue
        units.extend(_split_oversize(_Unit(start=start, end=end, text=text), max_tokens))
    return units


def _split_oversize(unit: _Unit, max_tokens: int) -> list[_Unit]:
    """Parte un cue gigante por oraciones (y a corte duro si hace falta)."""
    texts: list[str] = []
    for sentence in _split_sentences(unit.text):
        if est_tokens(sentence) <= max_tokens:
            texts.append(sentence)
            continue
        step = max_tokens * 4
        texts.extend(sentence[pos:pos + step] for pos in range(0, len(sentence), step))

    # Reparto temporal proporcional a los caracteres acumulados de cada pieza.
    total_chars = sum(len(text) for text in texts) or 1
    duration = max(unit.end - unit.start, 0.0)
    out: list[_Unit] = []
    offset = 0
    for text in texts:
        char_start = offset
        offset += len(text)
        out.append(
            _Unit(
                start=unit.start + duration * (char_start / total_chars),
                end=unit.start + duration * (offset / total_chars),
                text=text,
            )
        )
    return out


def chunk_transcript(
    segments: Iterable[Any],
    *,
    min_tokens: int = DEFAULT_MIN_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: float = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Chunking de una transcripción con solapamiento y timestamps.

    Args:
        segments: Segmentos con ``start``/``end``/``text`` (dict o dataclass).
        min_tokens: Mínimo objetivo por chunk (500 por defecto).
        max_tokens: Máximo por chunk (1000 por defecto).
        overlap: Fracción de tokens repetida entre chunks (0.10-0.15).

    Returns:
        Lista de chunks indexados de 0 a n-1. Vacía si no hay texto.

    Raises:
        ValueError: Parámetros fuera de rango.
    """
    if min_tokens < 1:
        raise ValueError("min_tokens debe ser >= 1")
    if max_tokens < 1:
        raise ValueError("max_tokens debe ser >= 1")
    if min_tokens > max_tokens:
        raise ValueError("min_tokens no puede superar max_tokens")
    if not 0.0 <= overlap < 1.0:
        raise ValueError("overlap debe estar en [0, 1)")

    units = _build_units(list(segments), max_tokens)
    if not units:
        return []

    unit_tokens = [est_tokens(unit.text) for unit in units]
    chunks: list[Chunk] = []
    start_idx = 0
    count = len(units)

    while start_idx < count:
        # Greedy: crece mientras quepa en max_tokens (siempre toma ≥1 unidad).
        total = 0
        end_idx = start_idx
        while end_idx < count and (
            total + unit_tokens[end_idx] <= max_tokens or end_idx == start_idx
        ):
            total += unit_tokens[end_idx]
            end_idx += 1

        # Frontera de oración: si el chunk no cierra oración, recorta la
        # cola hasta el último cue que sí la cierre sin bajar de min_tokens.
        # Si no existe, conserva el llenado máximo (best-effort).
        if not _ends_sentence(units[end_idx - 1].text):
            suffix = 0  # tokens[candidate:end_idx]
            for candidate in range(end_idx - 1, start_idx, -1):
                suffix += unit_tokens[candidate]
                tokens_e = total - suffix  # tokens[start_idx:candidate]
                if _ends_sentence(units[candidate - 1].text) and tokens_e >= min_tokens:
                    end_idx = candidate
                    total = tokens_e
                    break

        window = units[start_idx:end_idx]
        chunks.append(
            Chunk(
                index=len(chunks),
                text="\n".join(unit.text for unit in window),
                start=window[0].start,
                end=window[-1].end,
                token_count=total,
            )
        )

        if end_idx >= count:
            break

        # Solapamiento: reincluye la cola del chunk hasta ~overlap% de tokens.
        target = total * overlap
        carried = 0.0
        next_start = end_idx
        while next_start - 1 > start_idx and carried + unit_tokens[next_start - 1] <= target:
            carried += unit_tokens[next_start - 1]
            next_start -= 1
        start_idx = max(next_start, start_idx + 1)  # progreso garantizado

    return chunks
