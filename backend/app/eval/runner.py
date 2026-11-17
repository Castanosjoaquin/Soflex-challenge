"""Replay each llamada of the corpus through the lectores and the engine, as the API does.

A lectura runs after each llamante turno (the operador's turnos bring no dato of the llamante),
with the Lector por reglas alone in modo simulado or next to the Lector con IA, combined by
`merge.apply_readings` (SPEC §5.4). No operador acts: what is measured is what the copiloto
suggests from the relato alone.
"""

import asyncio
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from app.engine import merge
from app.engine.models import CallState, Mode
from app.engine.state import add_turn, new_call
from app.eval.corpus import EvalCall
from app.eval.metrics import (
    Confusion,
    datos,
    known_signals,
    premark_confusion,
    read_altura,
    read_street,
)
from app.readers.ia.reader import IAReader, IAStatus
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn

_BROKEN = {IAStatus.REPAIRED, IAStatus.RETRIED, IAStatus.INVALID}


class Outcome(BaseModel):
    """What the copiloto made of one llamada of the corpus, against its gold."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    variant: str
    applied: bool
    street: str | None
    street_ok: bool
    altura: int | None
    altura_ok: bool
    category: str | None
    category_ok: bool
    priority: str | None
    priority_ok: bool
    premarks: tuple[int, int, int, int]  # tp, fp, fn, tn
    # Datos the lector proposed and the ones dropped (no evidence in the relato, or off the lists).
    proposed: int = 0
    discarded: int = 0
    lecturas: int = 0
    broken: int = 0  # IA answers not valid as they came (repaired, retried or given up)
    fallbacks: int = 0  # IA lecturas that ended with the rules alone

    @property
    def confusion(self) -> Confusion:
        return Confusion(*self.premarks)


async def run_call(call: EvalCall, rules: RulesReader, ia: IAReader | None) -> Outcome:
    state = new_call(call.case_id, call.line, Mode.SIMULADO if ia is None else Mode.IA)
    proposed = discarded = lecturas = broken = fallbacks = 0
    for i, parsed in enumerate(call.turns):
        state = add_turn(state, Turn(index=i, at_ms=0, speaker=parsed.speaker, text=parsed.text))
        if parsed.speaker is not Speaker.LLAMANTE:
            continue
        lecturas += 1
        by_rules = rules.read(state.turns, state.line)
        by_ia, mode = None, state.mode
        if ia is None:
            proposed += datos(by_rules)
            discarded += datos(by_rules) - datos(merge.verified(by_rules, state.turns))
        else:
            reading = await ia.read(state.turns, state.line)
            by_ia = reading.output
            broken += reading.status in _BROKEN
            fallbacks += reading.fell_back
            mode = Mode.REGLAS if reading.fell_back else Mode.IA
            if by_ia is not None:
                kept = datos(merge.verified(by_ia, state.turns))
                proposed += datos(by_ia) + len(reading.dropped)
                discarded += datos(by_ia) - kept + len(reading.dropped)
        state = merge.apply_readings(state.model_copy(update={"mode": mode}), by_rules, by_ia)
    return _outcome(call, state).model_copy(
        update={
            "proposed": proposed,
            "discarded": discarded,
            "lecturas": lecturas,
            "broken": broken,
            "fallbacks": fallbacks,
        }
    )


def _outcome(call: EvalCall, state: CallState) -> Outcome:
    street, altura = read_street(state), read_altura(state)
    category = state.incident.category if state.incident else None
    priority = state.priority.level if state.priority else None
    confusion = premark_confusion(call.mandatorias, known_signals(state))
    return Outcome(
        case_id=call.case_id,
        variant=call.variant,
        applied=call.applied,
        street=street,
        street_ok=street == call.street,
        altura=altura,
        altura_ok=altura == call.altura,
        category=category.value if category else None,
        category_ok=category is call.category,
        priority=priority.value if priority else None,
        priority_ok=priority is call.priority,
        premarks=(confusion.tp, confusion.fp, confusion.fn, confusion.tn),
    )


async def run_corpus(
    calls: Sequence[EvalCall], ia: IAReader | None = None, concurrency: int = 4
) -> list[Outcome]:
    """Every llamada of the corpus, in order. With the IA, a few llamadas at a time."""
    rules = RulesReader()
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(call: EvalCall) -> Outcome:
        async with gate:
            return await run_call(call, rules, ia)

    return list(await asyncio.gather(*(one(c) for c in calls)))
