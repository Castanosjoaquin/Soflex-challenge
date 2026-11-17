"""Llamadas in memory, keyed by call_id, with lecturas serialized per llamada (SPEC §5.3)."""

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel

from app.calls.action_log import ActionLog, ActionRecord
from app.catalog.incidents import SUBTYPES, Subtype
from app.catalog.models import Category, Priority
from app.engine import state as engine
from app.engine.models import CallState, Line, Mode
from app.readers.rules.location import read_turn_location
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker, Turn


class ActionKind(StrEnum):
    CONFIRM_LOCATION = "confirm_location"
    CORRECT_LOCATION = "correct_location"
    CONFIRM_TYPE = "confirm_type"
    SET_PRIORITY = "set_priority"


class CallNotFoundError(LookupError):
    pass


class InvalidActionError(ValueError):
    """The action does not fit the llamada as it is now (e.g. nothing to confirm yet)."""


class InvalidActionValueError(ValueError):
    """The action itself is malformed: a missing motivo or an unknown value."""


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
            reading = self._reader.read(state.turns, state.line)
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
            state, target = self._apply(call.state, kind, value, reason)
            self._log.append(
                ActionRecord(
                    call_id=call_id,
                    at=datetime.now(UTC),
                    action=kind.value,
                    target=target,
                    before=_summary(call.state, target),
                    after=_summary(state, target),
                    reason=reason,
                )
            )
            call.state = state
            return state

    def _apply(
        self, state: CallState, kind: ActionKind, value: str | None, reason: str | None
    ) -> tuple[CallState, str]:
        match kind:
            case ActionKind.CONFIRM_LOCATION:
                if state.location is None:
                    raise InvalidActionError("Todavía no hay una ubicación para confirmar")
                return engine.confirm_location(state), "location"
            case ActionKind.CORRECT_LOCATION:
                return self._correct_location(state, value), "location"
            case ActionKind.CONFIRM_TYPE:
                category, subtype = _parse_type(value)
                if category is None and state.incident is None:
                    raise InvalidActionError("Todavía no hay un tipo para confirmar")
                return engine.confirm_type(state, category, subtype), "incident"
            case ActionKind.SET_PRIORITY:
                if not (reason or "").strip():
                    raise InvalidActionValueError("Cambiar la prioridad requiere un motivo")
                try:
                    level = Priority(value or "")
                except ValueError:
                    raise InvalidActionValueError(f"Prioridad desconocida: {value!r}") from None
                return engine.set_priority(state, level, reason or ""), "priority"

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


def _parse_type(value: str | None) -> tuple[Category | None, Subtype | None]:
    """`None` confirms the suggestion; `TIPO` or `TIPO:subtipo` sets it."""
    if not value:
        return None, None
    raw_category, _, raw_subtype = value.partition(":")
    try:
        category = Category(raw_category)
        subtype = Subtype(raw_subtype) if raw_subtype else None
    except ValueError:
        raise InvalidActionValueError(f"Tipo desconocido: {value!r}") from None
    if subtype is not None and SUBTYPES[subtype].category is not category:
        raise InvalidActionValueError(f"{subtype} no es un subtipo de {category}")
    return category, subtype


_SUMMARY_FIELDS: dict[str, set[str]] = {
    "location": {"street", "number", "cross_streets", "landmark", "confidence", "source"},
    "incident": {"category", "subtype", "confidence", "source"},
    "priority": {"level", "rule", "overridden_by_operator"},
}


def _summary(state: CallState, target: str) -> str | None:
    dato = getattr(state, target)
    if not isinstance(dato, BaseModel):
        return None
    return dato.model_dump_json(include=_SUMMARY_FIELDS[target])
