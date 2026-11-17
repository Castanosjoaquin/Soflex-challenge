"""Llamadas in memory, keyed by call_id, with lecturas serialized per llamada (SPEC §5.3)."""

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.calls.action_log import ActionLog, ActionRecord
from app.engine import state as engine
from app.engine.models import CallState, Line, Location, Mode
from app.readers.rules.location import read_turn_location
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn


class ActionKind(StrEnum):
    CONFIRM_LOCATION = "confirm_location"
    CORRECT_LOCATION = "correct_location"


class CallNotFoundError(LookupError):
    pass


class InvalidActionError(ValueError):
    pass


@dataclass
class _Call:
    state: CallState
    opened_at: float
    # One lectura at a time per llamada: a turno that arrives mid-lectura waits its turn.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class CallService:
    def __init__(
        self,
        reader: RulesReader,
        log: ActionLog,
        mode: Mode,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._reader = reader
        self._log = log
        self._mode = mode
        self._clock = clock
        self._calls: dict[str, _Call] = {}

    def open(self, line: Line, sample_id: str | None = None) -> CallState:
        call_id = uuid.uuid4().hex[:12]
        state = engine.new_call(call_id, line, self._mode, sample_id=sample_id)
        self._calls[call_id] = _Call(state=state, opened_at=self._clock())
        return state

    def get(self, call_id: str) -> CallState:
        return self._call(call_id).state

    async def add_turn(self, call_id: str, speaker: Speaker, text: str) -> CallState:
        call = self._call(call_id)
        async with call.lock:
            at_ms = round((self._clock() - call.opened_at) * 1000)
            turn = Turn(index=len(call.state.turns), at_ms=at_ms, speaker=speaker, text=text)
            state = engine.add_turn(call.state, turn)
            reading = self._reader.read(state.turns)
            call.state = engine.apply_reading(state, reading)
            return call.state

    async def act(
        self,
        call_id: str,
        kind: ActionKind,
        value: str | None = None,
        reason: str | None = None,
    ) -> CallState:
        call = self._call(call_id)
        async with call.lock:
            before = call.state.location
            match kind:
                case ActionKind.CONFIRM_LOCATION:
                    if before is None:
                        raise InvalidActionError("Todavía no hay una ubicación para confirmar")
                    state = engine.confirm_location(call.state)
                case ActionKind.CORRECT_LOCATION:
                    state = self._correct_location(call.state, value)
            self._log.append(
                ActionRecord(
                    call_id=call_id,
                    at=datetime.now(UTC),
                    action=kind.value,
                    target="location",
                    before=_summary(before),
                    after=_summary(state.location),
                    reason=reason,
                )
            )
            call.state = state
            return state

    def _correct_location(self, state: CallState, value: str | None) -> CallState:
        text = (value or "").strip()
        if not text:
            raise InvalidActionError("Falta la dirección corregida")
        # The operador types a dirección; read it with the same patterns as the relato.
        parsed = read_turn_location(Turn(index=-1, at_ms=0, speaker=Speaker.LLAMANTE, text=text))
        if parsed is None or parsed.street is None:
            return engine.correct_location(state, street=text, number=None, cross_streets=[])
        return engine.correct_location(
            state, street=parsed.street, number=parsed.number, cross_streets=parsed.cross_streets
        )

    def _call(self, call_id: str) -> _Call:
        try:
            return self._calls[call_id]
        except KeyError:
            raise CallNotFoundError(call_id) from None


def _summary(location: Location | None) -> str | None:
    if location is None:
        return None
    return location.model_dump_json(
        include={"street", "number", "cross_streets", "landmark", "confidence", "source"}
    )
