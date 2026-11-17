"""Autocorrección vs. contradicción (SPEC §5.4.5, issue #8): never overwrite what is confirmed."""

import contextlib
import random
from collections.abc import Callable

import pytest

from app.catalog.models import Category, Priority
from app.catalog.signals import SignalAnswer, SignalId
from app.engine.contradictions import Resolution, UnknownAvisoError
from app.engine.models import AvisoKind, AvisoStatus, CallState, Confidence, Line, Mode
from app.engine.state import (
    UnknownQuestionError,
    add_turn,
    answer_question,
    apply_reading,
    confirm_location,
    confirm_type,
    correct_location,
    new_call,
    resolve_contradiction,
    set_priority,
)
from app.readers.models import (
    Evidence,
    IncidentReading,
    LocationReading,
    NumberKind,
    ReaderOutput,
    SignalReading,
    StreetNumber,
)
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn

S = SignalId
SI, NO, NO_SABE = SignalAnswer.SI, SignalAnswer.NO, SignalAnswer.NO_SABE


def _say(state: CallState, text: str) -> CallState:
    """The llamante says a turno and the rules read the whole relato again."""
    turn = Turn(index=len(state.turns), at_ms=0, speaker=Speaker.LLAMANTE, text=text)
    state = add_turn(state, turn)
    return apply_reading(state, RulesReader().read(state.turns))


def _call(*texts: str) -> CallState:
    state = new_call("c1", Line.L911, Mode.SIMULADO)
    for text in texts:
        state = _say(state, text)
    return state


def _altura(state: CallState) -> int | None:
    assert state.location is not None
    assert state.location.number is not None
    return state.location.number.value


def _pending(state: CallState) -> list[str]:
    return [a.text for a in state.avisos if a.status is AvisoStatus.PENDIENTE]


# Autocorrección: a dato not confirmed takes the latest value, silently.


def test_unconfirmed_altura_takes_the_latest_value_without_aviso() -> None:
    state = _call("Es en Av. Corrientes 1540 casi Montevideo", "No, perdón, es en el 1450")
    assert _altura(state) == 1450
    assert state.location is not None
    assert state.location.confidence is not Confidence.CONFIRMADO
    assert state.avisos == []


def test_unconfirmed_street_takes_the_latest_official_street_without_aviso() -> None:
    state = _call("Es en Av. Corrientes 1540", "No, perdón, es en Callao 300")
    assert state.location is not None
    assert state.location.street == "Callao"
    assert state.avisos == []


# Contradicción: a confirmed dato stays, and the operador gets an aviso.


def _confirmed_1540() -> CallState:
    return confirm_location(_call("Es en Av. Corrientes 1540 casi Montevideo"))


def test_confirmed_altura_stays_and_raises_the_aviso_of_the_demo() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en el 1450")
    assert _altura(state) == 1540
    assert state.location is not None
    assert state.location.confidence is Confidence.CONFIRMADO
    [aviso] = state.avisos
    assert aviso.kind is AvisoKind.CONTRADICCION
    assert aviso.text == "Antes dijo 1540, ahora dice 1450"
    assert aviso.label == "Altura"
    assert [e.quote for e in aviso.evidence] == ["en el 1450"]
    assert aviso.status is AvisoStatus.PENDIENTE


def test_accepting_takes_the_new_altura_confirmed() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en el 1450")
    state = resolve_contradiction(state, state.avisos[0].id, Resolution.ACEPTAR)
    assert _altura(state) == 1450
    assert state.location is not None
    assert state.location.confidence is Confidence.CONFIRMADO
    assert state.avisos[0].status is AvisoStatus.ACEPTADO
    assert _pending(state) == []
    assert state.carta.where[-1].value.endswith("1450, casi MONTEVIDEO")


def test_keeping_leaves_the_altura_and_the_same_relato_does_not_ask_again() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en el 1450")
    state = resolve_contradiction(state, state.avisos[0].id, Resolution.MANTENER)
    assert _altura(state) == 1540
    assert state.avisos[0].status is AvisoStatus.MANTENIDO
    state = _say(state, "Apúrense por favor")
    assert _altura(state) == 1540
    assert _pending(state) == []


def test_the_relato_repeating_itself_raises_one_aviso_only() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en el 1450")
    state = _say(state, "Hay mucho humo")
    assert len(state.avisos) == 1


def test_a_new_change_replaces_the_pending_aviso_of_the_same_dato() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en el 1450")
    state = _say(state, "No, no, es en el 1460")
    assert _pending(state) == ["Antes dijo 1540, ahora dice 1460"]
    assert len({a.id for a in state.avisos}) == len(state.avisos)


def test_another_street_is_a_contradiction_of_the_whole_direccion() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en Callao 300")
    [aviso] = state.avisos
    assert aviso.label == "Dirección"
    assert (
        aviso.text == "Antes dijo AV. CORRIENTES 1540, casi MONTEVIDEO, ahora dice AV. CALLAO 300"
    )


def test_the_relato_saying_the_same_as_confirmed_raises_nothing() -> None:
    state = _say(_confirmed_1540(), "Sí, Corrientes 1540")
    assert state.avisos == []


def test_a_direccion_corrected_by_the_operador_is_not_contradicted_by_the_old_relato() -> None:
    state = _call("Es en Av. Corrientes 1540")
    state = correct_location(
        state,
        street="Av. Corrientes",
        number=StreetNumber(value=1450, kind=NumberKind.EXACTA),
        cross_streets=[],
    )
    state = _say(state, "Hay mucho humo")
    assert state.avisos == []
    assert _altura(state) == 1450


def test_resolving_an_unknown_or_resolved_aviso_fails() -> None:
    state = _say(_confirmed_1540(), "No, perdón, es en el 1450")
    with pytest.raises(UnknownAvisoError):
        resolve_contradiction(state, "aviso-99", Resolution.ACEPTAR)
    state = resolve_contradiction(state, state.avisos[0].id, Resolution.MANTENER)
    with pytest.raises(UnknownAvisoError):
        resolve_contradiction(state, state.avisos[0].id, Resolution.ACEPTAR)


# Hand-built lecturas, for tipo and señales.


def _ev(state: CallState, quote: str) -> Evidence:
    for turn in state.turns:
        if (start := turn.text.find(quote)) >= 0:
            return Evidence(turn_index=turn.index, start=start, end=start + len(quote), quote=quote)
    raise AssertionError(quote)


Reading = Callable[[CallState], ReaderOutput]


def _hear(state: CallState, text: str, reading: Reading) -> CallState:
    turn = Turn(index=len(state.turns), at_ms=0, speaker=Speaker.LLAMANTE, text=text)
    state = add_turn(state, turn)
    return apply_reading(state, reading(state))


def _incident(category: Category, quote: str) -> Reading:
    return lambda s: ReaderOutput(
        incident=IncidentReading(category=category, evidence=[_ev(s, quote)])
    )


def _medical(*signals: tuple[SignalId, SignalAnswer, str]) -> Reading:
    return lambda s: ReaderOutput(
        incident=IncidentReading(
            category=Category.EMERGENCIA_MEDICA, evidence=[_ev(s, "se descompuso")]
        ),
        signals=[
            SignalReading(signal_id=signal_id, value=value, evidence=_ev(s, quote))
            for signal_id, value, quote in signals
        ],
    )


def _new() -> CallState:
    return new_call("c1", Line.L911, Mode.SIMULADO)


def test_confirmed_tipo_stays_and_raises_an_aviso() -> None:
    state = _hear(_new(), "Hay humo en la cocina", _incident(Category.INCENDIO_RESCATE, "humo"))
    state = confirm_type(state)
    state = _hear(state, "No, es un choque", _incident(Category.ACCIDENTE_VIAL, "un choque"))
    assert state.incident is not None
    assert state.incident.category is Category.INCENDIO_RESCATE
    [aviso] = state.avisos
    assert aviso.label == "Tipo"
    assert aviso.target == "incident"
    state = resolve_contradiction(state, aviso.id, Resolution.ACEPTAR)
    assert state.incident is not None
    assert state.incident.category is Category.ACCIDENTE_VIAL
    assert state.incident.confidence is Confidence.CONFIRMADO


def test_unconfirmed_tipo_changes_without_aviso() -> None:
    state = _hear(_new(), "Hay humo en la cocina", _incident(Category.INCENDIO_RESCATE, "humo"))
    state = _hear(state, "No, es un choque", _incident(Category.ACCIDENTE_VIAL, "un choque"))
    assert state.incident is not None
    assert state.incident.category is Category.ACCIDENTE_VIAL
    assert state.avisos == []


def _breathing_confirmed() -> CallState:
    state = _hear(_new(), "Mi papá se descompuso, respira", _medical((S.RESPIRA, SI, "respira")))
    return answer_question(state, S.RESPIRA.value, SI)


def test_a_respondida_senal_stays_and_raises_an_aviso() -> None:
    state = _hear(
        _breathing_confirmed(),
        "Ahora no respira",
        _medical((S.RESPIRA, NO, "no respira")),
    )
    respira = next(s for s in state.signals if s.signal_id is S.RESPIRA)
    assert (respira.value, respira.confidence) == (SI, Confidence.CONFIRMADO)
    [aviso] = state.avisos
    assert aviso.text == "Antes dijo «Respira: sí», ahora dice «Respira: no»"
    assert [e.quote for e in aviso.evidence] == ["no respira"]
    state = resolve_contradiction(state, aviso.id, Resolution.ACEPTAR)
    respira = next(s for s in state.signals if s.signal_id is S.RESPIRA)
    assert (respira.value, respira.confidence) == (NO, Confidence.CONFIRMADO)
    assert state.priority is not None
    assert state.priority.level is Priority.P1


def test_no_se_sabe_does_not_contradict_a_respondida_senal() -> None:
    state = _hear(
        _breathing_confirmed(), "No sé si respira", _medical((S.RESPIRA, NO_SABE, "si respira"))
    )
    assert state.avisos == []


def test_unconfirmed_senal_takes_the_latest_value_without_aviso() -> None:
    state = _hear(_new(), "Mi papá se descompuso, respira", _medical((S.RESPIRA, SI, "respira")))
    state = _hear(state, "Ahora no respira", _medical((S.RESPIRA, NO, "no respira")))
    respira = next(s for s in state.signals if s.signal_id is S.RESPIRA)
    assert respira.value is NO
    assert state.avisos == []


# Señal de P1 over a prioridad the operador lowered (second review note of #8).


def _lowered_to_p2() -> CallState:
    state = _hear(_new(), "Mi papá se descompuso", _medical())
    state = confirm_type(state)
    return set_priority(state, Priority.P2, "El llamante exagera")


def test_p1_senal_over_a_lowered_prioridad_keeps_it_and_raises_an_aviso() -> None:
    state = _hear(_lowered_to_p2(), "No respira", _medical((S.RESPIRA, NO, "No respira")))
    assert state.priority is not None
    assert state.priority.level is Priority.P2
    [aviso] = state.avisos
    assert aviso.kind is AvisoKind.SENAL_P1
    assert aviso.text == "Apareció una señal de P1 (No respira) y la prioridad está en P2"
    assert [e.quote for e in aviso.evidence] == ["No respira"]
    # The instrucción crítica does not wait for the operador.
    assert state.critical_instruction is not None


def test_accepting_the_p1_aviso_raises_the_prioridad_and_keeps_it_fixed() -> None:
    state = _hear(_lowered_to_p2(), "No respira", _medical((S.RESPIRA, NO, "No respira")))
    state = resolve_contradiction(state, state.avisos[0].id, Resolution.ACEPTAR)
    assert state.priority is not None
    assert state.priority.level is Priority.P1
    assert state.priority.rule == "No respira"
    assert state.priority.overridden_by_operator is not None
    assert state.priority.overridden_by_operator.from_level is Priority.P2


def test_keeping_the_p1_aviso_leaves_the_prioridad_and_does_not_ask_again() -> None:
    state = _hear(_lowered_to_p2(), "No respira", _medical((S.RESPIRA, NO, "No respira")))
    state = resolve_contradiction(state, state.avisos[0].id, Resolution.MANTENER)
    state = _hear(state, "Sigue sin respirar, no respira", _medical((S.RESPIRA, NO, "no respira")))
    assert state.priority is not None
    assert state.priority.level is Priority.P2
    assert _pending(state) == []


def test_operador_answer_that_fires_p1_over_a_lowered_prioridad_raises_the_aviso() -> None:
    state = answer_question(_lowered_to_p2(), S.RESPIRA.value, NO)
    assert state.priority is not None
    assert state.priority.level is Priority.P2
    assert [a.kind for a in state.avisos] == [AvisoKind.SENAL_P1]


def test_p1_senal_known_before_lowering_raises_nothing() -> None:
    state = _hear(
        _new(), "Mi papá se descompuso, no respira", _medical((S.RESPIRA, NO, "no respira"))
    )
    state = confirm_type(state)
    state = set_priority(state, Priority.P2, "Ya lo están reanimando")
    state = _hear(state, "Sigue igual", _medical((S.RESPIRA, NO, "no respira")))
    assert state.avisos == []


def test_without_override_the_prioridad_follows_the_rules_and_says_nothing() -> None:
    state = _hear(_new(), "Mi papá se descompuso", _medical())
    state = _hear(state, "No respira", _medical((S.RESPIRA, NO, "No respira")))
    assert state.priority is not None
    assert state.priority.level is Priority.P1
    assert state.avisos == []


# No lectura ever changes a confirmed dato: a wide, seeded table of random lecturas.

_STREETS = ["Av. Corrientes", "Callao", "Montevideo", "Rivadavia", "Calle Inventada"]
_RELATO = (
    "Es en Av. Corrientes 1540 casi Montevideo. Callao 300. Rivadavia 5000. Calle Inventada 12. "
    "Hay humo y fuego, un choque, se descompuso, no respira, respira, está consciente, no sé."
)
_QUOTES = ["humo", "fuego", "un choque", "se descompuso", "no respira", "respira", "no sé"]


def _random_reading(rng: random.Random, state: CallState) -> ReaderOutput:
    location = None
    if rng.random() < 0.8:
        street = rng.choice(_STREETS)
        location = LocationReading(
            said=street,
            evidence=[_ev(state, street)],
            street=street,
            number=StreetNumber(value=rng.choice([300, 1450, 1540, 5000]), kind=NumberKind.EXACTA),
        )
    incident = None
    if rng.random() < 0.8:
        incident = IncidentReading(
            category=rng.choice(list(Category)), evidence=[_ev(state, rng.choice(_QUOTES))]
        )
    signals = [
        SignalReading(
            signal_id=signal_id,
            value=rng.choice(list(SignalAnswer)),
            evidence=_ev(state, rng.choice(_QUOTES)),
        )
        for signal_id in rng.sample(list(SignalId), k=rng.randint(0, 6))
    ]
    return ReaderOutput(location=location, incident=incident, signals=signals)


def _confirmed(state: CallState) -> dict[str, object]:
    return {
        "location": state.location,
        "incident": state.incident,
        "signals": {s.signal_id: s for s in state.signals if s.confidence is Confidence.CONFIRMADO},
        "priority": state.priority,
    }


@pytest.mark.parametrize("seed", range(100))
def test_no_lectura_modifies_a_confirmed_dato(seed: int) -> None:
    rng = random.Random(seed)
    state = add_turn(_new(), Turn(index=0, at_ms=0, speaker=Speaker.LLAMANTE, text=_RELATO))
    state = apply_reading(state, _random_reading(rng, state))
    if state.location is None:
        state = correct_location(state, street="Callao", number=None, cross_streets=[])
    state = confirm_location(state)
    # Half of them médicas, so that the vital señales can be asked and answered.
    state = confirm_type(
        state, rng.choice([Category.EMERGENCIA_MEDICA, rng.choice(list(Category))])
    )
    for signal_id in rng.sample([S.RESPIRA, S.CONSCIENTE], k=rng.randint(0, 2)):
        with contextlib.suppress(UnknownQuestionError):  # asked only when there are víctimas
            state = answer_question(state, signal_id.value, rng.choice([SI, NO]))
    state = set_priority(state, rng.choice(list(Priority)), "Criterio del operador")
    before = _confirmed(state)
    for _ in range(8):
        state = apply_reading(state, _random_reading(rng, state))
        assert _confirmed(state) == before
    assert all(a.status is AvisoStatus.PENDIENTE for a in state.avisos)
