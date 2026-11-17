"""Etapa ⑤ and the instrucción crítica (SPEC §5.8, DESIGN §2 regla 3)."""

from typing import Any

import pytest

from app.catalog.incidents import Subtype
from app.catalog.loader import parse_dataset
from app.catalog.models import Category, Priority
from app.catalog.signals import SignalAnswer, SignalId
from app.config import REPO_ROOT
from app.engine.models import (
    CallState,
    Confidence,
    Line,
    Mode,
    SignalValue,
    Source,
    StageId,
    StageStatus,
)
from app.engine.state import (
    UnknownInstructionError,
    add_turn,
    apply_reading,
    confirm_type,
    mark_instruction_read,
    new_call,
    set_priority,
)
from app.readers.models import ReaderOutput
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn
from app.transcript.parser import parse_transcript

PIZZERIA = (
    "Hola, por favor manden a los bomberos ya! En la pizzería de Av. Corrientes 1540 casi "
    "Montevideo, se prendió fuego la campana de la cocina y se está metiendo el humo negro al "
    "salón, la gente salió corriendo a la calle pero adentro quedó el cocinero!"
)
CASES = {c.id[-3:]: c for c in parse_dataset(REPO_ROOT / "data" / "dataset_challenge_soflex.csv")}


def _say(state: CallState, text: str) -> CallState:
    turn = Turn(index=len(state.turns), at_ms=0, speaker=Speaker.LLAMANTE, text=text)
    state = add_turn(state, turn)
    return apply_reading(state, RulesReader().read(state.turns, Line.L911))


def _replay(case_id: str) -> CallState:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    for i, parsed in enumerate(parse_transcript(CASES[case_id].transcript)):
        turn = Turn(index=i, at_ms=0, speaker=parsed.speaker, text=parsed.text)
        state = apply_reading(
            add_turn(state, turn), RulesReader().read([*state.turns, turn], Line.L911)
        )
    return state


def _stage(state: CallState, stage_id: StageId) -> Any:
    return next(s for s in state.stages if s.id is stage_id)


def _with_signals(*facts: tuple[SignalId, SignalAnswer]) -> CallState:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    signals = [
        SignalValue(signal_id=s, value=v, source=Source.OPERADOR, confidence=Confidence.CONFIRMADO)
        for s, v in facts
    ]
    return apply_reading(state.model_copy(update={"signals": signals}), ReaderOutput())


def test_caso_001_shows_the_critica_from_the_first_turno() -> None:
    state = _say(new_call("c1", Line.L911, Mode.SIMULADO), PIZZERIA)
    assert state.critical_instruction is not None
    assert state.critical_instruction.text == "No vuelva a entrar al local por ningún motivo."
    assert state.instructions[0] == state.critical_instruction
    assert state.instructions[1].instruction_id == "vereda_enfrente"
    # The bar is still at ①: the crítica does not wait for its etapa.
    assert _stage(state, StageId.UBICAR).status is StageStatus.ACTUAL
    assert _stage(state, StageId.INSTRUCCIONES).alert


def test_caso_001_replayed_keeps_one_critica() -> None:
    state = _replay("001")
    assert [i.critical for i in state.instructions].count(True) == 1
    assert state.critical_instruction is not None
    assert state.critical_instruction.instruction_id == "critica_no_reingresar_local"


def test_a_pastizal_fire_never_says_no_tire_agua() -> None:
    state = _replay("004")
    assert state.incident is not None and state.incident.subtype is Subtype.INCENDIO_PASTIZAL
    assert state.instructions
    assert not any("tire agua" in i.text for i in state.instructions)


def test_an_electrico_fire_says_no_tire_agua_first_after_the_critica() -> None:
    state = _replay("017")
    ids = [i.instruction_id for i in state.instructions]
    assert ids[0] == "critica_humo"
    assert ids[1] == "no_agua_electrico"


@pytest.mark.parametrize(
    ("case_id", "critica"),
    [
        ("005", "critica_no_sacar_casco"),
        ("009", "critica_no_respira"),
        ("012", "critica_gas"),
        ("018", "critica_no_sacar_del_vehiculo"),
        ("020", "critica_no_tocar_cable"),
        ("026", "critica_inconsciente"),
    ],
)
def test_every_p1_case_gets_its_critica(case_id: str, critica: str) -> None:
    state = _replay(case_id)
    assert state.critical_instruction is not None
    assert state.critical_instruction.instruction_id == critica


def test_without_a_p1_senal_there_is_no_critica() -> None:
    state = _replay("010")
    assert state.priority is not None and state.priority.level is not Priority.P1
    assert state.critical_instruction is None
    assert not any(i.critical for i in state.instructions)


def test_only_one_critica_is_active_and_the_others_are_read_as_normal() -> None:
    state = _with_signals(
        (SignalId.CONSCIENTE, SignalAnswer.NO),
        (SignalId.SANGRADO_ABUNDANTE, SignalAnswer.SI),
    )
    ids = [i.instruction_id for i in state.instructions]
    assert ids == ["critica_inconsciente", "critica_sangrado"]
    assert [i.critical for i in state.instructions] == [True, False]


def test_lowering_the_prioridad_does_not_hide_the_critica() -> None:
    state = _say(new_call("c1", Line.L911, Mode.SIMULADO), PIZZERIA)
    state = set_priority(state, Priority.P3, "el llamante exagera")
    assert state.critical_instruction is not None


def test_the_subtipo_instrucciones_appear_when_the_subtipo_is_known() -> None:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    assert state.instructions == []
    state = confirm_type(state, Category.EMERGENCIA_MEDICA, Subtype.CONVULSION)
    ids = [i.instruction_id for i in state.instructions]
    assert ids == ["no_objetos_boca", "convulsion_espacio", "convulsion_lateral"]


def test_marking_every_instruccion_read_finishes_etapa_5() -> None:
    state = _say(new_call("c1", Line.L911, Mode.SIMULADO), PIZZERIA)
    assert _stage(state, StageId.INSTRUCCIONES).status is StageStatus.ACTUAL
    critical = state.instructions[0].instruction_id
    state = mark_instruction_read(state, critical)
    assert state.critical_instruction is not None and state.critical_instruction.read
    assert not _stage(state, StageId.INSTRUCCIONES).alert
    assert mark_instruction_read(state, critical) == state  # twice changes nothing
    for item in state.instructions:
        state = mark_instruction_read(state, item.instruction_id)
    assert _stage(state, StageId.INSTRUCCIONES).status is StageStatus.HECHA


def test_an_instruccion_that_does_not_apply_cannot_be_marked() -> None:
    state = _say(new_call("c1", Line.L911, Mode.SIMULADO), PIZZERIA)
    with pytest.raises(UnknownInstructionError):
        mark_instruction_read(state, "no_agua_electrico")


def _property_names(schema: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        names |= set(schema.get("properties", {}))
        for value in schema.values():
            names |= _property_names(value)
    elif isinstance(schema, list):
        for value in schema:
            names |= _property_names(value)
    return names


def test_no_lector_can_bring_instruccion_text() -> None:
    """ADR 0001: the IA proposes señales with evidence; it never writes an instrucción."""
    names = _property_names(ReaderOutput.model_json_schema())
    assert names, "the schema has fields"
    assert not any("instruc" in name or "instruction" in name for name in names)
    assert set(ReaderOutput.model_fields) == {"location", "incident", "signals"}
