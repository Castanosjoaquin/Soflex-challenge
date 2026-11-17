"""Build the traza of a lectura from what the CallService already has in hand.

Nothing here decides anything: the control de evidencia and the desacuerdos are asked again to
`merge` (the same functions the combinación uses), and the changes are the difference between
the llamada before the turno and after the lectura.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from app.catalog.incidents import SUBTYPES, TYPES
from app.catalog.signals import SIGNALS, SignalAnswer
from app.engine import merge
from app.engine.carta import format_address
from app.engine.models import (
    CallState,
    Confidence,
    Incident,
    QuestionStatus,
    Source,
)
from app.readers.ia.reader import IAReading
from app.readers.models import ReaderOutput
from app.trace.models import (
    Change,
    ChangeKind,
    Disagreement,
    Discarded,
    ReadingTrace,
    Step,
    StepTime,
)
from app.transcript.models import Turn

ANSWER = {SignalAnswer.SI: "sí", SignalAnswer.NO: "no", SignalAnswer.NO_SABE: "no se sabe"}
NOT_IN_RELATO = "no aparece en el relato"


class Stopwatch:
    """Times each step of a lectura, in milliseconds."""

    def __init__(self) -> None:
        self.steps: list[StepTime] = []

    @contextmanager
    def step(self, step: Step) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            ms = round((time.perf_counter() - started) * 1000, 1)
            self.steps.append(StepTime(step=step, ms=ms))


def build(
    *,
    index: int,
    at: datetime,
    turn: Turn,
    before: CallState,
    after: CallState,
    rules: ReaderOutput,
    ia: IAReading | None,
    steps: list[StepTime],
) -> ReadingTrace:
    """`before` is the llamada before the turno; `after`, once the lectura is folded in."""
    trace = ReadingTrace(
        call_id=after.call_id,
        index=index,
        at=at,
        turn=turn,
        turns=len(after.turns),
        mode=after.mode,
        steps=steps,
        rules=rules,
        ia=ia,
        changes=changes(before, after),
        confirmed=[
            target
            for target, dato in (("location", after.location), ("incident", after.incident))
            if dato is not None and dato.confidence is Confidence.CONFIRMADO
        ],
        priority=after.priority.level if after.priority else None,
    )
    if ia is None or ia.output is None:
        return trace
    # Both lectores combined: the same control de evidencia and desacuerdos as `merge`.
    checked_rules = merge.check(rules, after.turns)
    checked_ia = merge.check(ia.output, after.turns)
    discarded = [
        Discarded(source=source, target=d.target, quote=d.quote, reason=NOT_IN_RELATO)
        for source, checked in ((Source.REGLAS, checked_rules), (Source.IA, checked_ia))
        for d in checked.dropped
    ]
    return trace.model_copy(
        update={
            "proposed": checked_rules.proposed + checked_ia.proposed,
            "discarded": discarded,
            "disagreements": disagreements(checked_rules.output, checked_ia.output),
        }
    )


def disagreements(rules: ReaderOutput, ia: ReaderOutput) -> list[Disagreement]:
    found: list[Disagreement] = []
    if rules.incident and ia.incident and rules.incident.category is not ia.incident.category:
        found.append(
            Disagreement(
                target="incident",
                rules=TYPES[rules.incident.category].label,
                ia=TYPES[ia.incident.category].label,
            )
        )
    by_rules = {s.signal_id: s.value for s in rules.signals}
    by_ia = {s.signal_id: s.value for s in ia.signals}
    found += [
        Disagreement(target=i.value, rules=ANSWER[by_rules[i]], ia=ANSWER[by_ia[i]])
        for i in merge.disputed_signals(rules, ia)
    ]
    return found


def changes(before: CallState, after: CallState) -> list[Change]:
    """What the lectura changed, in the order the panel reads it."""
    found: list[Change] = []
    old_location = format_address(before.location) if before.location else None
    new_location = format_address(after.location) if after.location else None
    if new_location != old_location and after.location is not None:
        quote = after.location.evidence[0].quote if after.location.evidence else None
        found.append(
            Change(
                kind=ChangeKind.LOCATION,
                target="location",
                label="Ubicación",
                before=old_location,
                after=new_location,
                quote=quote,
            )
        )
    if _incident(after.incident) != _incident(before.incident) and after.incident is not None:
        quote = after.incident.evidence[0].quote if after.incident.evidence else None
        found.append(
            Change(
                kind=ChangeKind.INCIDENT,
                target="incident",
                label="Tipo",
                before=_incident(before.incident),
                after=_incident(after.incident),
                quote=quote,
            )
        )
    if after.type_dispute is not None and after.type_dispute != before.type_dispute:
        options = " / ".join(
            f"{o.source.value}: {TYPES[o.category].label}" for o in after.type_dispute.options
        )
        found.append(
            Change(
                kind=ChangeKind.TYPE_DISPUTE,
                target="type_dispute",
                label="Tipo en disputa",
                after=options,
            )
        )
    found += _signal_changes(before, after)
    premarked = {i.question_id for i in before.checklist if i.status is QuestionStatus.PRE_MARCADA}
    for item in after.checklist:
        if item.status is QuestionStatus.PRE_MARCADA and item.question_id not in premarked:
            found.append(
                Change(
                    kind=ChangeKind.PREMARK,
                    target=item.question_id,
                    label=item.text,
                    after=ANSWER[item.value] if item.value else None,
                    quote=item.evidence.quote if item.evidence else None,
                )
            )
    old_level = before.priority.level if before.priority else None
    if after.priority is not None and after.priority.level is not old_level:
        found.append(
            Change(
                kind=ChangeKind.PRIORITY,
                target="priority",
                label="Prioridad",
                before=old_level.value if old_level else None,
                after=f"{after.priority.level.value} ({after.priority.rule})",
            )
        )
    raised = {a.id for a in before.avisos}
    found += [
        Change(kind=ChangeKind.AVISO, target=a.id, label="Aviso", after=a.text)
        for a in after.avisos
        if a.id not in raised
    ]
    return found


def _signal_changes(before: CallState, after: CallState) -> list[Change]:
    known = {s.signal_id: s.value for s in before.signals}
    return [
        Change(
            kind=ChangeKind.SIGNAL,
            target=s.signal_id.value,
            label=SIGNALS[s.signal_id].label,
            before=ANSWER[known[s.signal_id]] if s.signal_id in known else None,
            after=ANSWER[s.value],
            quote=s.evidence.quote if s.evidence else None,
        )
        for s in after.signals
        if known.get(s.signal_id) is not s.value
    ]


def _incident(incident: Incident | None) -> str | None:
    if incident is None:
        return None
    label = TYPES[incident.category].label
    return f"{label} · {SUBTYPES[incident.subtype].label}" if incident.subtype else label
