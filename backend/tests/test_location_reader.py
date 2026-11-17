import pytest

from app.catalog.loader import parse_dataset
from app.catalog.streets import match_street
from app.config import REPO_ROOT
from app.readers.models import LocationReading, NumberKind
from app.readers.rules.location import read_location
from app.transcript.models import Speaker, Turn
from app.transcript.parser import parse_transcript

DATASET = REPO_ROOT / "data" / "dataset_challenge_soflex.csv"
CASES = {c.id[-3:]: c for c in parse_dataset(DATASET)}


def _turns(raw: str) -> list[Turn]:
    return [
        Turn(index=i, at_ms=0, speaker=p.speaker, text=p.text)
        for i, p in enumerate(parse_transcript(raw))
    ]


def _read(raw: str) -> LocationReading:
    reading = read_location(_turns(raw))
    assert reading is not None
    return reading


def _read_case(case: str) -> LocationReading:
    return _read(CASES[case].transcript)


def test_case_001_street_number_and_casi() -> None:
    reading = _read_case("001")
    assert reading.street == "Av. Corrientes"
    assert reading.number is not None
    assert (reading.number.value, reading.number.kind) == (1540, NumberKind.EXACTA)
    assert reading.cross_streets == ["Montevideo"]
    assert reading.said == "Av. Corrientes 1540 casi Montevideo"


@pytest.mark.parametrize(
    ("case", "street", "value", "kind", "cross"),
    [
        ("002", "Scalabrini Ortiz", 800, NumberKind.AL, ["Vera", "Velasco"]),
        ("009", "Av. Directorio", 2140, NumberKind.EXACTA, []),
        ("012", "Thames", 1900, NumberKind.EXACTA, ["Nicaragua", "Costa Rica"]),
        ("028", "Av. Montes de Oca", 1100, NumberKind.AL, ["Rocha"]),
        ("005", "Av. San Juan", None, NumberKind.ESQUINA, ["Entre Ríos"]),
        ("013", "Av. Juan B. Justo", None, NumberKind.ESQUINA, ["Muñecas"]),
        ("022", "Av. 27 de Febrero", None, NumberKind.ESQUINA, ["Puente Alsina"]),
        ("024", "Av. Juan de Garay", None, NumberKind.ESQUINA, ["Av. Boedo"]),
    ],
)
def test_layers_on_dataset(
    case: str, street: str, value: int | None, kind: NumberKind, cross: list[str]
) -> None:
    reading = _read_case(case)
    assert reading.street == street
    assert reading.number is not None
    assert (reading.number.value, reading.number.kind) == (value, kind)
    assert reading.cross_streets == cross


def test_street_with_altura_reference() -> None:
    reading = _read_case("029")
    assert (reading.street, reading.landmark, reading.number) == (
        "Av. Lugones",
        "Parque Norte",
        None,
    )


def test_date_named_highway_is_not_a_number() -> None:
    reading = _read_case("006")
    assert reading.street == "Autopista 25 de Mayo"
    assert reading.number is None
    assert reading.landmark == "bajada de Boedo"


def test_landmark_naming_a_street() -> None:
    reading = _read_case("007")
    assert (reading.street, reading.landmark) == ("Av. Elcano", "puente de Av. Elcano")


def test_landmark_alone_has_no_street() -> None:
    reading = _read_case("008")
    assert reading.street is None
    assert reading.landmark == "estación Carlos Pellegrini de la Línea B"


def test_intersection_keeps_nearby_landmark_as_extra_evidence() -> None:
    reading = _read_case("015")
    assert (reading.street, reading.cross_streets) == ("Serrano", ["Honduras"])
    assert reading.landmark == "Plaza Serrano"
    assert [e.quote for e in reading.evidence] == ["Serrano y Honduras", "Plaza Serrano"]


def test_every_dataset_call_has_a_location_with_valid_offsets() -> None:
    for case_id, case in CASES.items():
        turns = _turns(case.transcript)
        reading = read_location(turns)
        assert reading is not None, case_id
        for ev in reading.evidence:
            turn = turns[ev.turn_index]
            assert turn.speaker is Speaker.LLAMANTE
            assert turn.text[ev.start : ev.end] == ev.quote, case_id


def test_ignores_ages_and_counts() -> None:
    assert read_location(_turns("Llamante: Mi Mamá de 82 años se cayó. Hay 15 personas.")) is None


def test_operador_turns_are_not_read() -> None:
    raw = "Operador: ¿Es en Corrientes 1540? Llamante: No sé, vengan rápido."
    assert read_location(_turns(raw)) is None


def test_latest_llamante_turn_wins() -> None:
    raw = (
        "Operador: ¿Dónde? Llamante: En Corrientes 1540. "
        "Operador: ¿Seguro? Llamante: Perdón, es Av. Callao 300."
    )
    reading = _read(raw)
    assert reading.street == "Av. Callao"
    assert reading.evidence[0].turn_index == 3


def test_offsets_point_into_the_original_text() -> None:
    reading = _read("Llamante: Hola, estoy en Thames 1900, entre Nicaragua y Costa Rica.")
    (ev,) = reading.evidence
    assert ev.quote == "Thames 1900, entre Nicaragua y Costa Rica"
    assert "Hola, estoy en Thames 1900, entre Nicaragua y Costa Rica."[ev.start : ev.end] == (
        ev.quote
    )


def test_sin_numero_and_km() -> None:
    sn = _read("Llamante: Es en Pasaje Lanín s/n.")
    assert sn.number is not None and sn.number.kind is NumberKind.SN
    km = _read("Llamante: En la Panamericana km 12.")
    assert km.number is not None
    assert (km.street, km.number.value, km.number.kind) == ("Panamericana", 12, NumberKind.KM)


def test_names_joined_by_y_are_not_a_corner_unless_they_are_streets() -> None:
    assert read_location(_turns("Llamante: Sí, Juan y María están adentro todavía.")) is None


def test_a_later_turno_only_replaces_the_ubicación_with_real_streets() -> None:
    raw = (
        "Operador: ¿Dónde? Llamante: En Thames 1900. "
        "Operador: ¿Quiénes están? Llamante: Sí, Juan y María están adentro todavía."
    )
    reading = _read(raw)
    assert reading.street == "Thames"


@pytest.mark.parametrize(
    ("raw", "street"),
    [
        ("Llamante: Estoy en Corrientes, se prendió fuego un auto.", "Corrientes"),
        ("Llamante: Choque sobre la Av. Rivadavia, vengan.", "Av. Rivadavia"),
        ("Llamante: Es por la calle Billinghurst.", "Billinghurst"),
    ],
)
def test_an_official_street_alone_is_read_without_altura(raw: str, street: str) -> None:
    reading = _read(raw)
    assert reading.street == street
    assert reading.number is None
    assert reading.said == street


@pytest.mark.parametrize(
    "raw",
    ["Llamante: Estoy en Pepito Inventado, vengan.", "Llamante: Estoy en Biyinghurst, vengan."],
)
def test_a_street_alone_must_be_in_the_list_by_name(raw: str) -> None:
    assert read_location(_turns(raw)) is None


def _llamante(*texts: str) -> list[Turn]:
    return [Turn(index=i, at_ms=0, speaker=Speaker.LLAMANTE, text=t) for i, t in enumerate(texts)]


def test_later_altura_alone_changes_the_altura_of_the_street_said() -> None:
    reading = read_location(
        _llamante("Es en Av. Corrientes 1540 casi Montevideo", "No, perdón, es en el 1450")
    )
    assert reading is not None
    assert reading.street == "Av. Corrientes"
    assert reading.number is not None
    assert (reading.number.value, reading.number.kind) == (1450, NumberKind.EXACTA)
    assert reading.cross_streets == ["Montevideo"]
    assert [e.quote for e in reading.evidence] == [
        "Av. Corrientes 1540 casi Montevideo",
        "en el 1450",
    ]


def test_later_altura_alone_in_words_is_read_on_the_normalized_text() -> None:
    turns = _llamante("Corrientes 1540", "no, es en el mil cuatrocientos cincuenta")
    reading = read_location(turns)
    assert reading is not None
    assert reading.number is not None
    assert reading.number.value == 1450
    assert reading.evidence[-1].quote == "en el mil cuatrocientos cincuenta"


@pytest.mark.parametrize("later", ["Tiene 80 años", "Tomé el 60", "Somos 1500 personas"])
def test_numbers_that_are_not_an_altura_change_nothing(later: str) -> None:
    reading = read_location(_llamante("Corrientes 1540", later))
    assert reading is not None
    assert reading.number is not None
    assert reading.number.value == 1540


def test_altura_alone_without_a_street_before_is_not_a_location() -> None:
    assert read_location(_llamante("Hay humo", "es en el 1450")) is None


# --- Relatos without capitals (ASR) --------------------------------------------------------------


def _lowercase(raw: str) -> list[Turn]:
    return [t.model_copy(update={"text": t.text.lower()}) for t in _turns(raw)]


def _official(reading: LocationReading | None) -> tuple[str | None, int | None]:
    if reading is None or reading.street is None:
        return None, None
    altura = reading.number.value if reading.number else None
    found = match_street(reading.street, altura)
    return (found.official if found else reading.street), altura


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_relato_without_capitals_reads_the_same_street(case: str) -> None:
    """Variante minusculas: an ASR seldom writes capitals, and the street is still there."""
    cased = read_location(_turns(CASES[case].transcript))
    lowercase = read_location(_lowercase(CASES[case].transcript))
    assert _official(lowercase) == _official(cased)


def test_a_lowercase_street_keeps_its_evidence_on_what_was_said() -> None:
    text = "hola, en un bodegón de av. san juan 2800 en san cristóbal. un hombre convulsiona"
    reading = read_location(_llamante(text))
    assert reading is not None
    assert reading.street == "Av. San Juan"
    assert reading.said == "av. san juan 2800"
    (ev,) = reading.evidence
    assert text[ev.start : ev.end] == ev.quote


@pytest.mark.parametrize(
    ("said", "street", "altura"),
    [
        ("es por la calle defensa, vengan", "Defensa", None),
        ("sobre la av. rivadavia, vengan", "Av. Rivadavia", None),
        ("es en la rivadavia al 6300", "Rivadavia", 6300),
        ("estoy en lavalle y florida", "Lavalle", None),
        ("choque en la avenida general paz y constituyentes", "Avenida General Paz", None),
    ],
)
def test_lowercase_streets_by_the_official_list(said: str, street: str, altura: int | None) -> None:
    reading = read_location(_llamante(said))
    assert reading is not None
    assert reading.street == street
    assert (reading.number.value if reading.number else None) == altura


@pytest.mark.parametrize(
    "said",
    [
        "estoy en la esquina, vengan rápido",
        "dejé las llaves sobre la mesa y salí corriendo",
        "sí, juan y maría están adentro todavía",
        "se prendió fuego la campana de la cocina",
        "se escapó por la ventana del fondo",
        "quedó cruzado en el carril central a la altura de la bajada",
        "tiene 80 años y vive en el tercer piso",
        "en serio, vengan ya, está en el piso",
        "vive en el barrio norte, en la casa de mi abuela",
        "llamo por mi vecina rosa, se cayó en el baño",
    ],
)
def test_lowercase_words_that_are_also_street_names_are_not_a_ubicacion(said: str) -> None:
    assert read_location(_llamante(said)) is None
