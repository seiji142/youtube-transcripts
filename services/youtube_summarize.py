"""Resúmenes jerárquicos extractivos (Fase 4, E3).

Sin LLM ni dependencias externas (v1 100% offline): el transcript se
divide en secciones temporales y de cada sección se eligen las
oraciones más representativas por TF-IDF sobre el documento (sin
stopwords ES/EN). Cada oración conserva su ``start`` para citas
``&t=``.

Jerarquía: secciones (detalle por tramo) + ``overall`` (las mejores
oraciones del video completo).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_MAX_SECTIONS = 5
DEFAULT_SENTENCES_PER_SECTION = 2
MAX_SECTIONS_LIMIT = 10
MAX_SENTENCES_LIMIT = 5

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

_STOPWORDS_ES = frozenset(
    "el la los las un una unos unas de del en y o u que qué se su sus "
    "por para con sin sobre entre hasta desde esto esta este estos estas "
    "ese esa esos esas aquel aquello ello lo le les me te nos os mi mis "
    "tu tus es son fue fueron era eran hay está están estoy estamos "
    "tiene tienen tengo tenemos hace hacen hizo muy más mas menos pero "
    "como cómo cuando donde dónde cual cuál cuales porque pues así tan "
    "solo sólo también tampoco algo nada todo todos todas cada cual "
    "quien quienes cuyo cuya aquí ahí allí entonces bueno pues mira "
    "mirad oye vale bueno".split()
)
_STOPWORDS_EN = frozenset(
    "the a an of in on and or but to for with without from by at as is "
    "are was were be been being it its this that these those he she "
    "they them his her their we you your our i me my we us have has "
    "had do does did will would can could should there here what which "
    "who whom whose when where why how not no yes so very more most "
    "some any all each".split()
)
_STOPWORDS = _STOPWORDS_ES | _STOPWORDS_EN


def _field(segment: Any, name: str) -> Any:
    if isinstance(segment, Mapping):
        return segment[name]
    return getattr(segment, name)


def _terms(text: str) -> list[str]:
    """Tokens en minúsculas sin stopwords ES/EN."""
    return [
        word for word in _WORD_RE.findall(text.lower())
        if word not in _STOPWORDS and len(word) > 1
    ]


@dataclass(frozen=True)
class Sentence:
    """Oración con el rango temporal de su segmento origen."""

    text: str
    start: float
    end: float


@dataclass
class SectionSummary:
    """Resumen extractivo de una sección temporal."""

    index: int
    start: float
    end: float
    sentences: list[Sentence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "sentences": [
                {"text": s.text, "start": s.start, "end": s.end}
                for s in self.sentences
            ],
        }


@dataclass
class SummaryResult:
    """Resumen jerárquico: secciones + overall del video."""

    sections: list[SectionSummary] = field(default_factory=list)
    overall: list[Sentence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": [s.to_dict() for s in self.sections],
            "overall": [
                {"text": s.text, "start": s.start, "end": s.end}
                for s in self.overall
            ],
        }


def _build_sentences(segments: Sequence[Any]) -> list[Sentence]:
    """Parte los segmentos en oraciones conservando timestamps."""
    sentences: list[Sentence] = []
    for segment in segments:
        text = str(_field(segment, "text")).strip()
        if not text:
            continue
        start = float(_field(segment, "start"))
        end = float(_field(segment, "end"))
        parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
        for part in parts or [text]:
            sentences.append(Sentence(text=part, start=start, end=end))
    return sentences


def _score(sentences: Sequence[Sentence]) -> list[tuple[float, int]]:
    """Puntaje TF-IDF por oración (determinista: el índice desempata).

    Devuelve (puntaje, índice) ordenado de mayor a menor. ``idf`` con
    suavizado +1 para no anular términos que aparecen en todas las
    oraciones.
    """
    term_freqs: list[Counter[str]] = []
    doc_freq: Counter[str] = Counter()
    for sentence in sentences:
        counts = Counter(_terms(sentence.text))
        term_freqs.append(counts)
        doc_freq.update(counts.keys())
    total_sentences = len(sentences) or 1
    scored: list[tuple[float, int]] = []
    for index, counts in enumerate(term_freqs):
        total = sum(
            count * (math.log(total_sentences / doc_freq[term]) + 1.0)
            for term, count in counts.items()
        )
        scored.append((total, index))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored


def summarize_transcript(
    segments: Iterable[Any],
    *,
    max_sections: int = DEFAULT_MAX_SECTIONS,
    sentences_per_section: int = DEFAULT_SENTENCES_PER_SECTION,
) -> SummaryResult:
    """Resume extractivamente por secciones temporales + overall.

    Args:
        segments: Segmentos con ``start``/``end``/``text``.
        max_sections: Nº máximo de secciones (1..10).
        sentences_per_section: Oraciones por sección y para el
            overall (1..5).

    Returns:
        ``SummaryResult`` (vacío si no hay texto).

    Raises:
        ValueError: Parámetros fuera de rango.
    """
    if not 1 <= max_sections <= MAX_SECTIONS_LIMIT:
        raise ValueError(f"max_sections debe estar en [1, {MAX_SECTIONS_LIMIT}]")
    if not 1 <= sentences_per_section <= MAX_SENTENCES_LIMIT:
        raise ValueError(
            f"sentences_per_section debe estar en [1, {MAX_SENTENCES_LIMIT}]",
        )

    sentences = _build_sentences(list(segments))
    if not sentences:
        return SummaryResult()

    ranked = _score(sentences)
    rank_of = {index: rank for rank, (_, index) in enumerate(ranked)}

    duration = max(s.end for s in sentences)

    # Secciones por tramos iguales de tiempo; se omiten las vacías.
    width = duration / max_sections if duration > 0 else 0.0
    sections: list[SectionSummary] = []
    for number in range(max_sections):
        start = number * width
        end = duration if number == max_sections - 1 else (number + 1) * width
        in_section = [
            (rank_of[i], i)
            for i, s in enumerate(sentences)
            if (s.start >= start and (s.start < end or number == max_sections - 1))
        ]
        if not in_section:
            continue
        in_section.sort()
        picked = sorted(i for _, i in in_section[:sentences_per_section])
        sections.append(SectionSummary(
            index=len(sections),
            start=start,
            end=end,
            sentences=[sentences[i] for i in picked],
        ))

    overall_idx = sorted(i for _, i in ranked[:sentences_per_section])
    return SummaryResult(
        sections=sections,
        overall=[sentences[i] for i in overall_idx],
    )
