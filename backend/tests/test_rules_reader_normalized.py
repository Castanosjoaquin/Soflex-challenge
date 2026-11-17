"""The Lector por reglas reads the normalized relato and highlights on the original one."""

from app.catalog.models import Category
from app.catalog.signals import SignalAnswer, SignalId
from app.engine.verification import verify
from app.readers.models import Evidence, NumberKind
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn


def _turns(*texts: str) -> list[Turn]:
    return [Turn(index=i, at_ms=0, speaker=Speaker.LLAMANTE, text=t) for i, t in enumerate(texts)]


def _on_original(evidence: Evidence, turns: list[Turn]) -> None:
    """The evidence is a verbatim span of the original turno, and the verificación accepts it."""
    assert turns[evidence.turn_index].text[evidence.start : evidence.end] == evidence.quote
    assert verify(evidence, turns) == evidence


def test_number_in_words_reads_as_altura_and_highlights_the_words() -> None:
    turns = _turns("Es en Corrientes mil quinientos cuarenta")
    location = RulesReader().read(turns).location
    assert location is not None
    assert location.street == "Corrientes"
    assert location.number is not None
    assert (location.number.value, location.number.kind) == (1540, NumberKind.EXACTA)
    assert location.said == "Corrientes mil quinientos cuarenta"
    [evidence] = location.evidence
    assert (evidence.start, evidence.end) == (6, 40)
    _on_original(evidence, turns)


def test_autocorrection_within_the_turno_keeps_the_last_street() -> None:
    turns = _turns("en Corrientes… no, perdón, en Montevideo al 800")
    location = RulesReader().read(turns).location
    assert location is not None
    assert location.street == "Montevideo"
    assert location.number is not None
    assert (location.number.value, location.number.kind) == (800, NumberKind.AL)
    [evidence] = location.evidence
    assert evidence.quote == "Montevideo al 800"
    assert evidence.start == turns[0].text.index("Montevideo")
    _on_original(evidence, turns)


def test_fillers_do_not_hide_a_signal() -> None:
    turns = _turns("eh, este, hay humo")
    signals = {s.signal_id: s for s in RulesReader().read(turns).signals}
    humo = signals[SignalId.HUMO]
    assert humo.value is SignalAnswer.SI
    assert (humo.evidence.start, humo.evidence.end, humo.evidence.quote) == (14, 18, "humo")
    _on_original(humo.evidence, turns)


def test_corrected_signal_is_not_read() -> None:
    turns = _turns("Hay fuego… no, perdón, hay humo nomás")
    signals = {s.signal_id for s in RulesReader().read(turns).signals}
    assert SignalId.HUMO in signals
    assert SignalId.FUEGO_ACTIVO not in signals


def test_incident_evidence_lands_on_the_original_text() -> None:
    turns = _turns("Eh, o sea, mmm… hay un incendio en el depto")
    incident = RulesReader().read(turns).incident
    assert incident is not None
    assert incident.category is Category.INCENDIO_RESCATE
    assert incident.evidence
    for evidence in incident.evidence:
        _on_original(evidence, turns)


def test_evidence_after_a_number_in_words_keeps_its_offsets() -> None:
    turns = _turns("Somos dos mil quinientos vecinos, viste, y hay humo")
    signals = {s.signal_id: s for s in RulesReader().read(turns).signals}
    humo = signals[SignalId.HUMO].evidence
    assert humo.start == turns[0].text.index("humo")
    _on_original(humo, turns)
