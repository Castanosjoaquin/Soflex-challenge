"""A traza told in natural language, as the panel's detalle técnico shows it (DESIGN §9).

    Lectura #3 de la llamada 1f2e… (después de «hay una garrafa…») · IA · 1,4 s
    - Ordenó el texto: 3 turnos.
    - Lector por reglas: encontró 4 señales, la ubicación y el tipo en 6 ms.
    - Lector con IA: respondió en 1,2 s. El primer intento vino mal (…); se le pidió corregir y
      el segundo intento fue válido.
    - Control de evidencia: 9 datos con su frase en el relato, 1 descartado (…).

Lines marked `alert` are the ones that went wrong or need a look: the panel stresses them.
"""

from pydantic import BaseModel, ConfigDict

from app.catalog.signals import SIGNALS, SignalId
from app.engine.models import Mode, Source
from app.readers.ia.reader import IAReading, IAStatus
from app.readers.models import ReaderOutput
from app.trace.models import Change, ChangeKind, Discarded, ReadingTrace, Step


class TraceLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    alert: bool = False


class Narration(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    lines: list[TraceLine]


_MODE = {Mode.IA: "IA", Mode.REGLAS: "solo reglas", Mode.SIMULADO: "modo simulado"}
_LECTOR = {Source.REGLAS: "lector por reglas", Source.IA: "lector con IA"}
_FALLBACK = "Esta lectura es solo por reglas."
_MAX_ERROR = 160


def narrate(trace: ReadingTrace) -> Narration:
    excerpt = _shorten(trace.turn.text, 48)
    title = (
        f"Lectura #{trace.index} de la llamada {trace.call_id} (después de «{excerpt}») · "
        f"{_MODE[trace.mode]} · {duration(trace.total_ms)}"
    )
    lines = [
        TraceLine(text=f"Ordenó el texto: {_count(trace.turns, 'turno', 'turnos')}."),
        TraceLine(
            text=f"Lector por reglas: {_found(trace.rules)} en {duration(_ms(trace, Step.REGLAS))}."
        ),
        *_ia(trace),
        *_evidence(trace),
        *_agreement(trace),
        *_changes(trace),
    ]
    return Narration(title=title, lines=lines)


def duration(ms: float) -> str:
    """ "6 ms", "1,4 s": as the sala reads it."""
    if ms < 1:
        return "menos de 1 ms"
    if ms < 1000:
        return f"{round(ms)} ms"
    return f"{ms / 1000:.1f} s".replace(".", ",")


def dato_label(target: str) -> str:
    """How the traza names a dato: the ubicación, the tipo, or a señal by its label."""
    if target == "location":
        return "la ubicación"
    if target == "incident":
        return "el tipo"
    try:
        return SIGNALS[SignalId(target)].label
    except ValueError:
        return target


def _ia(trace: ReadingTrace) -> list[TraceLine]:
    ia = trace.ia
    if ia is None:
        return [TraceLine(text="Lector con IA: no está configurado; lee solo el de reglas.")]
    took = duration(_ms(trace, Step.IA) or ia.elapsed_ms)
    lines = [_ia_status(ia, took)]
    lines += [
        TraceLine(text=f"Descartado de la respuesta de la IA: {_error(d)}.", alert=True)
        for d in ia.dropped
    ]
    return lines


def _ia_status(ia: IAReading, took: str) -> TraceLine:
    found = _found(ia.output or ReaderOutput())
    match ia.status:
        case IAStatus.OK:
            return TraceLine(text=f"Lector con IA: respondió en {took} y {found}.")
        case IAStatus.REPAIRED:
            return TraceLine(
                text=f"Lector con IA: respondió en {took} y {found}. La respuesta vino "
                "con texto o comas de más y se reparó sin volver a pedirla.",
                alert=True,
            )
        case IAStatus.RETRIED:
            first = _error(ia.attempts[0].error) if ia.attempts else "respuesta inválida"
            return TraceLine(
                text=f"Lector con IA: respondió en {took}. El primer intento vino mal ({first}); "
                f"se le pidió corregir y el segundo intento fue válido: {found}.",
                alert=True,
            )
        case IAStatus.INVALID:
            return TraceLine(
                text=f"Lector con IA: los dos intentos vinieron mal ({_error(ia.error)}). "
                + _FALLBACK,
                alert=True,
            )
        case IAStatus.TIMEOUT:
            return TraceLine(
                text=f"Lector con IA: no respondió a tiempo ({_error(ia.error)}). " + _FALLBACK,
                alert=True,
            )
        case IAStatus.ERROR:
            return TraceLine(
                text=f"Lector con IA: falló el proveedor ({_error(ia.error)}). " + _FALLBACK,
                alert=True,
            )


def _evidence(trace: ReadingTrace) -> list[TraceLine]:
    if trace.ia is None or trace.ia.output is None:
        return []  # one lector only: it reads its own phrases, nothing to check against
    kept = trace.proposed - len(trace.discarded)
    head = f"Control de evidencia: {_count(kept, 'dato', 'datos')} con su frase en el relato"
    if not trace.discarded:
        return [TraceLine(text=f"{head}, ninguno descartado.")]
    discarded = "; ".join(_discarded(d) for d in trace.discarded)
    count = _count(len(trace.discarded), "descartado", "descartados")
    return [TraceLine(text=f"{head}, {count} ({discarded}).", alert=True)]


def _discarded(d: Discarded) -> str:
    return f"{dato_label(d.target)} del {_LECTOR[d.source]}: «{d.quote}» {d.reason}"


def _agreement(trace: ReadingTrace) -> list[TraceLine]:
    if trace.ia is None or trace.ia.output is None:
        return []
    lines: list[TraceLine] = []
    dropped = {d.target for d in trace.discarded}
    by_target = {d.target: d for d in trace.disagreements}
    tipo = by_target.pop("incident", None)
    if tipo is not None:
        lines.append(
            TraceLine(
                text=f"Los lectores no coinciden en el tipo: reglas {tipo.rules}, IA {tipo.ia}.",
                alert=True,
            )
        )
    elif trace.rules.incident and trace.ia.output.incident and "incident" not in dropped:
        lines.append(TraceLine(text="Los dos lectores coinciden en el tipo."))
    lines += [
        TraceLine(
            text=f"No coinciden en {dato_label(d.target)}: reglas {d.rules}, IA {d.ia}; "
            "queda a confirmar.",
            alert=True,
        )
        for d in by_target.values()
    ]
    if not by_target:
        lines.append(TraceLine(text="Ninguna señal en desacuerdo entre los dos lectores."))
    return lines


def _changes(trace: ReadingTrace) -> list[TraceLine]:
    by_kind: dict[ChangeKind, list[Change]] = {}
    for change in trace.changes:
        by_kind.setdefault(change.kind, []).append(change)
    lines = [
        _dato_change(trace, by_kind, ChangeKind.LOCATION, "Ubicación", "confirmada"),
        _dato_change(trace, by_kind, ChangeKind.INCIDENT, "Tipo", "confirmado"),
    ]
    lines += [
        TraceLine(text=f"Tipo en disputa ({c.after}): elige el operador.", alert=True)
        for c in by_kind.get(ChangeKind.TYPE_DISPUTE, [])
    ]
    lines += [
        TraceLine(text=f"Señal {c.label}: {_from_to(c)}{_quote(c)}.")
        for c in by_kind.get(ChangeKind.SIGNAL, [])
    ]
    lines += [
        TraceLine(text=f"Checklist: «{c.label}» pre-marcada en {c.after}{_quote(c, 'por')}.")
        for c in by_kind.get(ChangeKind.PREMARK, [])
    ]
    priority = by_kind.get(ChangeKind.PRIORITY)
    if priority:
        lines.append(TraceLine(text=f"Prioridad: {_from_to(priority[0])}."))
    elif trace.priority is not None:
        lines.append(TraceLine(text=f"Prioridad: sigue {trace.priority.value}."))
    else:
        lines.append(TraceLine(text="Prioridad: todavía sin calcular."))
    lines += [
        TraceLine(text=f"Aviso al operador: {c.after}", alert=True)
        for c in by_kind.get(ChangeKind.AVISO, [])
    ]
    return lines


def _dato_change(
    trace: ReadingTrace,
    by_kind: dict[ChangeKind, list[Change]],
    kind: ChangeKind,
    label: str,
    confirmed: str,
) -> TraceLine:
    changed = by_kind.get(kind)
    if changed:
        return TraceLine(text=f"{label}: {_from_to(changed[0])}{_quote(changed[0])}.")
    if kind.value in trace.confirmed:
        return TraceLine(text=f"{label}: sin cambios ({confirmed} por el operador, no se tocó).")
    return TraceLine(text=f"{label}: sin cambios.")


def _from_to(change: Change) -> str:
    return f"{change.before} → {change.after}" if change.before else f"{change.after}"


def _quote(change: Change, word: str = "") -> str:
    if not change.quote:
        return ""
    return f", {word} «{change.quote}»" if word else f" («{change.quote}»)"


def _found(output: ReaderOutput) -> str:
    parts = []
    if output.signals:
        parts.append(_count(len(output.signals), "señal", "señales"))
    if output.location is not None:
        parts.append("la ubicación")
    if output.incident is not None:
        parts.append("el tipo")
    if not parts:
        return "no encontró nada"
    found = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} y {parts[-1]}"
    return f"encontró {found}"


def _ms(trace: ReadingTrace, step: Step) -> float:
    return sum(s.ms for s in trace.steps if s.step is step)


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _error(error: str | None) -> str:
    return _shorten(error or "sin detalle", _MAX_ERROR)


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
