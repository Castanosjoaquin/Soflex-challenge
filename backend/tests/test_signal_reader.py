import pytest

from app.catalog.signals import SignalAnswer, SignalId
from app.readers.models import SignalReading
from app.readers.rules.signals import read_signals
from app.transcript.models import Speaker, Turn

S = SignalId
SI, NO, NO_SABE = SignalAnswer.SI, SignalAnswer.NO, SignalAnswer.NO_SABE

PIZZERIA = (
    "Hola, por favor manden a los bomberos ya! En la pizzería de Av. Corrientes 1540 casi "
    "Montevideo, se prendió fuego la campana de la cocina y se está metiendo el humo negro al "
    "salón, la gente salió corriendo a la calle pero adentro quedó el cocinero!"
)


def _read(*texts: str, speaker: Speaker = Speaker.LLAMANTE) -> dict[SignalId, SignalReading]:
    turns = [Turn(index=i, at_ms=0, speaker=speaker, text=t) for i, t in enumerate(texts)]
    return {s.signal_id: s for s in read_signals(turns)}


def test_case_001_reads_atrapada_humo_and_fuego_with_their_phrases() -> None:
    signals = _read(PIZZERIA)
    assert signals[S.PERSONA_ATRAPADA].value is SI
    assert signals[S.PERSONA_ATRAPADA].evidence.quote == "adentro quedó el cocinero"
    assert signals[S.HUMO].evidence.quote == "humo negro al salón"
    assert signals[S.FUEGO_ACTIVO].evidence.quote.startswith("se prendió fuego")


def test_evidence_offsets_point_into_the_original_text() -> None:
    for signal in _read(PIZZERIA).values():
        ev = signal.evidence
        assert PIZZERIA[ev.start : ev.end] == ev.quote


@pytest.mark.parametrize(
    ("text", "signal", "value"),
    [
        ("No respira", S.RESPIRA, NO),
        ("Sí, respira", S.RESPIRA, SI),
        ("No hay fuego por ahora", S.FUEGO_ACTIVO, NO),
        ("No hay heridos", S.HERIDOS, NO),
        ("No sé si respira", S.RESPIRA, NO_SABE),
        ("no sabemos si quedó alguien adentro", S.PERSONA_ATRAPADA, NO_SABE),
        ("Está inconsciente", S.CONSCIENTE, NO),
        ("tiene espuma en la boca y no responde", S.CONSCIENTE, NO),
        ("el humo es picante, no se puede respirar", S.RESPIRA, None),
        ("no había nadie en el patio", S.PERSONA_ATRAPADA, NO),
    ],
)
def test_negations_and_unknowns(text: str, signal: SignalId, value: SignalAnswer | None) -> None:
    found = _read(text).get(signal)
    assert (found.value if found else None) is value


@pytest.mark.parametrize(
    ("text", "signal", "value", "quote"),
    [
        # The demo turnos as first written (#24), before they were reworded around this.
        (
            "Heridos no. Un colectivo quedó parado en el medio del agua.",
            S.HERIDOS,
            NO,
            "Heridos no",
        ),
        (
            "uno sacó un cuchillo, lo estoy viendo desde la esquina. Disparos no escuché.",
            S.ARMA_FUEGO,
            NO,
            "Disparos no escuché",
        ),
        ("Fuego no hay, pero sale mucho humo", S.FUEGO_ACTIVO, NO, "Fuego no hay"),
        ("¿Heridos? Heridos, no.", S.HERIDOS, NO, "Heridos, no"),
        # A "no" after the phrase that opens something else, or asks, leaves it as said.
        ("Hay humo, no?", S.HUMO, SI, None),
        ("hay un herido no sabemos si respira", S.HERIDOS, SI, "herido"),
        ("está herido no responde", S.HERIDOS, SI, "herido"),
        ("hay humo no puedo respirar", S.HUMO, SI, None),
    ],
)
def test_a_negation_after_the_phrase(
    text: str, signal: SignalId, value: SignalAnswer, quote: str | None
) -> None:
    found = _read(text)[signal]
    assert found.value is value
    if quote is not None:
        assert found.evidence.quote == quote


def test_one_phrase_backs_one_signal() -> None:
    signals = _read("no le entra el aire")
    assert signals[S.RESPIRA].value is NO
    assert S.DIFICULTAD_RESPIRAR not in signals


def test_the_last_mention_wins() -> None:
    signals = _read("Se desmayó una señora. Ahora recuperó la conciencia.")
    assert signals[S.CONSCIENTE].value is SI


def test_later_turno_overrides_earlier_one() -> None:
    signals = _read("Hay fuego en la cocina", "Ya no hay fuego")
    assert signals[S.FUEGO_ACTIVO].value is NO
    assert signals[S.FUEGO_ACTIVO].evidence.turn_index == 1


def test_operador_turnos_are_not_read() -> None:
    assert _read("¿Respira? ¿Hay fuego?", speaker=Speaker.OPERADOR) == {}


def test_false_friends_are_not_signals() -> None:
    signals = _read("le dimos los disparos de salbutamol y el auto mordió el guardarraíl")
    assert S.ARMA_FUEGO not in signals
    assert S.ANIMAL_MORDEDURA not in signals


def test_menores_by_age() -> None:
    assert _read("mi hija de 8 años")[S.MENORES].value is SI
    assert S.MENORES not in _read("un chico de 24 años")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Arriba hay departamentos, ya sale humo por la ventana del primer piso", SI),
        ("el humo ya pasó al local de al lado", SI),
        ("se está metiendo el humo negro al salón", None),
    ],
)
def test_propagation_is_reaching_other_floors_or_linderos(
    text: str, expected: SignalAnswer | None
) -> None:
    assert _value(text, SignalId.PROPAGACION) is expected


def test_people_leaving_is_an_evacuation() -> None:
    assert _value("la gente salió corriendo a la calle", SignalId.EVACUADO) is SI


def _value(text: str, signal_id: SignalId) -> SignalAnswer | None:
    reading = _read(text).get(signal_id)
    return reading.value if reading else None
