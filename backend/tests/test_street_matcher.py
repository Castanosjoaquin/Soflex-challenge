import pytest

from app.catalog.loader import parse_dataset
from app.catalog.streets import MatchKind, match_street
from tests.conftest import DATASET


def test_exact_name() -> None:
    match = match_street("Billinghurst")
    assert match is not None
    assert match.official == "BILLINGHURST"
    assert match.kind is MatchKind.EXACTO


@pytest.mark.parametrize(
    "said", ["Corrientes", "Av. Corrientes", "avenida Corrientes", "Avda Corrientes"]
)
def test_avenue_with_or_without_its_prefix(said: str) -> None:
    match = match_street(said)
    assert match is not None
    assert match.official == "AV. CORRIENTES"
    assert match.kind is MatchKind.EXACTO


@pytest.mark.parametrize(
    ("said", "official"),
    [
        ("General Paz", "AV. GRAL. PAZ"),
        ("Av. Gral Paz", "AV. GRAL. PAZ"),
        ("Presidente Figueroa Alcorta", "AV. PRES. FIGUEROA ALCORTA"),
        ("Doctor Adolfo Dickman", "DR. ADOLFO DICKMAN"),
    ],
)
def test_titles_spelled_out_or_abbreviated(said: str, official: str) -> None:
    match = match_street(said)
    assert match is not None
    assert match.official == official


@pytest.mark.parametrize(
    ("said", "official"),
    [("Figueroa Alcorta", "AV. PRES. FIGUEROA ALCORTA"), ("Borges", "JORGE LUIS BORGES")],
)
def test_street_named_after_someone_by_surname(said: str, official: str) -> None:
    match = match_street(said)
    assert match is not None
    assert match.official == official
    assert match.kind is MatchKind.ALIAS


@pytest.mark.parametrize(
    ("said", "altura", "official"),
    [
        # Serrano was renamed Jorge Luis Borges only from 1601 on; below that it is still Serrano.
        ("Serrano", 1800, "JORGE LUIS BORGES"),
        ("Serrano", 1200, "SERRANO"),
        # Scalabrini Ortiz is an avenida up to 2500 and a calle after.
        ("Scalabrini Ortiz", 800, "AV. RAUL SCALABRINI ORTIZ"),
        ("Scalabrini Ortiz", 3000, "RAUL SCALABRINI ORTIZ"),
    ],
)
def test_the_altura_picks_the_stretch(said: str, altura: int, official: str) -> None:
    match = match_street(said, altura)
    assert match is not None
    assert match.official == official
    assert len(match.candidates) == 1


def test_first_words_of_a_surname() -> None:
    match = match_street("Scalabrini")
    assert match is not None
    assert match.official == "AV. RAUL SCALABRINI ORTIZ"
    assert match.kind is MatchKind.ALIAS


def test_a_name_that_is_avenida_and_calle_without_altura_is_ambiguous() -> None:
    match = match_street("Scalabrini Ortiz")
    assert match is not None
    assert [s.name for s in match.candidates] == [
        "AV. RAUL SCALABRINI ORTIZ",
        "RAUL SCALABRINI ORTIZ",
    ]
    assert match.avenida_o_calle


def test_saying_avenida_settles_it() -> None:
    match = match_street("Av. Scalabrini Ortiz")
    assert match is not None
    assert [s.name for s in match.candidates] == ["AV. RAUL SCALABRINI ORTIZ"]
    assert not match.avenida_o_calle


@pytest.mark.parametrize(
    ("said", "official"),
    [
        ("Biyinghurst", "BILLINGHURST"),  # ll/y
        ("Tames", "THAMES"),  # h muda
        ("Corientes", "AV. CORRIENTES"),  # a letter lost in the transcription
        ("Escalabrini Ortiz", "AV. RAUL SCALABRINI ORTIZ"),
        ("Nikaragua", "NICARAGUA"),
    ],
)
def test_transcription_errors_by_sound_and_likeness(said: str, official: str) -> None:
    match = match_street(said)
    assert match is not None
    assert match.official == official
    assert match.kind is MatchKind.FUZZY


@pytest.mark.parametrize("said", ["Juan", "María", "Pepito Inventado", "Mesa"])
def test_what_is_not_a_street_does_not_match(said: str) -> None:
    assert match_street(said) is None


def test_a_street_in_both_lists_with_that_altura_stays_ambiguous() -> None:
    # Calle Sarmiento (Almagro) runs 1-4700 and Av. Sarmiento (Palermo) 2601-4800.
    match = match_street("Sarmiento", 3900)
    assert match is not None
    assert match.avenida_o_calle


def test_every_street_of_the_dataset_is_in_the_official_list() -> None:
    """The streets annotated in the 30 llamadas; 008 is a subte platform, not a street."""
    misses = []
    for case in parse_dataset(DATASET):
        altura = int(case.street_number) if case.street_number.isdigit() else None
        if case.id.endswith("008"):
            continue
        if match_street(case.street.split("(")[0], altura) is None:
            misses.append(f"{case.id}: {case.street}")
    assert misses == []
