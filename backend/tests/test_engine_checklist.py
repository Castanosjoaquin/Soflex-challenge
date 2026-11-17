import pytest

from app.catalog.incidents import Subtype
from app.catalog.models import Category
from app.catalog.signals import SignalAnswer, SignalId
from app.engine.models import (
    CallState,
    ChecklistItem,
    Confidence,
    Line,
    Mode,
    QuestionStatus,
    Source,
    StageId,
    StageStatus,
)
from app.engine.state import (
    NoPremarkError,
    UnknownQuestionError,
    add_turn,
    answer_question,
    apply_reading,
    confirm_premark,
    confirm_type,
    new_call,
    skip_question,
)
from app.readers.models import Evidence, LocationReading, ReaderOutput
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn

S = SignalId
SI, NO, NO_SABE = SignalAnswer.SI, SignalAnswer.NO, SignalAnswer.NO_SABE

PIZZERIA = (
    "Hola, por favor manden a los bomberos ya! En la pizzería de Av. Corrientes 1540 casi "
    "Montevideo, se prendió fuego la campana de la cocina y se está metiendo el humo negro al "
    "salón, la gente salió corriendo a la calle pero adentro quedó el cocinero!"
)


def _call_with(*texts: str, line: Line = Line.L911) -> CallState:
    state = new_call("c1", line, Mode.SIMULADO)
    for text in texts:
        state = _say(state, text, line)
    return state


def _say(state: CallState, text: str, line: Line = Line.L911) -> CallState:
    turn = Turn(index=len(state.turns), at_ms=0, speaker=Speaker.LLAMANTE, text=text)
    state = add_turn(state, turn)
    return apply_reading(state, RulesReader().read(state.turns, line))


def _item(state: CallState, question_id: str) -> ChecklistItem:
    return next(i for i in state.checklist if i.question_id == question_id)


def _next_id(state: CallState) -> str | None:
    return state.next_question.id if state.next_question else None


def _stage(state: CallState, stage_id: StageId) -> StageStatus:
    return next(s.status for s in state.stages if s.id is stage_id)


# Caso 001


def test_case_001_premarks_atrapados_with_its_phrase_and_asks_for_gas_next() -> None:
    state = _call_with(PIZZERIA)
    atrapados = _item(state, "inc_atrapados")
    assert atrapados.text == "¿Hay personas atrapadas o adentro?"
    assert atrapados.status is QuestionStatus.PRE_MARCADA
    assert atrapados.value is SI
    assert atrapados.evidence is not None
    assert atrapados.evidence.quote == "adentro quedó el cocinero"
    assert state.next_question is not None
    assert state.next_question.id == "inc_gas"
    assert state.next_question.signal_ids == [S.GAS]
    assert _stage(state, StageId.PREGUNTAS) is StageStatus.ACTUAL


def test_the_checklist_follows_the_catalog_order_of_the_tipo() -> None:
    state = _call_with(PIZZERIA)
    assert [i.question_id for i in state.checklist] == [
        "inc_atrapados",
        "inc_gas",
        "inc_propagacion",
        "inc_evacuado",
        "inc_electrico",
        "inc_heridos",
    ]
    assert _item(state, "inc_propagacion").status is QuestionStatus.PRE_MARCADA
    assert _item(state, "inc_gas").status is QuestionStatus.PENDIENTE


# Próxima pregunta


def test_without_a_relato_the_next_question_is_where() -> None:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    assert state.next_question is not None
    assert (state.next_question.id, state.next_question.text) == (
        "ubicacion",
        "¿Dónde es la emergencia?",
    )
    assert state.checklist == []
    assert _stage(state, StageId.PREGUNTAS) is StageStatus.PENDIENTE


def test_a_street_without_altura_asks_for_it_before_anything_else() -> None:
    state = add_turn(
        new_call("c1", Line.L911, Mode.SIMULADO),
        Turn(index=0, at_ms=0, speaker=Speaker.LLAMANTE, text="Es en Corrientes, hay heridos"),
    )
    said = Evidence(turn_index=0, start=6, end=16, quote="Corrientes")
    reading = LocationReading(said="Corrientes", evidence=[said], street="Corrientes")
    state = apply_reading(state, ReaderOutput(location=reading))
    assert state.next_question is not None
    assert (state.next_question.id, state.next_question.text) == (
        "ubicacion",
        "¿A qué altura de Corrientes?",
    )


def test_a_place_without_streets_asks_where_near() -> None:
    state = _call_with("Estoy en la estación Carlos Pellegrini de la Línea B, hay humo")
    assert state.next_question is not None
    assert state.next_question.text == "¿Entre qué calles o cerca de qué esquina?"


def test_the_universal_comes_before_the_preguntas_clave() -> None:
    state = _call_with("chocaron dos autos en Av. Rivadavia 5000 y hay heridos")
    assert _next_id(state) == "universal"
    state = answer_question(state, "consciente", SI)
    state = answer_question(state, "respira", SI)
    assert _next_id(state) == "vial_atrapados"


def test_premarked_and_answered_questions_are_not_asked_again() -> None:
    state = answer_question(_call_with(PIZZERIA), "inc_gas", NO)
    # inc_propagacion is pre-marked, so the next one missing is inc_evacuado.
    assert _next_id(state) == "inc_evacuado"


def test_a_subtipo_brings_its_own_question() -> None:
    state = _call_with("chocaron dos autos en Av. Rivadavia 5000")
    assert "vial_casco" not in [i.question_id for i in state.checklist]
    state = confirm_type(state, Category.ACCIDENTE_VIAL, Subtype.CHOQUE_MOTO)
    assert "vial_casco" in [i.question_id for i in state.checklist]


# Acciones del operador


def test_an_answer_is_the_operadors_and_no_later_lectura_overwrites_it() -> None:
    state = answer_question(_call_with(PIZZERIA), "inc_gas", NO)
    gas = _item(state, "inc_gas")
    assert (gas.status, gas.value, gas.source) == (QuestionStatus.RESPONDIDA, NO, Source.OPERADOR)
    state = _say(state, "ahora huele mucho a gas, hay garrafas")
    gas = _item(state, "inc_gas")
    assert (gas.status, gas.value, gas.source) == (QuestionStatus.RESPONDIDA, NO, Source.OPERADOR)
    signal = next(s for s in state.signals if s.signal_id is S.GAS)
    assert signal.confidence is Confidence.CONFIRMADO


def test_confirming_a_premark_keeps_its_value_and_evidence() -> None:
    state = confirm_premark(_call_with(PIZZERIA), "inc_atrapados")
    atrapados = _item(state, "inc_atrapados")
    assert atrapados.status is QuestionStatus.RESPONDIDA
    assert atrapados.value is SI
    assert atrapados.source is Source.REGLAS
    assert atrapados.evidence is not None


def test_only_a_premark_can_be_confirmed() -> None:
    with pytest.raises(NoPremarkError):
        confirm_premark(_call_with(PIZZERIA), "inc_gas")
    with pytest.raises(UnknownQuestionError):
        confirm_premark(_call_with(PIZZERIA), "vial_casco")


def test_a_skipped_question_stays_in_the_checklist_and_the_next_one_comes() -> None:
    state = skip_question(_call_with(PIZZERIA), "inc_gas")
    assert _item(state, "inc_gas").status is QuestionStatus.SALTEADA
    assert _next_id(state) == "inc_evacuado"
    state = answer_question(state, "inc_gas", NO_SABE)
    assert _item(state, "inc_gas").status is QuestionStatus.RESPONDIDA
    assert state.skipped_questions == []


def test_the_universal_can_be_answered_no_sabe_or_skipped() -> None:
    text = "chocaron dos autos en Av. Rivadavia 5000 y hay heridos"
    state = answer_question(_call_with(text), "consciente", NO_SABE)
    assert state.next_question is not None
    assert state.next_question.signal_ids == [S.RESPIRA]
    state = skip_question(state, "universal")
    assert _next_id(state) == "vial_atrapados"
    with pytest.raises(UnknownQuestionError):
        answer_question(_call_with(PIZZERIA), "respira", SI)


def test_stage_three_is_done_when_every_critical_question_is_answered_or_skipped() -> None:
    state = confirm_premark(_call_with(PIZZERIA), "inc_atrapados")
    state = answer_question(state, "inc_gas", NO)
    assert _stage(state, StageId.PREGUNTAS) is StageStatus.ACTUAL
    state = skip_question(state, "inc_propagacion")
    assert _stage(state, StageId.PREGUNTAS) is StageStatus.HECHA
    # The non-critical ones are still there to ask.
    assert _next_id(state) == "inc_evacuado"
