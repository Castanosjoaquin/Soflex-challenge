"""Pure transitions of a llamada's state. Knows nothing about HTTP or the IA provider."""

from collections.abc import Sequence

from app.catalog.incidents import SUBTYPES, Subtype
from app.catalog.models import Category, Priority
from app.catalog.signals import INCOHERENT_PAIRS, VICTIM_SIGNALS, SignalAnswer, SignalId
from app.engine.models import (
    CallState,
    Confidence,
    Incident,
    Line,
    Location,
    Mode,
    NextQuestion,
    PriorityAssessment,
    PriorityOverride,
    SignalValue,
    Source,
    Stage,
    StageId,
    StageStatus,
)
from app.engine.priority import assess
from app.engine.verification import verify
from app.readers.models import (
    Evidence,
    IncidentReading,
    LocationReading,
    ReaderOutput,
    SignalReading,
    StreetNumber,
)
from app.transcript.models import Turn


class NoLocationError(ValueError):
    """The operador acted on a ubicación that the relato has not produced yet."""


class NoIncidentError(ValueError):
    """The operador confirmed a tipo that the relato has not produced yet."""


def new_call(call_id: str, line: Line, mode: Mode, sample_id: str | None = None) -> CallState:
    state = CallState(call_id=call_id, line=line, mode=mode, sample_id=sample_id, stages=[])
    return _derive(state)


def add_turn(state: CallState, turn: Turn) -> CallState:
    return state.model_copy(update={"turns": [*state.turns, turn]})


def apply_reading(state: CallState, output: ReaderOutput) -> CallState:
    """Fold a lectura of the whole relato into the state.

    Every dato whose evidence is not in the relato is discarded. A confirmed dato is never
    overwritten; an unconfirmed one takes the latest value (autocorrección).
    """
    location = state.location
    if not _is_confirmed(location) and output.location is not None:
        location = _location_from(state.turns, output.location) or location
    incident = state.incident
    if not _is_confirmed(incident) and output.incident is not None:
        incident = _incident_from(state.turns, output.incident) or incident
    signals = _merge_signals(state.turns, state.signals, output.signals)
    return _derive(
        state.model_copy(update={"location": location, "incident": incident, "signals": signals})
    )


def confirm_location(state: CallState) -> CallState:
    if state.location is None:
        raise NoLocationError
    location = state.location.model_copy(update={"confidence": Confidence.CONFIRMADO})
    return _derive(state.model_copy(update={"location": location}))


def correct_location(
    state: CallState,
    *,
    street: str,
    number: StreetNumber | None,
    cross_streets: list[str],
) -> CallState:
    """The operador sets the dirección; what the llamante said and its evidence stay."""
    said = state.location.said if state.location else ""
    evidence = state.location.evidence if state.location else []
    corrected = Location(
        said=said,
        evidence=evidence,
        street=street,
        number=number,
        cross_streets=cross_streets,
        confidence=Confidence.CONFIRMADO,
        source=Source.OPERADOR,
    )
    return _derive(state.model_copy(update={"location": corrected}))


def confirm_type(
    state: CallState, category: Category | None = None, subtype: Subtype | None = None
) -> CallState:
    """Confirm the suggested tipo, or set another one (and optionally its subtipo)."""
    current = state.incident
    if category is None:
        if current is None:
            raise NoIncidentError
        confirmed = current.model_copy(update={"confidence": Confidence.CONFIRMADO})
    else:
        if subtype is not None and SUBTYPES[subtype].category is not category:
            raise ValueError(f"{subtype} no es un subtipo de {category}")
        kept = current if current is not None and current.category is category else None
        if subtype is None and kept is not None:
            subtype = kept.subtype
        confirmed = Incident(
            category=category,
            subtype=subtype,
            evidence=kept.evidence if kept else [],
            confidence=Confidence.CONFIRMADO,
            source=kept.source if kept and kept.subtype is subtype else Source.OPERADOR,
        )
    return _derive(state.model_copy(update={"incident": confirmed}))


def set_priority(state: CallState, level: Priority, reason: str) -> CallState:
    """The operador changes the prioridad. The motivo is mandatory and the porqué is kept."""
    if not reason.strip():
        raise ValueError("Cambiar la prioridad requiere un motivo")
    previous = state.priority
    priority = PriorityAssessment(
        level=level,
        rule=previous.rule if previous else "Fijada por el operador",
        reasons=previous.reasons if previous else [],
        overridden_by_operator=PriorityOverride(
            from_level=previous.level if previous else None, reason=reason.strip()
        ),
    )
    return _derive(state.model_copy(update={"priority": priority}))


# Location


def _location_from(turns: Sequence[Turn], reading: LocationReading) -> Location | None:
    if not reading.evidence or any(verify(ev, turns) is None for ev in reading.evidence):
        return None
    return Location(
        said=reading.said,
        evidence=reading.evidence,
        street=reading.street,
        number=reading.number,
        cross_streets=reading.cross_streets,
        landmark=reading.landmark,
        confidence=_location_confidence(reading),
        source=Source.REGLAS,
    )


def _location_confidence(reading: LocationReading) -> Confidence:
    """Probable when the dirección can be pinned down: a street plus an altura or a cross street."""
    has_altura = reading.number is not None and reading.number.value is not None
    if reading.street and (has_altura or reading.cross_streets):
        return Confidence.PROBABLE
    return Confidence.A_CONFIRMAR


# Incidente


def _incident_from(turns: Sequence[Turn], reading: IncidentReading) -> Incident | None:
    evidence = _verified(turns, reading.evidence)
    if not evidence:
        return None
    sure = reading.runner_up is None
    return Incident(
        category=reading.category,
        subtype=reading.subtype,
        evidence=evidence,
        confidence=Confidence.PROBABLE if sure else Confidence.A_CONFIRMAR,
        source=Source.REGLAS,
    )


# Señales


def _merge_signals(
    turns: Sequence[Turn], current: Sequence[SignalValue], readings: Sequence[SignalReading]
) -> list[SignalValue]:
    """Union of what was known and what this lectura found; confirmed señales are never touched."""
    merged = {s.signal_id: s for s in current}
    for reading in readings:
        previous = merged.get(reading.signal_id)
        if previous is not None and previous.confidence is Confidence.CONFIRMADO:
            continue
        evidence = verify(reading.evidence, turns)
        if evidence is None:
            continue
        merged[reading.signal_id] = SignalValue(
            signal_id=reading.signal_id,
            value=reading.value,
            evidence=evidence,
            source=Source.REGLAS,
            confidence=Confidence.PROBABLE,
        )
    return _with_coherence([merged[s] for s in SignalId if s in merged])


def _with_coherence(signals: list[SignalValue]) -> list[SignalValue]:
    """Señales in an incoherent pair are not trusted: both go to a_confirmar (SPEC §5.4.2)."""
    facts = {(s.signal_id, s.value) for s in signals}
    doubtful = {
        signal_id
        for left, right in INCOHERENT_PAIRS
        if left in facts and right in facts
        for signal_id in (left[0], right[0])
    }
    return [
        s.model_copy(update={"confidence": Confidence.A_CONFIRMAR})
        if s.signal_id in doubtful and s.confidence is not Confidence.CONFIRMADO
        else s
        for s in signals
    ]


def _verified(turns: Sequence[Turn], evidence: Sequence[Evidence]) -> list[Evidence]:
    return [found for ev in evidence if (found := verify(ev, turns)) is not None]


# What follows from the data


def _derive(state: CallState) -> CallState:
    """Recompute prioridad, próxima pregunta and etapas from the data the state holds."""
    priority = state.priority
    if priority is None or priority.overridden_by_operator is None:
        priority = assess(state.incident, state.signals)
    return state.model_copy(
        update={
            "priority": priority,
            "next_question": _universal_question(state),
            "stages": _stages(state),
        }
    )


def _known(state: CallState, signal_id: SignalId) -> SignalAnswer | None:
    """The value of a señal when it is actually known: sí or no, not "no se sabe"."""
    for s in state.signals:
        if s.signal_id is signal_id and s.value is not SignalAnswer.NO_SABE:
            return s.value
    return None


def _has_victims(state: CallState) -> bool:
    if state.incident is not None and state.incident.category is Category.EMERGENCIA_MEDICA:
        return True
    return any(s.signal_id in VICTIM_SIGNALS and s.value is SignalAnswer.SI for s in state.signals)


def _missing_vital_signs(state: CallState) -> list[SignalId]:
    """Riesgo vital still to evaluate. Someone who does not breathe needs no other question."""
    if not _has_victims(state) or _known(state, SignalId.RESPIRA) is SignalAnswer.NO:
        return []
    return [s for s in (SignalId.CONSCIENTE, SignalId.RESPIRA) if _known(state, s) is None]


_UNIVERSAL_TEXT = {
    SignalId.CONSCIENTE: "¿Está consciente?",
    SignalId.RESPIRA: "¿Respira?",
}


def _universal_question(state: CallState) -> NextQuestion | None:
    missing = _missing_vital_signs(state)
    if not missing:
        return None
    return NextQuestion(
        id="universal",
        text=" ".join(_UNIVERSAL_TEXT[s] for s in missing),
        signal_ids=missing,
    )


def _is_confirmed(dato: Location | Incident | None) -> bool:
    return dato is not None and dato.confidence is Confidence.CONFIRMADO


def _stages(state: CallState) -> list[Stage]:
    """① and ② have a real status; the rest arrive with their tickets."""
    ubicar = StageStatus.HECHA if _is_confirmed(state.location) else StageStatus.ACTUAL
    if _is_confirmed(state.incident) and not _missing_vital_signs(state):
        que_pasa = StageStatus.HECHA
    elif state.incident is not None or state.signals:
        que_pasa = StageStatus.ACTUAL
    else:
        que_pasa = StageStatus.PENDIENTE
    status = {StageId.UBICAR: ubicar, StageId.QUE_PASA: que_pasa}
    return [Stage(id=s, status=status.get(s, StageStatus.PENDIENTE)) for s in StageId]
