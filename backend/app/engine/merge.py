"""Combinación of the two lectores (SPEC §5.4): what the rules and the IA read, as one state.

1. Every dato of either lector is verified against the relato; what is not there is dropped.
2. Señales are the **union** of both. When the two give a señal different values (sí against
   no), it stays with the rules' value, `a_confirmar`, and the IA's reading as its alternative:
   the operador sees both phrases. A "no se sabe" does not disagree: the known value wins.
3. The ubicación is the rules' one; the IA's only fills in when the rules found none (the rules
   read the dirección by layers and the catalog of streets checks it).
4. When the tipos differ, the llamada is **en disputa** until the operador chooses; meanwhile the
   incidente is the option with the higher prioridad (ante la duda, sobre-priorizar).

With one lector only (modo simulado, or the IA fell back) nothing can disagree: confidence never
drops for lack of a second lector.
"""

from collections.abc import Sequence

from app.catalog.models import Category, Priority
from app.catalog.signals import SignalAnswer, SignalId
from app.engine.models import (
    CallState,
    Confidence,
    Incident,
    SignalAlternative,
    SignalValue,
    Source,
    TypeDispute,
)
from app.engine.priority import assess
from app.engine.state import apply_reading
from app.engine.verification import verify
from app.readers.models import Evidence, IncidentReading, ReaderOutput, SignalReading
from app.transcript.models import Turn


class NoTypeDisputeError(ValueError):
    """The operador chose a tipo that is not one of the options en disputa."""


def apply_readings(state: CallState, rules: ReaderOutput, ia: ReaderOutput | None) -> CallState:
    """Fold the lectura of each lector into the state. `ia` is None with a single lector."""
    if ia is None:
        return apply_reading(state, rules).model_copy(update={"type_dispute": None})
    rules, ia = verified(rules, state.turns), verified(ia, state.turns)
    by_rules = {s.signal_id: s for s in rules.signals}
    by_ia = {s.signal_id: s for s in ia.signals}
    disputed = {i for i in by_rules.keys() & by_ia.keys() if _disagree(by_rules[i], by_ia[i])}
    ia_wins = {
        i
        for i, s in by_ia.items()
        if i not in disputed and (i not in by_rules or (_unknown(by_rules[i]) and not _unknown(s)))
    }

    # The rules' value of a señal en desacuerdo goes in too: it is the value the señal keeps, and
    # over a confirmed señal it raises the same aviso as with the rules alone.
    state = apply_reading(
        state,
        ReaderOutput(
            location=rules.location,
            signals=[s for i, s in by_rules.items() if i not in ia_wins],
        ),
    )
    state = apply_reading(
        state,
        ReaderOutput(
            location=ia.location if rules.location is None else None,
            signals=[by_ia[i] for i in ia_wins],
        ),
        Source.IA,
    )
    signals = _with_disagreements(state.signals, by_rules, by_ia, disputed)
    state = state.model_copy(update={"signals": signals})
    state = _with_incident(state, rules.incident, ia.incident)
    # An empty lectura changes no dato: it recomputes what follows from them.
    return apply_reading(state, ReaderOutput())


def choose_type(state: CallState, category: Category) -> CallState:
    """The operador picks one of the tipos en disputa: it is confirmed as the lector read it."""
    dispute = state.type_dispute
    option = next((o for o in dispute.options if o.category is category), None) if dispute else None
    if option is None:
        raise NoTypeDisputeError(category)
    chosen = option.model_copy(update={"confidence": Confidence.CONFIRMADO})
    return apply_reading(
        state.model_copy(update={"incident": chosen, "type_dispute": None}), ReaderOutput()
    )


def verified(output: ReaderOutput, turns: Sequence[Turn]) -> ReaderOutput:
    """Only the datos whose phrases are in the relato, with the evidence located on it."""
    location = output.location
    if location is not None:
        evidence = _verified(location.evidence, turns)
        ok = evidence and len(evidence) == len(location.evidence)
        location = location.model_copy(update={"evidence": evidence}) if ok else None
    incident = output.incident
    if incident is not None:
        evidence = _verified(incident.evidence, turns)
        incident = incident.model_copy(update={"evidence": evidence}) if evidence else None
    signals = [
        s.model_copy(update={"evidence": found})
        for s in output.signals
        if (found := verify(s.evidence, turns)) is not None
    ]
    return ReaderOutput(location=location, incident=incident, signals=signals)


def _verified(evidence: Sequence[Evidence], turns: Sequence[Turn]) -> list[Evidence]:
    return [found for ev in evidence if (found := verify(ev, turns)) is not None]


def _unknown(reading: SignalReading) -> bool:
    return reading.value is SignalAnswer.NO_SABE


def _disagree(left: SignalReading, right: SignalReading) -> bool:
    return not _unknown(left) and not _unknown(right) and left.value is not right.value


def _with_disagreements(
    signals: Sequence[SignalValue],
    by_rules: dict[SignalId, SignalReading],
    by_ia: dict[SignalId, SignalReading],
    disputed: set[SignalId],
) -> list[SignalValue]:
    merged = {s.signal_id: s for s in signals}
    for signal_id in disputed:
        current = merged.get(signal_id)
        if current is not None and current.confidence is Confidence.CONFIRMADO:
            continue
        rules, ia = by_rules[signal_id], by_ia[signal_id]
        merged[signal_id] = SignalValue(
            signal_id=signal_id,
            value=rules.value,
            evidence=rules.evidence,
            source=Source.REGLAS,
            confidence=Confidence.A_CONFIRMAR,
            alternative=SignalAlternative(value=ia.value, evidence=ia.evidence, source=Source.IA),
        )
    return [merged[s] for s in SignalId if s in merged]


def _with_incident(
    state: CallState, rules: IncidentReading | None, ia: IncidentReading | None
) -> CallState:
    if state.incident is not None and state.incident.confidence is Confidence.CONFIRMADO:
        # The confirmed tipo stays; a lectura that changes it raises the aviso (contradictions).
        state = state.model_copy(update={"type_dispute": None})
        if rules is not None:
            return apply_reading(state, ReaderOutput(incident=rules))
        if ia is not None:
            return apply_reading(state, ReaderOutput(incident=ia), Source.IA)
        return state
    if rules is not None and ia is not None and rules.category is not ia.category:
        options = [_option(rules, Source.REGLAS), _option(ia, Source.IA)]
        incident = min(options, key=lambda o: _rank(state, o))  # ties go to the rules
        return state.model_copy(
            update={"incident": incident, "type_dispute": TypeDispute(options=options)}
        )
    state = state.model_copy(update={"type_dispute": None})
    if rules is not None and ia is not None:
        # Both lectores agree on the tipo: that is enough to make it probable.
        agreed = rules.model_copy(
            update={
                "subtype": rules.subtype or ia.subtype,
                "evidence": [*rules.evidence, *(e for e in ia.evidence if e not in rules.evidence)],
                "runner_up": None,
            }
        )
        return apply_reading(state, ReaderOutput(incident=agreed))
    if rules is not None:
        return apply_reading(state, ReaderOutput(incident=rules))
    if ia is not None:
        return apply_reading(state, ReaderOutput(incident=ia), Source.IA)
    return state


def _option(reading: IncidentReading, source: Source) -> Incident:
    return Incident(
        category=reading.category,
        subtype=reading.subtype,
        evidence=reading.evidence,
        confidence=Confidence.A_CONFIRMAR,
        source=source,
    )


def _rank(state: CallState, option: Incident) -> int:
    """Lower is more urgent: the prioridad the llamada would have with this tipo."""
    assessment = assess(option, state.signals)
    return list(Priority).index(assessment.level) if assessment else len(Priority)
