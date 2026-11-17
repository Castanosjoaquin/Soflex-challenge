import pytest

from app.engine.models import (
    CallState,
    Confidence,
    Line,
    Mode,
    Source,
    Stage,
    StageId,
    StageStatus,
)
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


# Dirección oficial (SPEC §5.5)


def test_the_dirección_uses_official_names() -> None:
    state = _call_with("Es en Scalabrini Ortiz al 800, entre Vera y Velasco")
    assert state.location is not None
    assert state.location.street == "Scalabrini Ortiz"
    assert state.location.street_official == "AV. RAUL SCALABRINI ORTIZ"
    assert state.location.cross_streets_official == ["VERA", "JUAN RAMIREZ DE VELASCO"]
    assert state.location.confidence is Confidence.PROBABLE


def test_a_street_matched_by_sound_is_a_confirmar() -> None:
    state = _call_with("Estoy en Biyinghurst 1845, casi Juncal")
    assert state.location is not None
    assert state.location.street_official == "BILLINGHURST"
    assert state.location.confidence is Confidence.A_CONFIRMAR


def test_a_street_not_in_the_list_stays_as_said_and_a_confirmar() -> None:
    state = _call_with("Es en Pepito Inventado 1234")
    assert state.location is not None
    assert state.location.street == "Pepito Inventado"
    assert state.location.said == "Pepito Inventado 1234"
    assert state.location.street_official is None
    assert state.location.confidence is Confidence.A_CONFIRMAR


def test_ambiguous_names_list_their_candidates() -> None:
    state = _call_with("Fue en Sarmiento 3900")
    assert state.location is not None
    assert state.location.candidates == ["SARMIENTO", "AV. SARMIENTO"]
    assert state.location.confidence is Confidence.A_CONFIRMAR


# Pregunta de ubicación faltante (DESIGN §Paso 4)


def _ubicar(state: CallState) -> Stage:
    return next(s for s in state.stages if s.id is StageId.UBICAR)


def test_a_relato_without_ubicación_asks_where_and_turns_ubicar_red() -> None:
    state = _call_with("Hola, se está prendiendo fuego la cocina")
    assert state.next_question is not None
    assert state.next_question.text == "¿Dónde es la emergencia?"
    assert _ubicar(state).alert


def test_a_new_call_asks_where_but_is_not_alarmed_yet() -> None:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    assert state.next_question is not None
    assert state.next_question.text == "¿Dónde es la emergencia?"
    assert not _ubicar(state).alert


@pytest.mark.parametrize(
    ("relato", "question"),
    [
        (
            "Estoy en la estación Carlos Pellegrini de la Línea B",
            "¿Entre qué calles o cerca de qué entrada?",
        ),
        ("Fue en Sarmiento 3900", "¿Es la avenida o la calle?"),
        ("En la esquina de Scalabrini Ortiz y Honduras", "¿Es la avenida o la calle?"),
    ],
)
def test_an_incomplete_ubicación_asks_what_is_missing(relato: str, question: str) -> None:
    state = _call_with(relato)
    assert state.next_question is not None
    assert state.next_question.text == question
    assert not _ubicar(state).alert


@pytest.mark.parametrize(
    "relato", ["Es en Av. Corrientes 1540 casi Montevideo", "En Thames y Nicaragua"]
)
def test_a_complete_ubicación_asks_nothing(relato: str) -> None:
    assert _call_with(relato).next_question is None


def test_a_confirmed_ubicación_asks_nothing() -> None:
    state = confirm_location(_call_with("Fue en Sarmiento 3900"))
    assert state.next_question is None


@pytest.mark.parametrize(
    ("relato", "question"),
    [
        ("Estoy en Corrientes, se prendió fuego un auto", "¿A qué altura de Corrientes?"),
        ("Choque sobre la Av. Rivadavia, vengan", "¿A qué altura de Rivadavia?"),
        # Without altura, the altura is asked first: it also settles avenida o calle.
        ("Estoy en Scalabrini Ortiz, vengan", "¿A qué altura de Scalabrini Ortiz?"),
    ],
)
def test_a_street_without_altura_asks_for_it(relato: str, question: str) -> None:
    state = _call_with(relato)
    assert state.location is not None
    assert state.location.confidence is Confidence.A_CONFIRMAR
    assert state.next_question is not None
    assert state.next_question.text == question


def test_the_operador_correction_is_normalized_and_stays_confirmed() -> None:
    state = correct_location(
        _call_with("Es en Biyinghurst 1845"),
        street="Biyinghurst",
        number=StreetNumber(value=1845, kind=NumberKind.EXACTA),
        cross_streets=["Juncal"],
    )
    assert state.location is not None
    assert state.location.street_official == "BILLINGHURST"
    assert state.location.cross_streets_official == ["JUNCAL"]
    assert state.location.confidence is Confidence.CONFIRMADO


def test_a_corner_on_a_street_renamed_in_part_asks_for_the_altura() -> None:
    state = _call_with("En Serrano y Honduras, frente a la plaza")
    assert state.location is not None
    assert state.location.candidates == ["SERRANO", "JORGE LUIS BORGES"]
    assert state.location.confidence is Confidence.A_CONFIRMAR
    assert state.next_question is not None
    assert state.next_question.text == "¿A qué altura de Serrano?"
