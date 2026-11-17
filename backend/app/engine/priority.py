"""Prioridad by the tabla de reglas (SPEC §5.6): never by the IA, always with its porqué."""

from collections.abc import Sequence

from app.catalog.incidents import SUBTYPES
from app.catalog.models import Priority
from app.catalog.priority import (
    BASE_LABEL,
    BASE_PRIORITY,
    PRIORITY_RULES,
    RECLAMO_LABEL,
    PriorityRule,
)
from app.engine.models import Incident, PriorityAssessment, PriorityReason, SignalValue


def assess(incident: Incident | None, signals: Sequence[SignalValue]) -> PriorityAssessment | None:
    """The first rule whose señales all hold; else the base of the tipo (P4 for a reclamo).

    With no rule and no tipo there is nothing to prioritize yet.
    """
    known = {s.signal_id: s for s in signals}
    for rule in fired_rules(signals):
        reasons = [
            PriorityReason(signal_id=m.signal_id, value=m.value, evidence=m.evidence)
            for c in rule.when
            if (m := known.get(c.signal_id)) is not None
        ]
        return PriorityAssessment(level=rule.level, rule=rule.label, reasons=reasons)
    if incident is None:
        return None
    if incident.subtype is not None and SUBTYPES[incident.subtype].reclamo:
        return PriorityAssessment(level=Priority.P4, rule=RECLAMO_LABEL)
    return PriorityAssessment(level=BASE_PRIORITY[incident.category], rule=BASE_LABEL)


def fired_rules(signals: Sequence[SignalValue]) -> list[PriorityRule]:
    """Every rule of the tabla whose señales all hold, in the tabla's order."""
    known = {s.signal_id: s.value for s in signals}
    return [r for r in PRIORITY_RULES if all(known.get(c.signal_id) is c.value for c in r.when)]
