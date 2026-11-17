"""Pure transitions of a llamada's state. Knows nothing about HTTP or the IA provider."""

from collections.abc import Sequence

from app.catalog.incidents import SUBTYPES, Subtype
from app.catalog.instructions import Instruction, instructions_for
from app.catalog.models import Category, Priority
from app.catalog.questions import checklist_for
from app.catalog.signals import INCOHERENT_PAIRS, VICTIM_SIGNALS, SignalAnswer, SignalId
from app.catalog.streets import MatchKind, StreetMatch, bare_name, match_street
from app.engine.models import (
    CallState,
    ChecklistItem,
    Confidence,
    Incident,
    InstructionItem,
    Line,
    Location,
    Mode,
    NextQuestion,
    PriorityAssessment,
    PriorityOverride,
    QuestionStatus,
    SignalValue,
    Source,
    Stage,
    StageId,
    StageStatus,
)
from app.engine.priority import assess, fired_rules
from app.engine.verification import verify
from app.readers.models import (
    Evidence,
    IncidentReading,
    LocationReading,
    ReaderOutput,
    SignalReading,
    StreetNumber,
)
from app.transcript.models import Speaker, Turn


class NoLocationError(ValueError):
    """The operador acted on a ubicación that the relato has not produced yet."""


class NoIncidentError(ValueError):
    """The operador confirmed a tipo that the relato has not produced yet."""


class UnknownQuestionError(ValueError):
    """The operador acted on a pregunta that is not asked in this llamada right now."""


class NoPremarkError(ValueError):
    """The operador confirmed a pre-marca that the relato has not produced."""


class UnknownInstructionError(ValueError):
    """The operador marked an instrucción that does not apply to this llamada right now."""


UNIVERSAL = "universal"


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
    return _derive(state.model_copy(update={"location": _with_official_names(corrected)}))


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


def confirm_premark(state: CallState, question_id: str) -> CallState:
    """The operador validates what the relato answered. The value and its evidence stay."""
    item = _checklist_item(state, question_id)
    signal = _signal(state, item.signal_id)
    if signal is None or signal.confidence is Confidence.CONFIRMADO:
        raise NoPremarkError(question_id)
    confirmed = signal.model_copy(update={"confidence": Confidence.CONFIRMADO})
    return _with_signal(state, confirmed, question_id)


def answer_question(state: CallState, question_id: str, value: SignalAnswer) -> CallState:
    """The operador answers a pregunta clave, or one of the universal ones (by its señal id).

    The answer is the señal, confirmed and from the operador: no later lectura overwrites it.
    """
    signal_id = _answerable_signal(state, question_id)
    answer = SignalValue(
        signal_id=signal_id, value=value, source=Source.OPERADOR, confidence=Confidence.CONFIRMADO
    )
    return _with_signal(state, answer, question_id)


def skip_question(state: CallState, question_id: str) -> CallState:
    """The operador moves on without an answer: a pregunta clave, or the universal ones."""
    if question_id != UNIVERSAL:
        _checklist_item(state, question_id)
    elif not _missing_vital_signs(state):
        raise UnknownQuestionError(question_id)
    if question_id in state.skipped_questions:
        return state
    skipped = [*state.skipped_questions, question_id]
    return _derive(state.model_copy(update={"skipped_questions": skipped}))


def mark_instruction_read(state: CallState, instruction_id: str) -> CallState:
    """The operador read an instrucción aloud. Marking it twice changes nothing."""
    if all(i.instruction_id != instruction_id for i in state.instructions):
        raise UnknownInstructionError(instruction_id)
    if instruction_id in state.read_instructions:
        return state
    read = [*state.read_instructions, instruction_id]
    return _derive(state.model_copy(update={"read_instructions": read}))


def _checklist_item(state: CallState, question_id: str) -> ChecklistItem:
    for item in state.checklist:
        if item.question_id == question_id:
            return item
    raise UnknownQuestionError(question_id)


def _answerable_signal(state: CallState, question_id: str) -> SignalId:
    if any(item.question_id == question_id for item in state.checklist):
        return _checklist_item(state, question_id).signal_id
    if _has_victims(state) and question_id in _UNIVERSAL_TEXT:
        return SignalId(question_id)
    raise UnknownQuestionError(question_id)


def _signal(state: CallState, signal_id: SignalId) -> SignalValue | None:
    return next((s for s in state.signals if s.signal_id is signal_id), None)


def _with_signal(state: CallState, signal: SignalValue, question_id: str) -> CallState:
    others = [s for s in state.signals if s.signal_id is not signal.signal_id]
    signals = sorted([*others, signal], key=lambda s: list(SignalId).index(s.signal_id))
    skipped = [q for q in state.skipped_questions if q != question_id]
    return _derive(state.model_copy(update={"signals": signals, "skipped_questions": skipped}))


# Location


def _location_from(turns: Sequence[Turn], reading: LocationReading) -> Location | None:
    if not reading.evidence or any(verify(ev, turns) is None for ev in reading.evidence):
        return None
    location = Location(
        said=reading.said,
        evidence=reading.evidence,
        street=reading.street,
        number=reading.number,
        cross_streets=reading.cross_streets,
        landmark=reading.landmark,
        confidence=Confidence.A_CONFIRMAR,
        source=Source.REGLAS,
    )
    return _with_official_names(location)


def _altura(location: Location) -> int | None:
    return location.number.value if location.number else None


def _street_match(location: Location) -> StreetMatch | None:
    if location.street is None:
        return None
    return match_street(location.street, _altura(location))


def _with_official_names(location: Location) -> Location:
    """Take the streets said to their official names: the catalog decides, the lector proposes.

    Probable only when the dirección can be pinned down: one official street, found by its name
    or an alias (not by sound), plus an altura or a cross street. A confirmed one stays confirmed.
    """
    altura = _altura(location)
    match = _street_match(location)
    cross_official = []
    for cross in location.cross_streets:
        cross_match = match_street(cross)
        cross_official.append(cross_match.official if cross_match else cross)
    pinned = altura is not None or bool(location.cross_streets)
    sure = match is not None and match.kind is not MatchKind.FUZZY and len(match.candidates) == 1
    confidence = location.confidence
    if confidence is not Confidence.CONFIRMADO:
        confidence = Confidence.PROBABLE if sure and pinned else Confidence.A_CONFIRMAR
    return location.model_copy(
        update={
            "street_official": match.official if match else None,
            "candidates": [s.name for s in match.candidates]
            if match and len(match.candidates) > 1
            else [],
            "cross_streets_official": cross_official,
            "confidence": confidence,
        }
    )


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
    """Recompute prioridad, checklist, próxima pregunta and etapas from the state's data."""
    priority = state.priority
    if priority is None or priority.overridden_by_operator is None:
        priority = assess(state.incident, state.signals)
    state = state.model_copy(update={"priority": priority, "checklist": _checklist(state)})
    instructions = _instructions(state)
    critical = instructions[0] if instructions and instructions[0].critical else None
    state = state.model_copy(
        update={"instructions": instructions, "critical_instruction": critical}
    )
    return state.model_copy(
        update={"next_question": _next_question(state), "stages": _stages(state)}
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
    """Riesgo vital still to evaluate. Someone who does not breathe needs no other question.

    An operador's "no sabe" counts as evaluated, and so does skipping the universal questions.
    """
    if (
        not _has_victims(state)
        or UNIVERSAL in state.skipped_questions
        or _known(state, SignalId.RESPIRA) is SignalAnswer.NO
    ):
        return []
    return [s for s in (SignalId.CONSCIENTE, SignalId.RESPIRA) if not _evaluated(state, s)]


def _evaluated(state: CallState, signal_id: SignalId) -> bool:
    signal = _signal(state, signal_id)
    if signal is None:
        return False
    return signal.value is not SignalAnswer.NO_SABE or signal.confidence is Confidence.CONFIRMADO


_UNIVERSAL_TEXT = {
    SignalId.CONSCIENTE: "¿Está consciente?",
    SignalId.RESPIRA: "¿Respira?",
}


def _universal_question(state: CallState) -> NextQuestion | None:
    missing = _missing_vital_signs(state)
    if not missing:
        return None
    return NextQuestion(
        id=UNIVERSAL,
        text=" ".join(_UNIVERSAL_TEXT[s] for s in missing),
        signal_ids=missing,
    )


def _next_question(state: CallState) -> NextQuestion | None:
    """The first missing pregunta of the earliest etapa not done (SPEC §5.7)."""
    return _location_question(state) or _universal_question(state) or _key_question(state)


def _key_question(state: CallState) -> NextQuestion | None:
    for item in state.checklist:
        if item.status is QuestionStatus.PENDIENTE:
            return NextQuestion(id=item.question_id, text=item.text, signal_ids=[item.signal_id])
    return None


# Instrucciones


def _instructions(state: CallState) -> list[InstructionItem]:
    """The instrucciones that apply now; the first crítica among them is the active one.

    The crítica depends only on the señales that fire a P1 rule, not on the prioridad shown: an
    operador who lowers the prioridad does not hide what keeps someone alive.
    """
    incident = state.incident
    signals = {s.signal_id: s.value for s in state.signals}
    fired = frozenset(r.id for r in fired_rules(state.signals) if r.level is Priority.P1)
    applicable = instructions_for(
        incident.category if incident else None,
        incident.subtype if incident else None,
        signals,
        fired,
    )
    critical_id = next((i.id for i in applicable if i.critical), None)
    # The active crítica goes first; any other crítica that applies is read as a normal one.
    applicable.sort(key=lambda i: i.id != critical_id)
    # A crítica may repeat a normal instrucción ("No le saque el casco"): read it once.
    unique: list[Instruction] = []
    for instruction in applicable:
        if all(instruction.text != kept.text for kept in unique):
            unique.append(instruction)
    return [
        InstructionItem(
            instruction_id=i.id,
            text=i.text,
            critical=i.id == critical_id,
            read=i.id in state.read_instructions,
        )
        for i in unique
    ]


# Checklist


def _checklist(state: CallState) -> list[ChecklistItem]:
    """The preguntas clave of the tipo and subtipo, each with what the llamada knows of it."""
    if state.incident is None:
        return []
    signals = {s.signal_id: s for s in state.signals}
    items = []
    for question in checklist_for(state.incident.category, state.incident.subtype):
        signal = signals.get(question.signal_id)
        items.append(
            ChecklistItem(
                question_id=question.id,
                text=question.text,
                signal_id=question.signal_id,
                critical=question.critical,
                status=_status(signal, skipped=question.id in state.skipped_questions),
                value=signal.value if signal else None,
                evidence=signal.evidence if signal else None,
                source=signal.source if signal else None,
            )
        )
    return items


def _status(signal: SignalValue | None, *, skipped: bool) -> QuestionStatus:
    """Answered beats skipped, and skipped beats a pre-marca: the operador decided to move on."""
    if signal is not None and signal.confidence is Confidence.CONFIRMADO:
        return QuestionStatus.RESPONDIDA
    if skipped:
        return QuestionStatus.SALTEADA
    if signal is not None:
        return QuestionStatus.PRE_MARCADA
    return QuestionStatus.PENDIENTE


def _checklist_done(state: CallState) -> bool:
    closed = {QuestionStatus.RESPONDIDA, QuestionStatus.SALTEADA}
    return all(item.status in closed for item in state.checklist if item.critical)


def _llamante_spoke_without_location(state: CallState) -> bool:
    return state.location is None and any(t.speaker is Speaker.LLAMANTE for t in state.turns)


def _location_question(state: CallState) -> NextQuestion | None:
    """What is still missing to pin the ubicación down (DESIGN §Paso 4). It goes first."""
    location = state.location
    if location is None:
        return _ubicacion("¿Dónde es la emergencia?")
    if _is_confirmed(location):
        return None
    if location.street is None:
        return _ubicacion("¿Entre qué calles o cerca de qué entrada?")
    if location.number is None and not location.cross_streets and location.landmark is None:
        # Asked first: the altura also settles a name that is avenida and calle.
        return _altura_question(location.street)
    match = _street_match(location)
    if match is not None and match.avenida_o_calle:
        return _ubicacion("¿Es la avenida o la calle?")
    if match is not None and len(match.candidates) > 1 and _altura(location) is None:
        # A street renamed in part ("Serrano" or "Jorge Luis Borges"): the altura tells.
        return _altura_question(location.street)
    return None


def _altura_question(street: str) -> NextQuestion:
    return _ubicacion(f"¿A qué altura de {bare_name(street)}?")


def _ubicacion(text: str) -> NextQuestion:
    return NextQuestion(id="ubicacion", text=text)


def _is_confirmed(dato: Location | Incident | None) -> bool:
    return dato is not None and dato.confidence is Confidence.CONFIRMADO


def _stages(state: CallState) -> list[Stage]:
    """①, ②, ③ and ⑤ have a real status; ④ arrives with Derivar."""
    ubicar = StageStatus.HECHA if _is_confirmed(state.location) else StageStatus.ACTUAL
    if _is_confirmed(state.incident) and not _missing_vital_signs(state):
        que_pasa = StageStatus.HECHA
    elif state.incident is not None or state.signals:
        que_pasa = StageStatus.ACTUAL
    else:
        que_pasa = StageStatus.PENDIENTE
    if not state.checklist:
        preguntas = StageStatus.PENDIENTE
    elif _checklist_done(state):
        preguntas = StageStatus.HECHA
    else:
        preguntas = StageStatus.ACTUAL
    if not state.instructions:
        instrucciones = StageStatus.PENDIENTE
    elif all(i.read for i in state.instructions):
        instrucciones = StageStatus.HECHA
    else:
        instrucciones = StageStatus.ACTUAL
    status = {
        StageId.UBICAR: ubicar,
        StageId.QUE_PASA: que_pasa,
        StageId.PREGUNTAS: preguntas,
        StageId.INSTRUCCIONES: instrucciones,
    }
    critical = state.critical_instruction
    alert = {
        StageId.UBICAR: _llamante_spoke_without_location(state),
        StageId.INSTRUCCIONES: critical is not None and not critical.read,
    }
    return [
        Stage(id=s, status=status.get(s, StageStatus.PENDIENTE), alert=alert.get(s, False))
        for s in StageId
    ]
