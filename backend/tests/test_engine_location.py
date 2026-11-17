import pytest

from app.engine.models import CallState, Confidence, Line, Mode, Source, StageId, StageStatus
from app.engine.state import (
    NoLocationError,
    add_turn,
    apply_reading,
    confirm_location,
    correct_location,
    new_call,
)
from app.readers.models import Evidence, LocationReading, NumberKind, ReaderOutput, StreetNumber
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn


def _call_with(*texts: str) -> CallState:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    for i, text in enumerate(texts):
        state = add_turn(state, Turn(index=i, at_ms=0, speaker=Speaker.LLAMANTE, text=text))
        state = apply_reading(state, RulesReader().read(state.turns))
    return state


def _stage(state: CallState, stage_id: StageId) -> StageStatus:
    return next(s.status for s in state.stages if s.id is stage_id)


def test_street_and_number_is_probable() -> None:
    state = _call_with("Es en Av. Corrientes 1540 casi Montevideo")
    assert state.location is not None
    assert state.location.confidence is Confidence.PROBABLE
    assert _stage(state, StageId.UBICAR) is StageStatus.ACTUAL


def test_landmark_only_is_a_confirmar() -> None:
    state = _call_with("Estoy en la estación Carlos Pellegrini de la Línea B")
    assert state.location is not None
    assert state.location.confidence is Confidence.A_CONFIRMAR


def test_confirm_marks_ubicar_done_and_survives_new_readings() -> None:
    state = confirm_location(_call_with("Es en Av. Corrientes 1540"))
    assert _stage(state, StageId.UBICAR) is StageStatus.HECHA
    later = add_turn(state, Turn(index=1, at_ms=0, speaker=Speaker.LLAMANTE, text="En Callao 300"))
    later = apply_reading(later, RulesReader().read(later.turns))
    assert later.location is not None
    assert later.location.street == "Av. Corrientes"
    assert later.location.confidence is Confidence.CONFIRMADO


def test_unconfirmed_location_takes_the_latest_value() -> None:
    state = _call_with("Es en Av. Corrientes 1540", "No, perdón, en Callao 300")
    assert state.location is not None
    assert state.location.street == "Callao"


def test_reading_with_evidence_not_in_relato_is_discarded() -> None:
    state = _call_with("Hola")
    fake = LocationReading(
        said="Corrientes 1540",
        evidence=[Evidence(turn_index=0, start=0, end=15, quote="Corrientes 1540")],
        street="Corrientes",
    )
    assert apply_reading(state, ReaderOutput(location=fake)).location is None


def test_correct_keeps_what_was_said() -> None:
    state = _call_with("Es en Corrientes 1540")
    corrected = correct_location(
        state,
        street="Av. Corrientes",
        number=StreetNumber(value=1450, kind=NumberKind.EXACTA),
        cross_streets=[],
    )
    assert corrected.location is not None
    assert corrected.location.said == "Corrientes 1540"
    assert corrected.location.source is Source.OPERADOR
    assert corrected.location.confidence is Confidence.CONFIRMADO
    assert _stage(corrected, StageId.UBICAR) is StageStatus.HECHA


def test_confirm_without_location_fails() -> None:
    with pytest.raises(NoLocationError):
        confirm_location(_call_with("Hola"))
