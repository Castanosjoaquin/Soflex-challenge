"""Pure transitions of a llamada's state. Knows nothing about HTTP or the IA provider."""

from collections.abc import Sequence

from app.engine.models import (
    CallState,
    Confidence,
    Line,
    Location,
    Mode,
    Source,
    Stage,
    StageId,
    StageStatus,
)
from app.readers.models import Evidence, LocationReading, ReaderOutput, StreetNumber
from app.transcript.models import Turn


class NoLocationError(ValueError):
    """The operador acted on a ubicación that the relato has not produced yet."""


def new_call(call_id: str, line: Line, mode: Mode, sample_id: str | None = None) -> CallState:
    return CallState(
        call_id=call_id, line=line, mode=mode, sample_id=sample_id, stages=_stages(None)
    )


def add_turn(state: CallState, turn: Turn) -> CallState:
    return state.model_copy(update={"turns": [*state.turns, turn]})


def apply_reading(state: CallState, output: ReaderOutput) -> CallState:
    """Fold a lectura of the whole relato into the state.

    A reading whose evidence is not in the relato is discarded. A confirmed ubicación is never
    overwritten; an unconfirmed one takes the latest value (autocorrección).
    """
    location = state.location
    reading = output.location
    is_confirmed = location is not None and location.confidence is Confidence.CONFIRMADO
    if reading is not None and not is_confirmed and _evidence_holds(state.turns, reading.evidence):
        location = _location_from(reading)
    return _with_location(state, location)


def confirm_location(state: CallState) -> CallState:
    if state.location is None:
        raise NoLocationError
    return _with_location(
        state, state.location.model_copy(update={"confidence": Confidence.CONFIRMADO})
    )


def correct_location(
    state: CallState,
    *,
    street: str,
    number: StreetNumber | None,
    cross_streets: list[str],
) -> CallState:
    """The operador sets the dirección; what the llamante said and its evidence stay."""
    said = state.location.said if state.location else ""
    evidence = state.location.evidence if state.location else []
    corrected = Location(
        said=said,
        evidence=evidence,
        street=street,
        number=number,
        cross_streets=cross_streets,
        confidence=Confidence.CONFIRMADO,
        source=Source.OPERADOR,
    )
    return _with_location(state, corrected)


def _location_from(reading: LocationReading) -> Location:
    return Location(
        said=reading.said,
        evidence=reading.evidence,
        street=reading.street,
        number=reading.number,
        cross_streets=reading.cross_streets,
        landmark=reading.landmark,
        confidence=_confidence(reading),
        source=Source.REGLAS,
    )


def _confidence(reading: LocationReading) -> Confidence:
    """Probable when the dirección can be pinned down: a street plus an altura or a cross street."""
    has_altura = reading.number is not None and reading.number.value is not None
    if reading.street and (has_altura or reading.cross_streets):
        return Confidence.PROBABLE
    return Confidence.A_CONFIRMAR


def _evidence_holds(turns: Sequence[Turn], evidence: Sequence[Evidence]) -> bool:
    by_index = {t.index: t for t in turns}
    return bool(evidence) and all(
        (turn := by_index.get(ev.turn_index)) is not None
        and turn.text[ev.start : ev.end] == ev.quote
        for ev in evidence
    )


def _with_location(state: CallState, location: Location | None) -> CallState:
    return state.model_copy(update={"location": location, "stages": _stages(location)})


def _stages(location: Location | None) -> list[Stage]:
    """Only ① Ubicar has a real status for now; the rest arrive with their tickets."""
    located = location is not None and location.confidence is Confidence.CONFIRMADO
    ubicar = StageStatus.HECHA if located else StageStatus.ACTUAL
    return [
        Stage(id=stage_id, status=ubicar if stage_id is StageId.UBICAR else StageStatus.PENDIENTE)
        for stage_id in StageId
    ]
