import pytest

from app.catalog.models import Priority
from app.catalog.signals import SignalAnswer
from app.engine import carta
from app.engine.models import (
    CallState,
    Carta,
    CartaDato,
    CartaOrigin,
    Confidence,
    Line,
    Mode,
    StageId,
    StageStatus,
)
from app.engine.state import (
    AlreadyDerivedError,
    NotDerivableError,
    add_turn,
    answer_question,
    apply_reading,
    confirm_location,
    confirm_premark,
    confirm_type,
    derive,
    mark_instruction_read,
    new_call,
    set_priority,
    skip_question,
)
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn

PIZZERIA = (
    "Hola, por favor manden a los bomberos ya! En la pizzería de Av. Corrientes 1540 casi "
    "Montevideo, se prendió fuego la campana de la cocina y se está metiendo el humo negro al "
    "salón, la gente salió corriendo a la calle pero adentro quedó el cocinero!"
)
GARRAFA = "Sí, hay una garrafa grande al lado de la cocina."


def _say(state: CallState, text: str) -> CallState:
    turn = Turn(index=len(state.turns), at_ms=0, speaker=Speaker.LLAMANTE, text=text)
    state = add_turn(state, turn)
    return apply_reading(state, RulesReader().read(state.turns, Line.L911))


def _pizzeria() -> CallState:
    return _say(new_call("c1", Line.L911, Mode.SIMULADO), PIZZERIA)


def _confirmed() -> CallState:
    return confirm_type(confirm_location(_pizzeria()))


def _line(lines: list[CartaDato], key: str) -> CartaDato:
    return next(d for d in lines if d.key == key)


def _stage(state: CallState, stage_id: StageId) -> StageStatus:
    return next(s.status for s in state.stages if s.id is stage_id)


def test_unconfirmed_data_stays_out_of_the_carta() -> None:
    state = _pizzeria()
    assert state.location is not None and state.location.confidence is Confidence.PROBABLE
    assert state.signals, "the relato has señales, all probable"
    c = state.carta
    assert (c.where, c.what, c.priority, c.at_risk, c.instructions) == ([], [], [], [], [])
    assert not state.can_derive
    assert _stage(state, StageId.DERIVAR) is StageStatus.PENDIENTE


def test_carta_with_ubicacion_and_tipo_confirmed_says_where_each_dato_comes_from() -> None:
    state = _confirmed()
    assert state.can_derive
    said = _line(state.carta.where, "ubicacion.dicho")
    assert (said.origin, said.quote) == (
        CartaOrigin.LLAMANTE,
        "Av. Corrientes 1540 casi Montevideo",
    )
    address = _line(state.carta.where, "ubicacion.direccion")
    assert address.origin is CartaOrigin.SISTEMA
    assert "1540" in address.value and "casi" in address.value
    tipo = _line(state.carta.what, "incidente.tipo")
    assert (tipo.value, tipo.origin) == ("Incendio y rescate", CartaOrigin.LLAMANTE)
    assert tipo.quote
    priority = _line(state.carta.priority, "prioridad")
    assert (priority.value, priority.origin) == ("P1", CartaOrigin.SISTEMA)
    # The persona atrapada is still a pre-marca: not in «quién está en riesgo».
    assert state.carta.at_risk == []
    assert all(d.origin is not None for d in state.carta.where + state.carta.what)


def test_carta_has_no_probable_or_a_confirmar_signal() -> None:
    state = confirm_premark(_confirmed(), "inc_atrapados")
    confirmed_keys = {
        f"senal.{s.signal_id.value}" for s in state.signals if s.confidence is Confidence.CONFIRMADO
    }
    unconfirmed_keys = {
        f"senal.{s.signal_id.value}"
        for s in state.signals
        if s.confidence is not Confidence.CONFIRMADO
    }
    keys = {d.key for d in state.carta.what + state.carta.at_risk if d.key.startswith("senal.")}
    assert keys == confirmed_keys
    assert not keys & unconfirmed_keys
    atrapada = _line(state.carta.at_risk, "senal.persona_atrapada")
    assert (atrapada.value, atrapada.quote) == ("Sí", "adentro quedó el cocinero")


def test_skipped_and_pending_preguntas_are_what_is_missing() -> None:
    state = skip_question(_confirmed(), "inc_propagacion")
    missing = {m.text: m.skipped for m in state.carta.missing}
    propagacion = next(i for i in state.checklist if i.question_id == "inc_propagacion")
    assert missing[propagacion.text] is True
    state = answer_question(state, "inc_gas", SignalAnswer.NO)
    gas = next(i for i in state.checklist if i.question_id == "inc_gas")
    assert gas.text not in {m.text for m in state.carta.missing}
    assert _line(state.carta.what, "senal.gas").origin is CartaOrigin.OPERADOR


def test_instrucciones_read_and_priority_changed_by_the_operador() -> None:
    state = _confirmed()
    critical = state.critical_instruction
    assert critical is not None
    state = mark_instruction_read(state, critical.instruction_id)
    (given,) = state.carta.instructions
    assert (given.value, given.origin) == (critical.text, CartaOrigin.OPERADOR)
    state = set_priority(state, Priority.P2, "El cocinero ya salió")
    priority = _line(state.carta.priority, "prioridad")
    why = _line(state.carta.priority, "prioridad.porque")
    assert (priority.value, priority.origin) == ("P2", CartaOrigin.OPERADOR)
    assert "El cocinero ya salió" in why.value


def test_derive_needs_ubicacion_and_tipo_and_happens_once() -> None:
    with pytest.raises(NotDerivableError):
        derive(confirm_type(_pizzeria()))
    state = _confirmed()
    assert _stage(state, StageId.DERIVAR) is StageStatus.ACTUAL
    assert next(s.alert for s in state.stages if s.id is StageId.DERIVAR), "P1: derivá ahora"
    state = derive(state)
    assert state.derived
    assert _stage(state, StageId.DERIVAR) is StageStatus.HECHA
    assert not next(s.alert for s in state.stages if s.id is StageId.DERIVAR)
    with pytest.raises(AlreadyDerivedError):
        derive(state)


def test_diff_lists_what_appeared_changed_and_went_away() -> None:
    before = _confirmed()
    after = confirm_premark(_say(before, GARRAFA), "inc_gas")
    changes = carta.diff(before.carta, after.carta)
    gas = next(c for c in changes if c.key == "senal.gas")
    assert (gas.label, gas.before, gas.after) == ("Gas", None, "Sí")
    assert carta.diff(after.carta, after.carta) == []
    gone = carta.diff(after.carta, Carta())
    assert all(c.after is None for c in gone) and len(gone) >= 3
