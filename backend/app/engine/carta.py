"""Carta de Llamada: a fixed template over the confirmed data of a llamada (SPEC §5.9, ADR 0001).

No IA writes it. Ubicación and tipo enter once the operador confirmed them. A señal enters when
it is confirmed or when it is a pre-marca (said by the llamante, phrase verified, marked "sin
confirmar"): deriving early must not hide «adentro quedó el cocinero» from the despachador. A dato
a_confirmar never enters. Each line says where it comes from: said by the llamante (with the
phrase), from the system, or loaded by the operador.
It carries no recursos: the despachador decides them.
"""

from app.catalog.incidents import SUBTYPES, TYPES
from app.catalog.signals import SIGNALS, SignalAnswer, SignalId
from app.engine.models import (
    CallState,
    Carta,
    CartaChange,
    CartaDato,
    CartaOrigin,
    Confidence,
    Location,
    MissingQuestion,
    QuestionStatus,
    SignalValue,
    Source,
)
from app.readers.models import Evidence, NumberKind

# Señales about the people involved: they go to «quién está en riesgo», the rest to «qué pasa».
PEOPLE_SIGNALS: frozenset[SignalId] = frozenset(
    {
        SignalId.PERSONA_ATRAPADA,
        SignalId.ATRAPADO_VEHICULO,
        SignalId.HERIDOS,
        SignalId.MENORES,
        SignalId.CONSCIENTE,
        SignalId.RESPIRA,
        SignalId.SANGRADO_ABUNDANTE,
        SignalId.DIFICULTAD_RESPIRAR,
        SignalId.GOLPE_CABEZA,
    }
)

_ANSWER_TEXT = {SignalAnswer.SI: "Sí", SignalAnswer.NO: "No", SignalAnswer.NO_SABE: "No se sabe"}
_UNIVERSAL = "universal"


def build(state: CallState) -> Carta:
    """The Carta as it stands now. `state` already has its checklist and próxima pregunta."""
    known = [s for s in state.signals if s.confidence is not Confidence.A_CONFIRMAR]
    return Carta(
        where=_where(state.location),
        what=_what(state) + [_signal(s) for s in known if s.signal_id not in PEOPLE_SIGNALS],
        priority=_priority(state),
        at_risk=[_signal(s) for s in known if s.signal_id in PEOPLE_SIGNALS],
        instructions=[
            CartaDato(
                key=f"instruccion.{i.instruction_id}",
                label="Instrucción dada",
                value=i.text,
                origin=CartaOrigin.OPERADOR,
            )
            for i in state.instructions
            if i.read
        ],
        notes=[
            CartaDato(
                key=f"nota.{n}", label="Nota del operador", value=text, origin=CartaOrigin.OPERADOR
            )
            for n, text in enumerate(state.notes, start=1)
        ],
        missing=_missing(state),
    )


def diff(before: Carta, after: Carta) -> list[CartaChange]:
    """Lines of the Carta that appeared, changed or went away, in the Carta's order."""
    old = {d.key: d for d in _lines(before)}
    new = {d.key: d for d in _lines(after)}
    changes = [
        CartaChange(
            key=key,
            label=dato.label,
            before=_shown(old[key]) if key in old else None,
            after=_shown(dato),
        )
        for key, dato in new.items()
        if key not in old or _shown(old[key]) != _shown(dato)
    ]
    changes += [
        CartaChange(key=key, label=dato.label, before=_shown(dato), after=None)
        for key, dato in old.items()
        if key not in new
    ]
    return changes


def _shown(dato: CartaDato) -> str:
    """How a line reads to the despachador: confirming a pre-marca is news too."""
    return dato.value if dato.confirmed else f"{dato.value} (sin confirmar)"


def _lines(carta: Carta) -> list[CartaDato]:
    return [
        *carta.where,
        *carta.what,
        *carta.priority,
        *carta.at_risk,
        *carta.instructions,
        *carta.notes,
    ]


def _quote(evidence: list[Evidence]) -> str | None:
    return evidence[0].quote if evidence else None


def _where(location: Location | None) -> list[CartaDato]:
    if location is None or location.confidence is not Confidence.CONFIRMADO:
        return []
    lines = []
    if location.said:
        lines.append(
            CartaDato(
                key="ubicacion.dicho",
                label="Dijo",
                value=location.said,
                origin=CartaOrigin.LLAMANTE,
                quote=_quote(location.evidence),
            )
        )
    by_operador = location.source is Source.OPERADOR
    lines.append(
        CartaDato(
            key="ubicacion.direccion",
            label="Dirección",
            value=format_address(location),
            origin=CartaOrigin.OPERADOR if by_operador else CartaOrigin.SISTEMA,
        )
    )
    return lines


def format_address(location: Location) -> str:
    """One-line dirección with the official names, e.g. "AV. CORRIENTES 1540, casi MONTEVIDEO"."""
    street = location.street_official or location.street
    cross = location.cross_streets_official or location.cross_streets
    number = location.number
    parts: list[str] = []
    if street:
        if number is not None and number.kind is NumberKind.ESQUINA and cross:
            parts.append(f"{street} y {cross[0]}")
        else:
            head = street
            if number is not None and number.value is not None:
                prefix = {NumberKind.AL: " al ", NumberKind.KM: " km "}.get(number.kind, " ")
                head += f"{prefix}{number.value}"
            if number is not None and number.kind is NumberKind.SN:
                head += " s/n"
            parts.append(head)
            if len(cross) == 1:
                parts.append(f"casi {cross[0]}")
            elif len(cross) >= 2:
                parts.append(f"entre {cross[0]} y {cross[1]}")
    if location.landmark:
        parts.append(location.landmark)
    return ", ".join(parts) or location.said


def _what(state: CallState) -> list[CartaDato]:
    incident = state.incident
    if incident is None or incident.confidence is not Confidence.CONFIRMADO:
        return []
    by_operador = incident.source is Source.OPERADOR
    origin = CartaOrigin.OPERADOR if by_operador else CartaOrigin.LLAMANTE
    quote = None if by_operador else _quote(incident.evidence)
    lines = [
        CartaDato(
            key="incidente.tipo",
            label="Tipo",
            value=TYPES[incident.category].label,
            origin=origin,
            quote=quote,
        )
    ]
    if incident.subtype is not None:
        lines.append(
            CartaDato(
                key="incidente.subtipo",
                label="Subtipo",
                value=SUBTYPES[incident.subtype].label,
                origin=origin,
                quote=quote,
            )
        )
    return lines


def _signal(signal: SignalValue) -> CartaDato:
    said = signal.source is not Source.OPERADOR and signal.evidence is not None
    return CartaDato(
        key=f"senal.{signal.signal_id.value}",
        label=SIGNALS[signal.signal_id].label,
        value=_ANSWER_TEXT[signal.value],
        origin=CartaOrigin.LLAMANTE if said else CartaOrigin.OPERADOR,
        quote=signal.evidence.quote if said and signal.evidence else None,
        confirmed=signal.confidence is Confidence.CONFIRMADO,
    )


def _priority(state: CallState) -> list[CartaDato]:
    """The prioridad the operador sees when deriving, and its porqué.

    It is calculated by the tabla de reglas, not suggested: the operador takes it by deriving, or
    changes it with a motivo. The señales behind it are in the Carta, confirmed or as pre-marcas.
    """
    priority = state.priority
    incident = state.incident
    if priority is None or incident is None or incident.confidence is not Confidence.CONFIRMADO:
        return []
    override = priority.overridden_by_operator
    origin = CartaOrigin.OPERADOR if override else CartaOrigin.SISTEMA
    why = f"Cambiada por el operador: {override.reason}" if override else priority.rule
    return [
        CartaDato(key="prioridad", label="Prioridad", value=priority.level.value, origin=origin),
        CartaDato(key="prioridad.porque", label="Por qué", value=why, origin=origin),
    ]


def _missing(state: CallState) -> list[MissingQuestion]:
    """Preguntas nobody answered yet: pending, or skipped with nothing said about them.

    A pre-marca is not missing: its señal is already in the Carta with the llamante's phrase.
    """
    missing = []
    if state.next_question is not None and state.next_question.id == _UNIVERSAL:
        missing.append(MissingQuestion(text=state.next_question.text))
    missing += [
        MissingQuestion(text=item.text, skipped=item.status is QuestionStatus.SALTEADA)
        for item in state.checklist
        if item.status is QuestionStatus.PENDIENTE
        or (item.status is QuestionStatus.SALTEADA and item.value is None)
    ]
    return missing
