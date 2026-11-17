"""Normalización del turno before the lectores read it (SPEC §5.2).

Four steps, in this order:

1. Muletillas out: "eh", "mmm", "o sea", "viste", "digamos", and "este" only when a pause follows
   it ("este…", "este,"), so the demonstrative ("este edificio") stays.
2. Autocorrección within the turno: "en Corrientes… no, perdón, en Montevideo" → "en Montevideo".
   The corrected part is dropped and the last value wins (CONTEXT.md, Autocorrección).
3. Números en palabras to digits, 0 to 99999: "mil quinientos cuarenta" → "1540".
4. Abreviaturas unified to the form the lectores read: "avenida"/"Avda" → "Av.", "gral" → "Gral.",
   "Juan B Justo" → "Juan B. Justo".

Every step keeps a map from the normalized text back to the original one, so a lector reads the
normalized text and its evidence is still highlighted on what the llamante actually said.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.transcript.text import fold

# A pause: comma, ellipsis ("…" or "..."), possibly several, with the spaces around them.
_PAUSE = r"(?:\s*(?:,|…|\.\.\.))"


@dataclass(frozen=True)
class Normalized:
    """A normalized text and, for each of its chars, the original span it comes from."""

    text: str
    original: str
    _starts: tuple[int, ...]
    _ends: tuple[int, ...]

    @classmethod
    def identity(cls, text: str) -> "Normalized":
        return cls(text, text, tuple(range(len(text))), tuple(range(1, len(text) + 1)))

    def to_original(self, start: int, end: int) -> tuple[int, int]:
        """The original span behind the normalized span ``[start, end)``.

        A char that stands for a longer original phrase ("1540" for "mil quinientos cuarenta")
        takes the whole phrase, so a span never cuts a replaced phrase in half.
        """
        if not 0 <= start <= end <= len(self.text):
            raise ValueError(f"span {start}:{end} outside the normalized text")
        if start == end:
            if start < len(self.text):
                return self._starts[start], self._starts[start]
            return len(self.original), len(self.original)
        return self._starts[start], self._ends[end - 1]

    def edit(self, edits: Iterable[tuple[int, int, str]]) -> "Normalized":
        """Replace spans of ``text`` (sorted, not overlapping) and compose the offset map."""
        chars: list[str] = []
        starts: list[int] = []
        ends: list[int] = []
        pos = 0
        for start, end, replacement in edits:
            if start < pos:
                raise ValueError("edits overlap or are not sorted")
            chars.append(self.text[pos:start])
            starts += self._starts[pos:start]
            ends += self._ends[pos:start]
            if replacement:
                src_start, src_end = self.to_original(start, end)
                chars.append(replacement)
                starts += [src_start] * len(replacement)
                ends += [src_end] * len(replacement)
            pos = end
        chars.append(self.text[pos:])
        starts += self._starts[pos:]
        ends += self._ends[pos:]
        return Normalized("".join(chars), self.original, tuple(starts), tuple(ends))


def normalize(text: str) -> Normalized:
    """The turno text ready for the lectores, with its map back to the original."""
    result = Normalized.identity(text)
    for step in (_drop_fillers, _apply_corrections, _numbers_to_digits, _unify_abbreviations):
        result = result.edit(step(result.text))
    return result


# --- 1. Muletillas -------------------------------------------------------------------------------

_FILLER = re.compile(
    rf"(?<!\w)(?:e+h+|e+hm+|m{{2,}}|o sea|digamos|viste(?={_PAUSE}|\s*[?.]|$)|este(?={_PAUSE}))"
    rf"(?!\w)(?:{_PAUSE}|\s*\?)*\s*",
    re.IGNORECASE,
)


def _drop_fillers(text: str) -> list[tuple[int, int, str]]:
    edits = []
    for match in _FILLER.finditer(text):
        start, end = match.start(), match.end()
        # The filler closes a phrase ("hay humo, viste."): drop the space before, keep the period.
        if end == len(text) or text[end] in ".?!":
            while start > 0 and text[start - 1] in " ,":
                start -= 1
        edits.append((start, end, ""))
    return edits


# --- 2. Autocorrección ---------------------------------------------------------------------------

# "digo" and "en realidad" are also plain speech ("le digo que salga"): only after a pause.
_CORRECTION = re.compile(
    rf"(?:{_PAUSE}|\s|^)\s*(?:no{_PAUSE}?\s*perd[oó]n|perd[oó]n{_PAUSE}?\s*no(?={_PAUSE})"
    rf"|mejor dicho|me equivoqu[eé]|(?<=[,….])\s*(?:digo|en realidad))(?!\w){_PAUSE}?\s*",
    re.IGNORECASE,
)
_SEGMENT_END = re.compile(r"[,;.!?…]")
_WORD = re.compile(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+")
# How far back the corrected value can start: one short phrase, not the whole turno.
_CORRECTION_REACH = 60


def _apply_corrections(text: str) -> list[tuple[int, int, str]]:
    edits: list[tuple[int, int, str]] = []
    floor = 0
    for match in _CORRECTION.finditer(text):
        after = _WORD.match(text, match.end())
        start = _corrected_start(text, match.start(), after.group() if after else None, floor)
        if start is None or after is None:
            continue
        edits.append((start, match.end(), ""))
        floor = match.end()
    return edits


def _corrected_start(text: str, marker: int, lead: str | None, floor: int) -> int | None:
    """Where the value being corrected begins, or None when there is nothing to correct.

    It is the last place before the marker where the same word as the new value opens ("en
    Corrientes… no, perdón, en Montevideo"); if there is none, the phrase right before the marker.
    """
    reach = max(floor, marker - _CORRECTION_REACH)
    before = text[reach:marker]
    if not before.strip(" ,.…"):
        return None
    if lead is not None:
        pattern = re.compile(rf"(?<!\w){re.escape(fold(lead))}(?!\w)")
        found = list(pattern.finditer(fold(before)))
        if found:
            return reach + found[-1].start()
    head = before.rstrip(" ,.…")
    stops = [m.end() for m in _SEGMENT_END.finditer(head)]
    start = reach + (stops[-1] if stops else 0)
    while start < marker and text[start].isspace():
        start += 1
    return start if start < marker else None


# --- 3. Números ----------------------------------------------------------------------------------

_UNITS = {
    "cero": 0,
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
}
_TEENS = {
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiun": 21,
    "veintiuno": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}
_TENS = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}
_HUNDREDS = {
    "ciento": 100,
    "doscientos": 200,
    "trescientos": 300,
    "cuatrocientos": 400,
    "quinientos": 500,
    "seiscientos": 600,
    "setecientos": 700,
    "ochocientos": 800,
    "novecientos": 900,
}
_HUNDREDS |= {k[:-2] + "as": v for k, v in _HUNDREDS.items() if k.endswith("os") and v > 100}
# Alone, "un"/"una"/"uno" are articles ("una persona"), not numbers.
_ARTICLES = frozenset({"un", "una", "uno"})
_NUMBER_WORDS = frozenset(_UNITS) | frozenset(_TEENS) | frozenset(_TENS) | frozenset(_HUNDREDS)
_NUMBER_WORDS |= {"cien", "mil", "y"}
MAX_NUMBER = 99_999

_Token = tuple[str, int, int]  # folded word, start, end


def _below_thousand(words: Sequence[str], i: int) -> tuple[int, int] | None:
    """Parse 1 to 999 at ``words[i]``: (value, words used), or None."""
    value, j = 0, i
    if j < len(words) and words[j] == "cien":
        return 100, 1
    if j < len(words) and words[j] in _HUNDREDS:
        value, j = _HUNDREDS[words[j]], j + 1
    if j < len(words) and words[j] in _TEENS:
        value, j = value + _TEENS[words[j]], j + 1
    elif j < len(words) and words[j] in _TENS:
        value, j = value + _TENS[words[j]], j + 1
        if j + 1 < len(words) and words[j] == "y" and _UNITS.get(words[j + 1], 0):
            value, j = value + _UNITS[words[j + 1]], j + 2
    elif j < len(words) and words[j] in _UNITS and words[j] != "cero":
        value, j = value + _UNITS[words[j]], j + 1
    if j == i or (words[i] == "ciento" and j == i + 1):
        return None
    return value, j - i


def _parse_number(words: Sequence[str]) -> tuple[int, int] | None:
    """The longest number at the start of ``words``: (value, words used), or None."""
    if not words:
        return None
    if words[0] == "cero":
        return 0, 1
    value, used = 0, 0
    if head := _below_thousand(words, 0):
        value, used = head
    if used < len(words) and words[used] == "mil" and (used == 0 or value > 0):
        value, used = (value or 1) * 1000, used + 1
        if tail := _below_thousand(words, used):
            value, used = value + tail[0], used + tail[1]
    if used == 0 or (used == 1 and words[0] in _ARTICLES):
        return None
    return value, used


def _numbers_to_digits(text: str) -> list[tuple[int, int, str]]:
    folded = fold(text)
    tokens = [(m.group(), m.start(), m.end()) for m in re.finditer(r"[a-z]+", folded)]
    edits: list[tuple[int, int, str]] = []
    i = 0
    while i < len(tokens):
        run = _number_run(tokens, i, text)
        parsed = _parse_number([t[0] for t in run]) if run else None
        if parsed is None:
            i += 1
            continue
        value, used = parsed
        if value <= MAX_NUMBER and not _is_name(text, run[0][1], run[used - 1][2]):
            edits.append((run[0][1], run[used - 1][2], str(value)))
        i += used
    return edits


def _number_run(tokens: Sequence[_Token], i: int, text: str) -> list[_Token]:
    """The number words from ``tokens[i]`` on, separated only by spaces and not part of a name.

    A capitalized number word inside a sentence is a name ("Tres Arroyos", "Nueve de Julio").
    """
    run: list[_Token] = []
    for token in tokens[i:]:
        word, start, _ = token
        if word not in _NUMBER_WORDS:
            break
        if run and text[run[-1][2] : start].strip():
            break
        if text[start].isupper() and not _opens_sentence(text, start):
            break
        run.append(token)
    while run and run[-1][0] == "y":
        run.pop()
    return run


_NAME_AFTER = re.compile(r"\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ]")


def _is_name(text: str, start: int, end: int) -> bool:
    """A capitalized number followed by a name is a name too: "Tres Arroyos", "Nueve de Julio"."""
    return text[start].isupper() and _NAME_AFTER.match(text, end) is not None


def _opens_sentence(text: str, pos: int) -> bool:
    head = text[:pos].rstrip()
    return not head or head[-1] in ".!?¡¿:…"


# --- 4. Abreviaturas -----------------------------------------------------------------------------

_NAME_AHEAD = r"(?=\s+[A-ZÁÉÍÓÚÑ0-9])"
_ABBREVIATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(?<!\w)(?:[Aa]vda\.?|[Aa]v(?!\.)|[Aa]venida)(?!\w){_NAME_AHEAD}"), "Av."),
    (re.compile(rf"(?<!\w)(?:[Gg]ral\.?)(?!\w){_NAME_AHEAD}"), "Gral."),
    (re.compile(rf"(?<!\w)(?:[Pp]te\.?)(?!\w){_NAME_AHEAD}"), "Pte."),
    (re.compile(rf"(?<!\w)(?:[Dd]r\.?)(?!\w){_NAME_AHEAD}"), "Dr."),
    (re.compile(r"(?<=\bJuan )(?:B|Be|Bautista)(?!\w)(?=\s+Justo\b)"), "B."),
)


def _unify_abbreviations(text: str) -> list[tuple[int, int, str]]:
    edits: list[tuple[int, int, str]] = []
    for pattern, replacement in _ABBREVIATIONS:
        for match in pattern.finditer(text):
            if match.group() != replacement:
                edits.append((match.start(), match.end(), replacement))
    return sorted(edits)
