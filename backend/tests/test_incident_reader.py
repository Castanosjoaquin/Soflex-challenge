from app.catalog.incidents import Subtype
from app.catalog.models import Category
from app.engine.models import Line
from app.readers.rules.incident import read_incident
from app.transcript.models import Speaker, Turn


def _turns(*texts: str) -> list[Turn]:
    return [Turn(index=i, at_ms=0, speaker=Speaker.LLAMANTE, text=t) for i, t in enumerate(texts)]


def test_pizzeria_fire_is_incendio_en_comercio_with_evidence() -> None:
    text = "En la pizzería se prendió fuego la campana de la cocina"
    reading = read_incident(_turns(text))
    assert reading is not None
    assert reading.category is Category.INCENDIO_RESCATE
    assert reading.subtype is Subtype.INCENDIO_COMERCIO
    assert any(e.quote == "pizzería" for e in reading.evidence)
    for ev in reading.evidence:
        assert text[ev.start : ev.end] == ev.quote


def test_no_keyword_means_no_tipo_even_with_a_line_prior() -> None:
    assert read_incident(_turns("Hola, buenas tardes"), Line.L107) is None


def test_line_prior_breaks_a_close_call() -> None:
    turns = _turns("hay humo y se cayó una pared")  # derrumbe (3) vs caída (3)
    by_103 = read_incident(turns, Line.L103)
    by_107 = read_incident(turns, Line.L107)
    assert by_103 is not None and by_103.category is Category.DEFENSA_CIVIL
    assert by_107 is not None and by_107.category is Category.EMERGENCIA_MEDICA


def test_a_close_race_names_the_runner_up() -> None:
    reading = read_incident(_turns("hay humo y una pelea"))
    assert reading is not None
    assert reading.runner_up is not None


def test_a_clear_lead_has_no_runner_up() -> None:
    reading = read_incident(_turns("se prendió fuego, hay llamas y humo en la casa"))
    assert reading is not None
    assert reading.runner_up is None
