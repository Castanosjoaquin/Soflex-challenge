"""Autocorrección vs. contradicción: a lectura never overwrites a human decision (SPEC §5.4.5).

When the relato changes a dato the operador has not confirmed, the latest value wins and nothing
is said: that is `state.apply_reading`. When it changes a confirmed one (ubicación, tipo or a
señal), the dato stays as it is and an **aviso** asks the operador: «Antes dijo 1540, ahora dice
1450». The same happens when a P1 señal appears over a prioridad the operador lowered.

These are the only two avisos that interrupt (DESIGN §Paso 8). To keep them rare, an aviso is
raised only when the relato *changes*: what the relato said last of each dato is kept in
`CallState.heard`, so a relato that still says the same thing, or a dato the operador corrected
by hand, raises nothing.
"""

from collections.abc import Sequence
from enum import StrEnum

from app.catalog.incidents import TYPES
from app.catalog.models import Priority
from app.catalog.signals import SIGNALS, SignalAnswer
from app.engine.carta import format_address
from app.engine.models import (
    Aviso,
    AvisoKind,
    AvisoStatus,
    CallState,
    Confidence,
    Incident,
    Location,
    PriorityAssessment,
    PriorityOverride,
    SignalValue,
)
from app.engine.priority import assess, fired_rules
from app.readers.models import Evidence, NumberKind

LOCATION = "location"
INCIDENT = "incident"
PRIORITY = "priority"


class Resolution(StrEnum):
    ACEPTAR = "aceptar"  # take the new value: it becomes the confirmed one
    MANTENER = "mantener"  # keep the value confirmed before


class UnknownAvisoError(ValueError):
    """The operador resolved an aviso that does not exist or is already resolved."""


def on_reading(
    state: CallState,
    location: Location | None,
    incident: Incident | None,
    signals: Sequence[SignalValue],
) -> CallState:
    """Raise an aviso for each confirmed dato this lectura changes, and remember what it heard.

    `state` already has the lectura folded in (confirmed data untouched); `location`, `incident`
    and `signals` are what the relato says now, verified.
    """
    avisos = list(state.avisos)
    heard = dict(state.heard)
    if location is not None:
        said = _location_key(location)
        if state.location is not None and _changed(state.location, said, heard.get(LOCATION)):
            avisos = _raised(avisos, _location_aviso(state.location, location))
        heard[LOCATION] = said
    if incident is not None:
        said = incident.category.value
        if state.incident is not None and _changed(state.incident, said, heard.get(INCIDENT)):
            avisos = _raised(avisos, _incident_aviso(state.incident, incident))
        heard[INCIDENT] = said
    known = {s.signal_id: s for s in state.signals}
    for signal in signals:
        key = signal.signal_id.value
        confirmed = known.get(signal.signal_id)
        # "No se sabe" does not contradict what is known: the llamante just does not know now.
        if (
            confirmed is not None
            and signal.value is not SignalAnswer.NO_SABE
            and _changed(confirmed, signal.value.value, heard.get(key))
        ):
            avisos = _raised(avisos, _signal_aviso(confirmed, signal))
        heard[key] = signal.value.value
    return state.model_copy(update={"avisos": avisos, "heard": heard})


def on_priority(before: CallState, after: CallState) -> CallState:
    """A P1 señal appeared and the operador's prioridad is lower: say so, do not change it.

    The instrucción crítica does not wait for this: it depends on the señales, not on the
    prioridad shown (`state._instructions`).
    """
    priority = after.priority
    if priority is None or priority.overridden_by_operator is None:
        return after
    if priority.level is Priority.P1:
        return after
    known = {r.id for r in fired_rules(before.signals)}
    appeared = [
        r for r in fired_rules(after.signals) if r.level is Priority.P1 and r.id not in known
    ]
    rules_says = assess(after.incident, after.signals)
    if not appeared or rules_says is None:
        return after
    rule = appeared[0]
    proposed = rules_says.model_copy(
        update={
            "overridden_by_operator": PriorityOverride(
                from_level=priority.level, reason=f"Aceptó el aviso de P1: {rule.label}"
            )
        }
    )
    aviso = Aviso(
        id="",
        kind=AvisoKind.SENAL_P1,
        target=PRIORITY,
        label="Prioridad",
        before=priority.level.value,
        after=Priority.P1.value,
        text=f"Apareció una señal de P1 ({rule.label}) y la prioridad está en {priority.level}",
        evidence=[r.evidence for r in rules_says.reasons if r.evidence is not None],
        proposed=proposed,
    )
    return after.model_copy(update={"avisos": _raised(after.avisos, aviso)})


def resolve(state: CallState, aviso_id: str, resolution: Resolution) -> CallState:
    """The operador takes the new value or keeps the one before. Either way the aviso closes.

    The caller recomputes what follows from the data (prioridad, Carta…).
    """
    aviso = next(
        (a for a in state.avisos if a.id == aviso_id and a.status is AvisoStatus.PENDIENTE), None
    )
    if aviso is None:
        raise UnknownAvisoError(aviso_id)
    accepted = resolution is Resolution.ACEPTAR
    status = AvisoStatus.ACEPTADO if accepted else AvisoStatus.MANTENIDO
    avisos = [a.model_copy(update={"status": status}) if a is aviso else a for a in state.avisos]
    state = state.model_copy(update={"avisos": avisos})
    if not accepted:
        return state
    match aviso.proposed:
        case Location() | Incident() as dato:
            confirmed = dato.model_copy(update={"confidence": Confidence.CONFIRMADO})
            return state.model_copy(update={aviso.target: confirmed})
        case SignalValue() as signal:
            confirmed_signal = signal.model_copy(update={"confidence": Confidence.CONFIRMADO})
            signals = [
                confirmed_signal if s.signal_id is signal.signal_id else s for s in state.signals
            ]
            return state.model_copy(update={"signals": signals})
        case PriorityAssessment() as priority:
            return state.model_copy(update={"priority": priority})


def _changed(confirmed: Location | Incident | SignalValue, said: str, before: str | None) -> bool:
    """The relato now says something else than before, about a dato the operador confirmed."""
    if confirmed.confidence is not Confidence.CONFIRMADO:
        return False
    return said != before and said != _key(confirmed)


def _key(dato: Location | Incident | SignalValue) -> str:
    match dato:
        case Location():
            return _location_key(dato)
        case Incident():
            return dato.category.value
        case SignalValue():
            return dato.value.value


def _location_key(location: Location) -> str:
    """Street and altura: a relato that leaves out the cross street does not change the dato."""
    street = location.street_official or location.street
    if street is None:
        return location.landmark or location.said
    return f"{street} {_altura(location)}"


def _raised(avisos: list[Aviso], aviso: Aviso) -> list[Aviso]:
    """Add the aviso; a pending one about the same dato is replaced: the relato moved on."""
    number = 1 + max((int(a.id.removeprefix("aviso-")) for a in avisos), default=0)
    kept = [
        a for a in avisos if not (a.target == aviso.target and a.status is AvisoStatus.PENDIENTE)
    ]
    return [*kept, aviso.model_copy(update={"id": f"aviso-{number}"})]


def _new_evidence(before: Sequence[Evidence], now: Sequence[Evidence]) -> list[Evidence]:
    fresh = [e for e in now if e not in before]
    return fresh or list(now)


def _contradiction(
    target: str,
    label: str,
    before: str,
    after: str,
    evidence: list[Evidence],
    proposed: Location | Incident | SignalValue,
) -> Aviso:
    return Aviso(
        id="",
        kind=AvisoKind.CONTRADICCION,
        target=target,
        label=label,
        before=before,
        after=after,
        text=f"Antes dijo {before}, ahora dice {after}",
        evidence=evidence,
        proposed=proposed,
    )


def _location_aviso(confirmed: Location, said: Location) -> Aviso:
    """Only the altura when the street is the same: «Antes dijo 1540, ahora dice 1450»."""
    same_street = (confirmed.street_official or confirmed.street) == (
        said.street_official or said.street
    )
    if same_street and confirmed.number != said.number:
        label, before, after = "Altura", _altura(confirmed), _altura(said)
    else:
        label, before, after = "Dirección", format_address(confirmed), format_address(said)
    evidence = _new_evidence(confirmed.evidence, said.evidence)
    return _contradiction(LOCATION, label, before, after, evidence, said)


def _altura(location: Location) -> str:
    number = location.number
    if number is None:
        return "sin altura"
    if number.kind is NumberKind.SN:
        return "sin número"
    if number.kind is NumberKind.ESQUINA:
        return "la esquina"
    prefix = {NumberKind.AL: "al ", NumberKind.KM: "km "}.get(number.kind, "")
    return f"{prefix}{number.value}"


def _incident_aviso(confirmed: Incident, said: Incident) -> Aviso:
    before, after = TYPES[confirmed.category].label, TYPES[said.category].label
    evidence = _new_evidence(confirmed.evidence, said.evidence)
    return _contradiction(INCIDENT, "Tipo", before, after, evidence, said)


_ANSWER = {SignalAnswer.SI: "sí", SignalAnswer.NO: "no", SignalAnswer.NO_SABE: "no se sabe"}


def _signal_aviso(confirmed: SignalValue, said: SignalValue) -> Aviso:
    label = SIGNALS[said.signal_id].label
    before = f"«{label}: {_ANSWER[confirmed.value]}»"
    after = f"«{label}: {_ANSWER[said.value]}»"
    evidence = [said.evidence] if said.evidence is not None else []
    return _contradiction(said.signal_id.value, label, before, after, evidence, said)
