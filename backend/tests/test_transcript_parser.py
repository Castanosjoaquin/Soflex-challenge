from app.catalog.loader import parse_dataset
from app.config import REPO_ROOT
from app.transcript.models import Speaker
from app.transcript.parser import parse_transcript

DATASET = REPO_ROOT / "data" / "dataset_challenge_soflex.csv"


def test_splits_operador_and_llamante() -> None:
    turns = parse_transcript("Operador: 911, ¿dónde es? Llamante: En Thames 1900.")
    assert [(t.speaker, t.text) for t in turns] == [
        (Speaker.OPERADOR, "911, ¿dónde es?"),
        (Speaker.LLAMANTE, "En Thames 1900."),
    ]


def test_text_without_prefixes_is_one_llamante_turn() -> None:
    turns = parse_transcript("  Se prendió fuego la cocina  ")
    assert [(t.speaker, t.text) for t in turns] == [
        (Speaker.LLAMANTE, "Se prendió fuego la cocina")
    ]


def test_empty_text_has_no_turns() -> None:
    assert parse_transcript("   ") == []


def test_prefixes_are_case_insensitive_and_multi_turn() -> None:
    raw = "OPERADOR: ¿Dirección? llamante: Corrientes. Operador: ¿Altura? Llamante: 1540"
    turns = parse_transcript(raw)
    assert [t.speaker for t in turns] == [
        Speaker.OPERADOR,
        Speaker.LLAMANTE,
        Speaker.OPERADOR,
        Speaker.LLAMANTE,
    ]
    assert turns[-1].text == "1540"


def test_preamble_before_first_prefix_goes_to_llamante() -> None:
    turns = parse_transcript("Hola? Operador: 911.")
    assert [(t.speaker, t.text) for t in turns] == [
        (Speaker.LLAMANTE, "Hola?"),
        (Speaker.OPERADOR, "911."),
    ]


def test_every_dataset_call_has_operador_then_llamante() -> None:
    for case in parse_dataset(DATASET):
        turns = parse_transcript(case.transcript)
        assert [t.speaker for t in turns] == [Speaker.OPERADOR, Speaker.LLAMANTE], case.id
