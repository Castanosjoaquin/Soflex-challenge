"""Rules-based ubicación reader: layered regex over the llamante's turnos (EDA, implicancia 1).

Layers, in order of preference within a turno:

1. street + altura: ``Corrientes 1540``, ``Scalabrini Ortiz al 800``, ``Lugones km 7``, ``s/n``,
   optionally followed by ``casi X``, ``entre X y Y`` or ``esquina X``.
2. intersection: ``(esquina de) X y Y``.
3. street + reference: ``Av. Lugones altura Parque Norte``.
4. landmark alone: ``Parque``, ``Plaza``, ``estación``, ``puente``, ``viaducto``, ``bajada``…

The last llamante turno that mentions a ubicación wins (autocorrección across turnos). Every
evidence carries offsets on the **original** turno text. Street names are kept as said: matching
them to the official street list is a separate step.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.readers.models import Evidence, LocationReading, NumberKind, StreetNumber
from app.transcript.models import Speaker, Turn

_UPPER = "A-ZÁÉÍÓÚÑ"
_LETTER = "A-Za-zÁÉÍÓÚÑáéíóúñü"
# Only abbreviations keep their dot, so a name never runs across a sentence ("Ríos. El").
# A single-letter initial ("Juan B. Justo") must not swallow the next sentence ("Línea B. En…").
_ABBREVIATION = (
    r"(?:(?:Av|Avda|Gral|Dr|Pte|Cnel|Tte|Sta|Sto)\."
    r"|[A-Z]\.(?!\s+(?:El|En|Es|Hay|La|Las|Los|Se|Son|Un|Una|Y)\b))"
)
# A capitalized word ("Corrientes", "Av.", "B.") or a date-like name chunk ("27 de Febrero").
_TOKEN = rf"(?:{_ABBREVIATION}|[{_UPPER}][{_LETTER}]*|\d{{1,2}}\s+de\s+[{_UPPER}][{_LETTER}]*)"
_CONNECTOR = r"(?:(?:de|del)(?:\s+(?:la|las|los))?|la|las|los)"
_NAME = rf"(?<![{_LETTER}\d]){_TOKEN}(?:\s+(?:{_CONNECTOR}\s+)?{_TOKEN})*"

_TAIL = re.compile(
    rf",?\s+(?:casi\s+(?P<casi>{_NAME})"
    rf"|entre\s+(?P<entre1>{_NAME})\s+y\s+(?P<entre2>{_NAME})"
    rf"|esquina\s+(?:(?:de|con)\s+)?(?P<esquina>{_NAME}))"
)
_STREET_NUMBER = re.compile(
    rf"(?P<street>{_NAME}),?\s+"
    r"(?:(?P<al>al\s+)?(?P<number>\d{2,5})"
    r"(?!\d|\s*(?:años|metros|minutos|personas|%)|\s+de\s+[A-Z])"
    r"|(?:km|Km|KM|kil[oó]metro)\s*(?P<km>\d{1,3})"
    r"|(?P<sn>sin\s+n[uú]mero|[sS]/[nN]))"
)
_INTERSECTION = re.compile(
    rf"(?:[eE]squina\s+(?:de\s+)?)?(?P<street>{_NAME})\s+y\s+(?P<cross>{_NAME})"
)
_LANDMARK_KEYWORD = (
    r"(?:[pP]arque|[pP]laza|[eE]staci[oó]n|[sS]ubestaci[oó]n|[pP]uente|[vV]iaducto"
    r"|[bB]ajada|[rR]otonda)"
)
_LANDMARK = re.compile(
    rf"(?P<landmark>(?P<kw>{_LANDMARK_KEYWORD})(?:\s+(?:de|del)(?:\s+la)?)?\s+(?P<name>{_NAME}))"
)
_STREET_REFERENCE = re.compile(
    rf"(?P<street>{_NAME})(?:,[^.,]{{1,40}})?,?\s+(?:a\s+la\s+)?altura\s+(?:de\s+)?(?:la\s+)?"
    rf"(?P<ref>{_LANDMARK.pattern}|{_NAME})"
)

# Capitalized words that open a sentence but are never part of a street name.
_LEADING_NOISE = frozenset(
    {
        "a",
        "acá",
        "aca",
        "al",
        "auxilio",
        "buen",
        "buenas",
        "buenos",
        "calle",
        "cerca",
        "de",
        "del",
        "desde",
        "el",
        "en",
        "es",
        "estamos",
        "estoy",
        "frente",
        "hay",
        "hola",
        "la",
        "las",
        "los",
        "mira",
        "mirá",
        "necesito",
        "por",
        "reporto",
        "si",
        "sí",
        "sobre",
        "son",
        "soy",
        "un",
        "una",
        "y",
    }
)
# Landmarks whose name is a street (``puente de Av. Elcano``), not a place (``Parque Norte``).
_STREET_LANDMARKS = ("puente", "viaducto", "bajada", "rotonda")


@dataclass(frozen=True)
class _Span:
    start: int
    end: int

    def overlaps(self, other: "_Span") -> bool:
        return self.start < other.end and other.start < self.end


def _trim_leading_noise(text: str, start: int, end: int) -> tuple[str, int] | None:
    """Drop sentence-opening words ("En Thames" → "Thames"); None if nothing is left."""
    name = text[start:end]
    offset = 0
    for word in re.finditer(r"\S+", name):
        if word.group().rstrip(".,").lower() not in _LEADING_NOISE:
            offset = word.start()
            break
    else:
        return None
    trimmed = name[offset:]
    if trimmed.rstrip(".").lower() in {"av", "avda", "avenida"}:
        return None
    return trimmed, start + offset


def _evidence(turn: Turn, start: int, end: int) -> Evidence:
    return Evidence(turn_index=turn.index, start=start, end=end, quote=turn.text[start:end])


def _with_tail(turn: Turn, end: int) -> tuple[list[str], int]:
    """Read ``casi X`` / ``entre X y Y`` / ``esquina X`` right after a street."""
    cross: list[str] = []
    while tail := _TAIL.match(turn.text, end):
        cross += [g for g in tail.group("casi", "entre1", "entre2", "esquina") if g]
        end = tail.end()
    return cross, end


def _landmark(turn: Turn, avoid: _Span | None) -> tuple[str, Evidence, re.Match[str]] | None:
    for match in _LANDMARK.finditer(turn.text):
        span = _Span(match.start(), match.end())
        if avoid is None or not span.overlaps(avoid):
            return match.group("landmark"), _evidence(turn, span.start, span.end), match
    return None


def _reading(
    turn: Turn,
    start: int,
    end: int,
    *,
    street: str | None,
    number: StreetNumber | None,
    cross_streets: list[str],
) -> LocationReading:
    main = _evidence(turn, start, end)
    evidence = [main]
    landmark: str | None = None
    if found := _landmark(turn, avoid=_Span(start, end)):
        landmark, landmark_evidence, _ = found
        evidence.append(landmark_evidence)
    return LocationReading(
        said=main.quote,
        evidence=evidence,
        street=street,
        number=number,
        cross_streets=cross_streets,
        landmark=landmark,
    )


def _read_street_number(turn: Turn) -> LocationReading | None:
    for match in _STREET_NUMBER.finditer(turn.text):
        trimmed = _trim_leading_noise(turn.text, match.start("street"), match.end("street"))
        if trimmed is None:
            continue
        street, start = trimmed
        if match.group("number"):
            kind = NumberKind.AL if match.group("al") else NumberKind.EXACTA
            number = StreetNumber(value=int(match.group("number")), kind=kind)
        elif match.group("km"):
            number = StreetNumber(value=int(match.group("km")), kind=NumberKind.KM)
        else:
            number = StreetNumber(kind=NumberKind.SN)
        cross, end = _with_tail(turn, match.end())
        return _reading(turn, start, end, street=street, number=number, cross_streets=cross)
    return None


def _read_intersection(turn: Turn) -> LocationReading | None:
    for match in _INTERSECTION.finditer(turn.text):
        trimmed = _trim_leading_noise(turn.text, match.start("street"), match.end("street"))
        if trimmed is None:
            continue
        street, start = trimmed
        if match.group(0).lower().startswith("esquina"):
            start = match.start()
        return _reading(
            turn,
            start,
            match.end(),
            street=street,
            number=StreetNumber(kind=NumberKind.ESQUINA),
            cross_streets=[match.group("cross")],
        )
    return None


def _read_street_reference(turn: Turn) -> LocationReading | None:
    for match in _STREET_REFERENCE.finditer(turn.text):
        trimmed = _trim_leading_noise(turn.text, match.start("street"), match.end("street"))
        if trimmed is None:
            continue
        street, start = trimmed
        main = _evidence(turn, start, match.end())
        return LocationReading(
            said=main.quote, evidence=[main], street=street, landmark=match.group("ref")
        )
    return None


def _read_landmark(turn: Turn) -> LocationReading | None:
    found = _landmark(turn, avoid=None)
    if found is None:
        return None
    landmark, evidence, match = found
    is_street = match.group("kw").lower() in _STREET_LANDMARKS
    return LocationReading(
        said=evidence.quote,
        evidence=[evidence],
        street=match.group("name") if is_street else None,
        landmark=landmark,
    )


_LAYERS = (_read_street_number, _read_intersection, _read_street_reference, _read_landmark)


def read_turn_location(turn: Turn) -> LocationReading | None:
    """The best ubicación said in one turno, by layer order."""
    for layer in _LAYERS:
        if reading := layer(turn):
            return reading
    return None


def read_location(turns: Sequence[Turn]) -> LocationReading | None:
    """The ubicación of the relato: the latest llamante turno that mentions one."""
    latest: LocationReading | None = None
    for turn in turns:
        if turn.speaker is Speaker.LLAMANTE and (reading := read_turn_location(turn)):
            latest = reading
    return latest
