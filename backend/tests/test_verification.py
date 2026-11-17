from app.engine.verification import verify
from app.readers.models import Evidence
from app.transcript.models import Speaker, Turn

TEXT = "se está metiendo el humo negro al salón, adentro quedó el cocinero!"
TURNS = [
    Turn(index=0, at_ms=0, speaker=Speaker.OPERADOR, text="911, ¿cuál es su emergencia?"),
    Turn(index=1, at_ms=0, speaker=Speaker.LLAMANTE, text=TEXT),
]


def _ev(quote: str, turn_index: int = 1, start: int = 0) -> Evidence:
    return Evidence(turn_index=turn_index, start=start, end=start + len(quote), quote=quote)


def test_exact_offsets_are_kept() -> None:
    start = TEXT.index("humo negro")
    ev = _ev("humo negro al salón", start=start)
    assert verify(ev, TURNS) == ev


def test_normalized_match_relocates_onto_the_original_text() -> None:
    found = verify(_ev("HUMO NEGRO AL SALON"), TURNS)
    assert found is not None
    assert found.quote == "humo negro al salón"
    assert TEXT[found.start : found.end] == found.quote


def test_fuzzy_match_at_ninety_percent() -> None:
    found = verify(_ev("adentro quedo el cosinero"), TURNS)
    assert found is not None
    assert found.quote == "adentro quedó el cocinero"


def test_wrong_turn_index_still_finds_the_llamante_turno() -> None:
    found = verify(_ev("adentro quedó el cocinero", turn_index=7), TURNS)
    assert found is not None and found.turn_index == 1


def test_invented_quote_is_discarded() -> None:
    assert verify(_ev("hay tres personas atrapadas en el baño"), TURNS) is None


def test_a_quote_from_the_operador_is_discarded() -> None:
    assert verify(_ev("cuál es su emergencia", turn_index=0), TURNS) is None


def test_a_word_fragment_is_not_a_match() -> None:
    assert verify(_ev("umo negr"), TURNS) is None
