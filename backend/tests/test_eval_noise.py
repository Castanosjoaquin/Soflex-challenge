"""The generator of variantes ruidosas: seeded, only on the llamante, and in sync with the files."""

from random import Random

import pytest

from app.catalog.loader import parse_dataset
from app.eval.noise import (
    NoiseKind,
    add_fillers,
    asr_typos,
    dump_variants,
    make_variant,
    make_variants,
    number_in_words,
    numbers_in_words,
    self_correction,
    variants_path,
    without_av,
    without_location,
)
from app.readers.rules.location import read_location
from app.transcript.models import ParsedTurn, Speaker, Turn
from app.transcript.normalize import normalize
from tests.conftest import DATASET

PIZZERIA = (
    "Hola, por favor manden a los bomberos ya! En la pizzería de Av. Corrientes 1540 casi "
    "Montevideo, se prendió fuego la campana de la cocina y se está metiendo el humo negro al "
    "salón, la gente salió corriendo a la calle pero adentro quedó el cocinero!"
)
TURNS = [
    ParsedTurn(speaker=Speaker.OPERADOR, text="911 emergencias, ¿dónde es su urgencia?"),
    ParsedTurn(speaker=Speaker.LLAMANTE, text=PIZZERIA),
]


def _location(text: str) -> tuple[str | None, int | None]:
    reading = read_location([Turn(index=0, at_ms=0, speaker=Speaker.LLAMANTE, text=text)])
    if reading is None:
        return None, None
    return reading.street, reading.number.value if reading.number else None


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "cero"),
        (21, "veintiuno"),
        (100, "cien"),
        (105, "ciento cinco"),
        (650, "seiscientos cincuenta"),
        (1540, "mil quinientos cuarenta"),
        (2845, "dos mil ochocientos cuarenta y cinco"),
        (21000, "veintiún mil"),
        (31500, "treinta y un mil quinientos"),
    ],
)
def test_number_in_words(n: int, words: str) -> None:
    assert number_in_words(n) == words


def test_the_normalizador_reads_every_number_back() -> None:
    # Alone, "uno" is an article for the normalizador ("uno de los chicos"): it stays a word.
    assert normalize(number_in_words(1)).text == "uno"
    for n in [0, *range(2, 100_000)]:
        assert normalize(number_in_words(n)).text == str(n)


def test_numbers_in_words_leaves_decimals_and_codes() -> None:
    text = "Corrientes 1540, km 4.5, S/N, a las 16:35, 3 autos"
    assert numbers_in_words(text) == (
        "Corrientes mil quinientos cuarenta, km 4.5, S/N, a las 16:35, tres autos"
    )


def test_same_seed_same_variant_and_noise_only_on_the_llamante() -> None:
    for kind in NoiseKind:
        first = make_variant("X-001", TURNS, kind)
        assert first == make_variant("X-001", TURNS, kind)
        assert first.turns[0] == TURNS[0]
        assert first.applied == (first.turns[1].text != PIZZERIA)


def test_another_seed_another_variant() -> None:
    a = make_variant("X-001", TURNS, NoiseKind.MULETILLAS, seed=1)
    b = make_variant("X-001", TURNS, NoiseKind.MULETILLAS, seed=2)
    assert a.turns != b.turns


def test_fillers_keep_every_word_in_order() -> None:
    noisy = add_fillers(PIZZERIA, Random(1))
    assert noisy != PIZZERIA
    words = iter(noisy.split(" "))
    assert all(word in words for word in PIZZERIA.split(" "))


def test_asr_typos_change_words_not_their_count() -> None:
    noisy = asr_typos(PIZZERIA, Random(1))
    assert noisy != PIZZERIA
    assert len(noisy.split()) == len(PIZZERIA.split())


def test_without_av() -> None:
    assert without_av("En Av. Corrientes y avenida Callao") == "En Corrientes y Callao"


def test_self_correction_says_another_altura_then_the_right_one() -> None:
    noisy = self_correction(PIZZERIA, Random(1))
    assert ", no, perdón, Av. Corrientes 1540 casi Montevideo" in noisy
    assert _location(noisy) == ("Av. Corrientes", 1540)


def test_without_location_leaves_nothing_to_locate() -> None:
    noisy = without_location(PIZZERIA)
    assert "Corrientes" not in noisy
    assert "se prendió fuego la campana" in noisy
    assert _location(noisy) == (None, None)


def test_no_variante_sin_direccion_has_a_ubicacion_for_the_rules() -> None:
    for variant in make_variants(parse_dataset(DATASET), NoiseKind.SIN_DIRECCION):
        turns = [
            Turn(index=i, at_ms=0, speaker=t.speaker, text=t.text)
            for i, t in enumerate(variant.turns)
        ]
        assert read_location(turns) is None, variant.case_id


def test_the_versioned_variantes_are_the_generator_output() -> None:
    cases = parse_dataset(DATASET)
    for kind in NoiseKind:
        expected = dump_variants(make_variants(cases, kind))
        assert variants_path(kind).read_text(encoding="utf-8") == expected, (
            f"{kind}: regenerá con `uv run python -m app.eval.noise`"
        )
