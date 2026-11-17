import random

import pytest

from app.transcript.normalize import MAX_NUMBER, Normalized, normalize

# --- Muletillas ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "normalized"),
    [
        ("eh, este, hay humo", "hay humo"),
        ("Ehh... hay humo", "hay humo"),
        ("mmm, en Corrientes", "en Corrientes"),
        ("hay humo, o sea, mucho humo", "hay humo, mucho humo"),
        ("está en el piso, digamos, tercero", "está en el piso, tercero"),
        ("hay humo, viste.", "hay humo."),
        ("este… se cayó", "se cayó"),
        ("en eh Corrientes", "en Corrientes"),
    ],
)
def test_fillers_are_dropped(said: str, normalized: str) -> None:
    assert normalize(said).text == normalized


@pytest.mark.parametrize(
    "said",
    [
        "este edificio tiene humo",
        "en este momento no respira",
        "lo viste al chofer",
        "hay humo en el depto",
    ],
)
def test_words_that_mean_something_stay(said: str) -> None:
    assert normalize(said).text == said


# --- Autocorrección ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "normalized"),
    [
        ("en Corrientes… no, perdón, en Montevideo al 800", "en Montevideo al 800"),
        ("Es en Corrientes... perdón, no, en Montevideo", "Es en Montevideo"),
        ("Hay fuego, no perdón, hay humo", "hay humo"),
        ("Corrientes 1500, digo, Montevideo 800", "Montevideo 800"),
        ("está en Lavalle, mejor dicho, en Tucumán", "está en Tucumán"),
        ("en Lavalle, me equivoqué, en Tucumán", "en Tucumán"),
        ("Es en Lavalle, en realidad, en Tucumán", "Es en Tucumán"),
    ],
)
def test_autocorrection_keeps_the_last_value(said: str, normalized: str) -> None:
    assert normalize(said).text == normalized


@pytest.mark.parametrize(
    ("said", "normalized"),
    [
        # Case 016, variante autocorreccion: the dot of "Av." does not end a sentence.
        (
            "Buen día, en Plaza Almagro, Av. Cabildo 2100, no, perdón, Sarmiento y Bulnes, hay",
            "Buen día, en Plaza Almagro, Sarmiento y Bulnes, hay",
        ),
        ("Hola, Gral. Paz 1200, no, perdón, Lavalle 300", "Hola, Lavalle 300"),
        ("Hola, Juan B. Justo 900, no, perdón, Muñecas 400", "Hola, Muñecas 400"),
    ],
)
def test_an_abbreviation_dot_is_not_where_the_corrected_value_starts(
    said: str, normalized: str
) -> None:
    assert normalize(said).text == normalized


@pytest.mark.parametrize(
    "said",
    [
        "No, perdón, no hay nadie adentro",  # nothing before the marker to correct
        "le digo que salga",  # "digo" without a pause is plain speech
        "en realidad no sé",
        "Está en la cocina, perdón, no sé",  # "perdón, no sé" is an apology, not a correction
    ],
)
def test_plain_speech_is_not_a_correction(said: str) -> None:
    assert normalize(said).text == said


# --- Números -------------------------------------------------------------------------------------

_UNITS = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
_TEENS_AND_TWENTIES = [
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
]
_TENS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_HUNDREDS = [
    "",
    "ciento",
    "doscientos",
    "trescientos",
    "cuatrocientos",
    "quinientos",
    "seiscientos",
    "setecientos",
    "ochocientos",
    "novecientos",
]


def _below_hundred(n: int, before_mil: bool) -> str:
    if n < 10:
        word = _UNITS[n]
    elif n < 30:
        word = _TEENS_AND_TWENTIES[n - 10]
    else:
        word = _TENS[n // 10] + (f" y {_UNITS[n % 10]}" if n % 10 else "")
    if before_mil and word.endswith("uno"):  # "veintiún mil", "treinta y un mil"
        word = word[:-3] + ("ún" if word.endswith("iuno") else "un")
    return word


def _below_thousand(n: int, before_mil: bool = False) -> str:
    if n == 100:
        return "cien"
    parts = [_HUNDREDS[n // 100], _below_hundred(n % 100, before_mil)]
    return " ".join(p for p in parts if p)


def _spell(n: int) -> str:
    """Spanish words for 0 to 99999, written independently of the normalizador."""
    if n == 0:
        return "cero"
    thousands, rest = divmod(n, 1000)
    parts = []
    if thousands:
        parts += ["mil"] if thousands == 1 else [_below_thousand(thousands, before_mil=True), "mil"]
    if rest:
        parts.append(_below_thousand(rest))
    return " ".join(parts)


def test_every_number_from_0_to_99999_turns_into_digits() -> None:
    wrong = {}
    for n in range(MAX_NUMBER + 1):
        if n == 1:  # "uno" alone is a pronoun or an article: tested below
            continue
        said = f"al {_spell(n)} hay humo"
        if (got := normalize(said).text) != f"al {n} hay humo":
            wrong[said] = got
    assert not wrong, list(wrong.items())[:10]


@pytest.mark.parametrize(
    ("said", "normalized"),
    [
        ("Corrientes mil quinientos cuarenta", "Corrientes 1540"),
        ("Rivadavia dos mil", "Rivadavia 2000"),
        ("Montevideo al ochocientos", "Montevideo al 800"),
        ("hay cuatro personas adentro", "hay 4 personas adentro"),
        ("Dos autos chocaron", "2 autos chocaron"),
        ("Lugones km siete", "Lugones km 7"),
        ("mil doscientas cincuenta", "1250"),
        ("veintiún mil", "21000"),
        ("dos y medio", "2 y medio"),
        ("humo y dos heridos", "humo y 2 heridos"),
    ],
)
def test_numbers_in_context(said: str, normalized: str) -> None:
    assert normalize(said).text == normalized


@pytest.mark.parametrize(
    "said",
    [
        "hay una persona atrapada",
        "uno de los chicos está herido",
        "un auto",
        "Tres Arroyos al 400",  # a street named with a number
        "Av. Nueve de Julio",
        "barrio de Once",
        "cien mil personas",  # over 99999
        "ciento",
    ],
)
def test_words_that_are_not_numbers_stay(said: str) -> None:
    assert normalize(said).text == said


# --- Abreviaturas --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "normalized"),
    [
        ("avenida Corrientes 1540", "Av. Corrientes 1540"),
        ("Avenida Rivadavia", "Av. Rivadavia"),
        ("Avda. Rivadavia", "Av. Rivadavia"),
        ("av Rivadavia", "Av. Rivadavia"),
        ("Av. Rivadavia", "Av. Rivadavia"),
        ("Av Gral Paz", "Av. Gral. Paz"),
        ("Pte Perón", "Pte. Perón"),
        ("dr Finochietto", "Dr. Finochietto"),
        ("Juan B Justo", "Juan B. Justo"),
        ("Juan Bautista Justo", "Juan B. Justo"),
        ("Av. Juan B. Justo y Muñecas", "Av. Juan B. Justo y Muñecas"),
        ("toda la avenida de vereda a vereda", "toda la avenida de vereda a vereda"),
    ],
)
def test_abbreviations_are_unified(said: str, normalized: str) -> None:
    assert normalize(said).text == normalized


def test_all_steps_together() -> None:
    said = "Eh, es en avenida Corrientes… no, perdón, en Montevideo al ochocientos, viste."
    assert normalize(said).text == "es en Montevideo al 800."


# --- Mapa de offsets -----------------------------------------------------------------------------


def _back(said: str, phrase: str) -> str:
    """Find `phrase` in the normalized text and return what it covers in the original."""
    normalized = normalize(said)
    start = normalized.text.index(phrase)
    first, last = normalized.to_original(start, start + len(phrase))
    return said[first:last]


@pytest.mark.parametrize(
    ("said", "phrase", "original"),
    [
        (
            "Es en Corrientes mil quinientos cuarenta",
            "Corrientes 1540",
            "Corrientes mil quinientos cuarenta",
        ),
        ("Es en Corrientes mil quinientos cuarenta", "1540", "mil quinientos cuarenta"),
        ("Es en Corrientes mil quinientos cuarenta", "154", "mil quinientos cuarenta"),
        ("en Corrientes… no, perdón, en Montevideo al 800", "Montevideo al 800", None),
        ("eh, este, hay humo", "humo", None),
        ("eh, este, hay humo", "hay humo", None),
        ("hay, eh, humo", "hay, humo", "hay, eh, humo"),
        ("avenida Corrientes 1540", "Av. Corrientes", "avenida Corrientes"),
        ("avenida Corrientes 1540", "Corrientes", None),
        ("Juan B Justo dos mil", "Juan B. Justo 2000", "Juan B Justo dos mil"),
    ],
)
def test_normalized_span_maps_back_to_the_original(
    said: str, phrase: str, original: str | None
) -> None:
    assert _back(said, phrase) == (original or phrase)


def test_identity_maps_every_span_to_itself() -> None:
    normalized = Normalized.identity("hay humo")
    assert normalized.to_original(0, 3) == (0, 3)
    assert normalized.to_original(4, 4) == (4, 4)
    assert normalized.to_original(8, 8) == (8, 8)


def test_span_outside_the_text_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalize("hay humo").to_original(0, 99)


_WORDS = ["hay", "humo", "en", "la", "cocina", "Corrientes", "1540", "quedó", "adentro", "sale"]
_NOISE = ["eh, ", "este, ", "mmm ", "o sea, ", "digamos, ", "eh… "]


@pytest.mark.parametrize("seed", range(200))
def test_property_clean_words_survive_noise_with_exact_offsets(seed: int) -> None:
    """Noise between clean words is dropped, and each word maps back onto itself."""
    rng = random.Random(seed)
    words = [rng.choice(_WORDS) for _ in range(rng.randint(1, 8))]
    pieces: list[str] = []
    positions: list[int] = []
    for word in words:
        if rng.random() < 0.5:
            pieces.append(rng.choice(_NOISE))
        positions.append(sum(map(len, pieces)))
        pieces.append(word + " ")
    said = "".join(pieces).rstrip()
    normalized = normalize(said)
    assert normalized.text == " ".join(words)
    cursor = 0
    for word, position in zip(words, positions, strict=True):
        start = normalized.text.index(word, cursor)
        cursor = start + len(word)
        assert normalized.to_original(start, cursor) == (position, position + len(word))
