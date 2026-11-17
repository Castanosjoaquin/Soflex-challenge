"""Prioridad by the tabla de reglas (SPEC §5.6): never by the IA, always with its porqué."""

from collections.abc import Sequence

from app.catalog.incidents import SUBTYPES
from app.catalog.models import Priority
from app.catalog.priority import BASE_LABEL, BASE_PRIORITY, PRIORITY_RULES, RECLAMO_LABEL
from app.engine.models import Incident, PriorityAssessment, PriorityReason, SignalValue


def assess(incident: Incident | None, signals: Sequence[SignalValue]) -> PriorityAssessment | None:
    """The first rule whose señales all hold; else the base of the tipo (P4 for a reclamo).

    With no rule and no tipo there is nothing to prioritize yet.
    """
    known = {s.signal_id: s for s in signals}
    for rule in PRIORITY_RULES:
        matched = [known.get(c.signal_id) for c in rule.when]
        if all(
            m is not None and m.value is c.value for m, c in zip(matched, rule.when, strict=True)
        ):
            reasons = [
                PriorityReason(signal_id=m.signal_id, value=m.value, evidence=m.evidence)
                for m in matched
                if m is not None
            ]
            return PriorityAssessment(level=rule.level, rule=rule.label, reasons=reasons)
    if incident is None:
        return None
    if incident.subtype is not None and SUBTYPES[incident.subtype].reclamo:
        return PriorityAssessment(level=Priority.P4, rule=RECLAMO_LABEL)
    return PriorityAssessment(level=BASE_PRIORITY[incident.category], rule=BASE_LABEL)
