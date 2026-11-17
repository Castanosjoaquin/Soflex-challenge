"""What the Lector con IA may answer, and how its answer becomes a `ReaderOutput` (SPEC §5.3).

The schema has no field for prioridad, instrucciones or preguntas: whatever the model writes
there is ignored, because nothing reads it (ADR 0001). Each dato carries its quote; the quote is
located in the relato later, by the engine's verificación.

Validation has two levels:

- **Structure**: the answer is one JSON object with `location`, `incident` and `signals` of the
  right shapes. If it is not, the lectura failed: repair, retry, fallback.
- **Each dato**: a señal outside the closed list, a tipo that does not exist or a dato without its
  quote is dropped on its own, and the rest of the lectura stands.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.catalog.incidents import SUBTYPES, Subtype
from app.catalog.models import Category
from app.catalog.signals import SignalAnswer, SignalId
from app.readers.models import (
    Evidence,
    IncidentReading,
    LocationReading,
    NumberKind,
    ReaderOutput,
    SignalReading,
    StreetNumber,
)


class _Quoted(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quote: str = Field(min_length=1)
    turn: int = -1


class LLMLocation(_Quoted):
    said: str = Field(min_length=1)
    street: str | None = None
    number: int | None = None
    cross_streets: list[str] = Field(default_factory=list)
    landmark: str | None = None


class LLMIncident(_Quoted):
    category: Category
    subtype: str | None = None


class LLMSignal(_Quoted):
    id: SignalId
    value: SignalAnswer


class LLMAnswer(BaseModel):
    """The structure of the answer. Its items are validated one by one afterwards."""

    model_config = ConfigDict(extra="ignore")

    location: dict[str, Any] | None = None
    incident: dict[str, Any] | None = None
    signals: list[dict[str, Any]] = Field(default_factory=list)


class Parsed(BaseModel):
    """A valid answer, as a lectura, plus the datos dropped from it and why."""

    model_config = ConfigDict(frozen=True)

    output: ReaderOutput
    dropped: list[str] = Field(default_factory=list)


class InvalidAnswerError(ValueError):
    """The answer is not a JSON object of the expected shape. The message goes to the retry."""


def parse(raw: str) -> Parsed:
    """Validate an answer. Raises `InvalidAnswerError` when its structure is wrong."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidAnswerError(f"No es JSON válido: {exc.msg} (posición {exc.pos})") from None
    try:
        answer = LLMAnswer.model_validate(data)
    except ValidationError as exc:
        raise InvalidAnswerError(_errors(exc)) from None
    dropped: list[str] = []
    return Parsed(
        output=ReaderOutput(
            location=_location(answer.location, dropped),
            incident=_incident(answer.incident, dropped),
            signals=_signals(answer.signals, dropped),
        ),
        dropped=dropped,
    )


_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def repair(raw: str) -> str | None:
    """Local repair: take the JSON object out of the text around it and drop trailing commas.

    Returns None when there is no object to take out.
    """
    text = _FENCE.sub("", raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    return _TRAILING_COMMA.sub(r"\1", text[start : end + 1])


def _errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'respuesta'}: {e['msg']}" for e in exc.errors()
    )


def _evidence(item: _Quoted) -> Evidence:
    # Offsets are unknown: the verificación finds the quote in the relato and sets them.
    return Evidence(turn_index=item.turn, start=0, end=0, quote=item.quote)


def _location(data: dict[str, Any] | None, dropped: list[str]) -> LocationReading | None:
    if data is None:
        return None
    try:
        item = LLMLocation.model_validate(data)
    except ValidationError as exc:
        dropped.append(f"ubicación: {_errors(exc)}")
        return None
    number = None
    if item.number is not None:
        number = StreetNumber(value=item.number, kind=NumberKind.EXACTA)
    elif item.cross_streets:
        number = StreetNumber(kind=NumberKind.ESQUINA)
    return LocationReading(
        said=item.said,
        evidence=[_evidence(item)],
        street=item.street or None,
        number=number,
        cross_streets=[c for c in item.cross_streets if c.strip()],
        landmark=item.landmark or None,
    )


def _incident(data: dict[str, Any] | None, dropped: list[str]) -> IncidentReading | None:
    if data is None:
        return None
    try:
        item = LLMIncident.model_validate(data)
    except ValidationError as exc:
        dropped.append(f"tipo: {_errors(exc)}")
        return None
    subtype = None
    if item.subtype:
        try:
            subtype = Subtype(item.subtype)
        except ValueError:
            dropped.append(f"subtipo {item.subtype!r}: fuera de la lista")
        if subtype is not None and SUBTYPES[subtype].category is not item.category:
            dropped.append(f"subtipo {subtype}: no es de {item.category}")
            subtype = None
    return IncidentReading(category=item.category, subtype=subtype, evidence=[_evidence(item)])


def _signals(items: list[dict[str, Any]], dropped: list[str]) -> list[SignalReading]:
    signals: dict[SignalId, SignalReading] = {}
    for data in items:
        try:
            item = LLMSignal.model_validate(data)
        except ValidationError as exc:
            dropped.append(f"señal {data.get('id')!r}: {_errors(exc)}")
            continue
        if item.id in signals:
            continue  # the first mention of a señal wins
        signals[item.id] = SignalReading(
            signal_id=item.id, value=item.value, evidence=_evidence(item)
        )
    return list(signals.values())
