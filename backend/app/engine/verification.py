"""Verificación de evidencia (SPEC §5.4.1): a dato without its phrase in the relato is discarded.

A quote is looked up inside a single llamante turno: first at its stated offsets, then as a
normalized exact match (no accents, case, punctuation or extra spaces), then fuzzy (ratio ≥ 0,9)
over word-aligned windows. The turno it names is tried first, then the other llamante turnos.
When found, the evidence is returned relocated onto the original text.
"""

import re
from collections.abc import Sequence
from difflib import SequenceMatcher

from app.readers.models import Evidence
from app.transcript.models import Speaker, Turn
from app.transcript.text import fold

FUZZY_THRESHOLD = 0.9
_NOISE = re.compile(r"[^\w\s]")


def verify(evidence: Evidence, turns: Sequence[Turn]) -> Evidence | None:
    llamante = [t for t in turns if t.speaker is Speaker.LLAMANTE]
    stated = [t for t in llamante if t.index == evidence.turn_index]
    if stated and stated[0].text[evidence.start : evidence.end] == evidence.quote:
        return evidence
    quote, _ = _normalize(evidence.quote)
    if not quote:
        return None
    ordered = stated + [t for t in llamante if t.index != evidence.turn_index]
    for find in (_find_exact, _find_fuzzy):
        for turn in ordered:
            if (found := find(turn, quote)) is not None:
                return found
    return None


def _normalize(text: str) -> tuple[str, list[int]]:
    """Folded text without punctuation and with single spaces, plus where each char came from."""
    chars: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(fold(text)):
        if _NOISE.match(ch) or ch.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                origin.append(i)
            continue
        chars.append(ch)
        origin.append(i)
    while chars and chars[-1] == " ":
        chars.pop()
        origin.pop()
    return "".join(chars), origin


def _relocate(turn: Turn, origin: list[int], start: int, end: int) -> Evidence:
    first, last = origin[start], origin[end - 1] + 1
    return Evidence(turn_index=turn.index, start=first, end=last, quote=turn.text[first:last])


def _find_exact(turn: Turn, quote: str) -> Evidence | None:
    text, origin = _normalize(turn.text)
    for match in re.finditer(re.escape(quote), text):
        if _at_word_edges(text, match.start(), match.end()):
            return _relocate(turn, origin, match.start(), match.end())
    return None


def _find_fuzzy(turn: Turn, quote: str) -> Evidence | None:
    text, origin = _normalize(turn.text)
    starts = [0] + [m.end() for m in re.finditer(" ", text)]
    ends = [m.start() for m in re.finditer(" ", text)] + [len(text)]
    low, high = len(quote) * 0.8, len(quote) * 1.2
    best: tuple[float, int, int] | None = None
    for start in starts:
        for end in ends:
            if end <= start or not low <= end - start <= high:
                continue
            ratio = SequenceMatcher(None, quote, text[start:end], autojunk=False).ratio()
            if ratio >= FUZZY_THRESHOLD and (best is None or ratio > best[0]):
                best = (ratio, start, end)
    if best is None:
        return None
    return _relocate(turn, origin, best[1], best[2])


def _at_word_edges(text: str, start: int, end: int) -> bool:
    before = start == 0 or text[start - 1] == " "
    after = end == len(text) or text[end] == " "
    return before and after
