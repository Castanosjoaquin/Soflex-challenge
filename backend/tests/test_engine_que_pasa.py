import pytest

from app.catalog.incidents import Subtype
from app.catalog.models import Category, Priority
from app.catalog.signals import SignalAnswer, SignalId
from app.engine.models import (
    CallState,
    Confidence,
    Incident,
    Line,
    Mode,
    SignalValue,
    Source,
    StageId,
    StageStatus,
)
from app.engine.priority import assess
from app.engine.state import (
    NoIncidentError,
    add_turn,
    apply_reading,
    confirm_type,
    new_call,
    set_priority,
)
from app.readers.models import Evidence, ReaderOutput, SignalReading
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn

S = SignalId
SI, NO = SignalAnswer.SI, SignalAnswer.NO

PIZZERIA = (
    "Hola, por favor manden a los bomberos ya! En la pizzería de Av. Corrientes 1540 casi "
    "Montevideo, se prendió fuego la campana de la cocina y se está metiendo el humo negro al "
    "salón, la gente salió corriendo a la calle pero adentro quedó el cocinero!"
)


# A dirección, so that the ubicación question is not the próxima pregunta.
AQUI = "Estoy en Av. Corrientes 1540. "


def _call_with(*texts: str, line: Line = Line.L911) -> CallState:
    state = new_call("c1", line, Mode.SIMULADO)
    for i, text in enumerate(texts):
        state = add_turn(state, Turn(index=i, at_ms=0, speaker=Speaker.LLAMANTE, text=text))
        state = apply_reading(state, RulesReader().read(state.turns, line))
    return state


def _stage(state: CallState, stage_id: StageId) -> StageStatus:
    return next(s.status for s in state.stages if s.id is stage_id)


def _signal(signal_id: SignalId, value: SignalAnswer = SI) -> SignalValue:
    return SignalValue(
        signal_id=signal_id, value=value, source=Source.REGLAS, confidence=Confidence.PROBABLE
    )


def _incident(category: Category, subtype: Subtype | None = None) -> Incident:
    return Incident(
        category=category, subtype=subtype, confidence=Confidence.PROBABLE, source=Source.REGLAS
    )


# Caso 001


def test_case_001_is_incendio_en_comercio_p1_with_its_porque() -> None:
    state = _call_with(PIZZERIA)
    assert state.incident is not None
    assert state.incident.category is Category.INCENDIO_RESCATE
    assert state.incident.subtype is Subtype.INCENDIO_COMERCIO
    assert state.incident.confidence is Confidence.PROBABLE
    assert state.priority is not None
    assert state.priority.level is Priority.P1
    assert [r.signal_id for r in state.priority.reasons] == [S.PERSONA_ATRAPADA, S.HUMO]
    assert [r.evidence.quote for r in state.priority.reasons if r.evidence] == [
        "adentro quedó el cocinero",
        "humo negro al salón",
    ]
    assert _stage(state, StageId.QUE_PASA) is StageStatus.ACTUAL


# Tabla de prioridad


@pytest.mark.parametrize(
    ("signals", "incident", "level"),
    [
        ([_signal(S.RESPIRA, NO)], None, Priority.P1),
        ([_signal(S.CONSCIENTE, NO)], None, Priority.P1),
        ([_signal(S.PERSONA_ATRAPADA), _signal(S.FUEGO_ACTIVO)], None, Priority.P1),
        ([_signal(S.PERSONA_ATRAPADA)], None, Priority.P2),
        ([_signal(S.FUEGO_ACTIVO)], None, Priority.P2),
        ([_signal(S.GAS)], None, Priority.P2),
        ([], _incident(Category.EMERGENCIA_MEDICA), Priority.P2),
        ([], _incident(Category.SERVICIOS_PUBLICOS, Subtype.SEMAFOROS), Priority.P3),
        ([], _incident(Category.SERVICIOS_PUBLICOS, Subtype.ALUMBRADO), Priority.P4),
        (
            [_signal(S.CABLES_CAIDOS)],
            _incident(Category.SERVICIOS_PUBLICOS, Subtype.PODA),
            Priority.P2,
        ),
        (
            [_signal(S.FUEGO_ACTIVO, NO)],
            _incident(Category.SERVICIOS_PUBLICOS, Subtype.BACHE),
            Priority.P4,
        ),
    ],
)
def test_priority_table(
    signals: list[SignalValue], incident: Incident | None, level: Priority
) -> None:
    assessed = assess(incident, signals)
    assert assessed is not None
    assert assessed.level is level
    assert assessed.rule


def test_no_tipo_and_no_risk_signal_means_no_priority_yet() -> None:
    assert assess(None, [_signal(S.MENORES)]) is None


def test_the_first_rule_wins_and_its_signals_are_the_porque() -> None:
    assessed = assess(None, [_signal(S.FUEGO_ACTIVO), _signal(S.EXPLOSION), _signal(S.HUMO)])
    assert assessed is not None
    assert assessed.rule == "Explosión"
    assert [r.signal_id for r in assessed.reasons] == [S.EXPLOSION]


# Verificación y coherencia


def test_a_signal_with_an_invented_quote_is_discarded() -> None:
    state = _call_with("Hola, es en Corrientes 1540")
    fake = SignalReading(
        signal_id=S.PERSONA_ATRAPADA,
        value=SI,
        evidence=Evidence(turn_index=0, start=0, end=21, quote="quedó un nene atrapado"),
    )
    after = apply_reading(state, ReaderOutput(signals=[fake]))
    assert after.signals == []
    assert after.priority is None


def test_incoherent_signals_go_to_a_confirmar() -> None:
    state = _call_with("No respira pero está consciente")
    by_id = {s.signal_id: s for s in state.signals}
    assert by_id[S.RESPIRA].confidence is Confidence.A_CONFIRMAR
    assert by_id[S.CONSCIENTE].confidence is Confidence.A_CONFIRMAR


def test_a_close_call_on_the_tipo_is_a_confirmar() -> None:
    state = _call_with("hay humo y una pelea")
    assert state.incident is not None
    assert state.incident.confidence is Confidence.A_CONFIRMAR


# Pregunta universal y etapa ②


def test_victims_with_unknown_vital_signs_ask_the_universal_question() -> None:
    state = _call_with(AQUI + "mi mamá se cayó y le duele la cadera", line=Line.L107)
    assert state.next_question is not None
    assert state.next_question.id == "universal"
    assert state.next_question.signal_ids == [S.CONSCIENTE, S.RESPIRA]


def test_only_the_missing_vital_sign_is_asked() -> None:
    state = _call_with(AQUI + "convulsiona y no responde", line=Line.L107)
    assert state.next_question is not None
    assert state.next_question.signal_ids == [S.RESPIRA]


def test_someone_who_does_not_breathe_needs_no_universal_question() -> None:
    state = _call_with(AQUI + "mi hija no respira", line=Line.L107)
    assert state.next_question is None


def test_no_victims_no_universal_question() -> None:
    state = _call_with(AQUI + "se apagaron los semáforos")
    assert state.next_question is not None
    assert state.next_question.id != "universal"


def test_the_ubicación_is_asked_before_the_universal_question() -> None:
    state = _call_with("mi mamá se cayó y le duele la cadera", line=Line.L107)
    assert state.next_question is not None
    assert state.next_question.text == "¿Dónde es la emergencia?"


def test_stage_two_is_done_when_tipo_confirmed_and_vital_risk_evaluated() -> None:
    state = _call_with("mi mamá se cayó y le duele la cadera", line=Line.L107)
    state = confirm_type(state)
    assert _stage(state, StageId.QUE_PASA) is StageStatus.ACTUAL
    state = add_turn(
        state,
        Turn(index=1, at_ms=0, speaker=Speaker.LLAMANTE, text="Sí, está consciente y respira"),
    )
    state = apply_reading(state, RulesReader().read(state.turns, Line.L107))
    assert _stage(state, StageId.QUE_PASA) is StageStatus.HECHA


def test_without_victims_confirming_the_tipo_closes_stage_two() -> None:
    state = confirm_type(_call_with("se apagaron los semáforos de la esquina"))
    assert _stage(state, StageId.QUE_PASA) is StageStatus.HECHA


# Acciones del operador


def test_a_confirmed_tipo_is_never_overwritten() -> None:
    state = confirm_type(_call_with("se apagaron los semáforos"))
    state = add_turn(
        state, Turn(index=1, at_ms=0, speaker=Speaker.LLAMANTE, text="hay fuego, llamas y humo")
    )
    state = apply_reading(state, RulesReader().read(state.turns))
    assert state.incident is not None
    assert state.incident.category is Category.SERVICIOS_PUBLICOS
    assert state.incident.confidence is Confidence.CONFIRMADO


def test_operador_can_set_another_tipo() -> None:
    state = confirm_type(_call_with(PIZZERIA), Category.DEFENSA_CIVIL, Subtype.FUGA_GAS)
    assert state.incident is not None
    assert state.incident.source is Source.OPERADOR
    assert state.incident.subtype is Subtype.FUGA_GAS


def test_subtipo_must_belong_to_its_tipo() -> None:
    with pytest.raises(ValueError, match="subtipo"):
        confirm_type(_call_with(PIZZERIA), Category.DEFENSA_CIVIL, Subtype.CONVULSION)


def test_confirm_without_tipo_fails() -> None:
    with pytest.raises(NoIncidentError):
        confirm_type(_call_with("Hola"))


def test_set_priority_keeps_the_porque_and_survives_new_readings() -> None:
    state = set_priority(_call_with(PIZZERIA), Priority.P2, "el cocinero ya salió")
    assert state.priority is not None
    assert state.priority.level is Priority.P2
    assert state.priority.overridden_by_operator is not None
    assert state.priority.overridden_by_operator.from_level is Priority.P1
    assert state.priority.reasons
    state = add_turn(state, Turn(index=1, at_ms=0, speaker=Speaker.LLAMANTE, text="hay humo"))
    state = apply_reading(state, RulesReader().read(state.turns))
    assert state.priority is not None and state.priority.level is Priority.P2


def test_set_priority_without_reason_fails() -> None:
    with pytest.raises(ValueError, match="motivo"):
        set_priority(_call_with(PIZZERIA), Priority.P3, "  ")
