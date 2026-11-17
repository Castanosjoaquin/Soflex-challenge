"""Llamadas in memory, keyed by call_id, with lecturas serialized per llamada (SPEC §5.3)."""

import asyncio
import json
import logging
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
from app.catalog.signals import SignalAnswer
from app.dispatch.store import DispatchStore
from app.engine import carta as cartas
from app.engine import merge
from app.engine import state as engine
from app.engine.contradictions import Resolution, UnknownAvisoError
from app.engine.models import Ampliacion, Aviso, CallState, Carta, Line, Mode
from app.readers.ia.reader import IAReader, IAReading
from app.readers.rules.location import read_turn_location
from app.readers.rules.reader import RulesReader
from app.trace import build as traces
from app.trace.models import ReadingTrace, Step
from app.trace.store import TraceStore
from app.transcript.models import Speaker, Turn

logger = logging.getLogger(__name__)


class ActionKind(StrEnum):
    CONFIRM_LOCATION = "confirm_location"
    CORRECT_LOCATION = "correct_location"
    CONFIRM_TYPE = "confirm_type"
    CHOOSE_TYPE = "choose_type"
    SET_PRIORITY = "set_priority"
    CONFIRM_PREMARK = "confirm_premark"
    ANSWER_QUESTION = "answer_question"
    SKIP_QUESTION = "skip_question"
    MARK_INSTRUCTION_READ = "mark_instruction_read"
    RESOLVE_CONTRADICTION = "resolve_contradiction"


class CallNotFoundError(LookupError):
    pass


class InvalidActionError(ValueError):
    """The action does not fit the llamada as it is now (e.g. nothing to confirm yet)."""


class InvalidActionValueError(ValueError):
    """The action itself is malformed: a missing motivo or an unknown value."""


class CannotDeriveError(ValueError):
    """Derivar is not possible yet (ubicación or tipo not confirmed) or was already done."""


@dataclass
class _Call:
    state: CallState
    opened_at: float
    # One lectura at a time per llamada: a turno that arrives mid-lectura waits its turn.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # The Carta as the despachador has it: as derivada plus every ampliación sent.
    sent: Carta | None = None


class CallService:
    def __init__(
        self,
        reader: RulesReader,
        log: ActionLog,
        dispatch: DispatchStore,
        traces: TraceStore,
        mode: Mode,
        clock: Callable[[], float] = time.monotonic,
        ia_reader: IAReader | None = None,
    ) -> None:
        """With an `ia_reader`, every lectura runs both lectores; without it, only the rules."""
        self._reader = reader
        self._ia_reader = ia_reader
        self._log = log
        self._dispatch = dispatch
        self._traces = traces
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
            at = datetime.now(UTC)
            at_ms = round((self._clock() - call.opened_at) * 1000)
            before, watch = call.state, traces.Stopwatch()
            with watch.step(Step.RELATO):
                turn = Turn(index=len(before.turns), at_ms=at_ms, speaker=speaker, text=text)
                state = engine.add_turn(before, turn)
            with watch.step(Step.REGLAS):
                rules = self._reader.read(state.turns, state.line)
            ia_reading: IAReading | None = None
            ia, mode = None, self._mode
            if self._ia_reader is not None:
                with watch.step(Step.IA):
                    ia_reading = await self._ia_reader.read(state.turns, state.line)
                if ia_reading.fell_back:
                    logger.warning("Lector con IA: %s (%s)", ia_reading.status, ia_reading.error)
                ia, mode = ia_reading.output, Mode.REGLAS if ia_reading.fell_back else Mode.IA
            with watch.step(Step.COMBINACION):
                state = state.model_copy(update={"mode": mode})
                call.state = merge.apply_readings(state, rules, ia)
            self._traces.append(
                traces.build(
                    index=turn.index + 1,
                    at=at,
                    turn=turn,
                    before=before,
                    after=call.state,
                    rules=rules,
                    ia=ia_reading,
                    steps=watch.steps,
                )
            )
            return call.state

    def readings(self, call_id: str) -> list[ReadingTrace]:
        """The trazas of a llamada, open or already closed; one per lectura, in order."""
        found = self._traces.for_call(call_id)
        if not found and call_id not in self._calls:
            raise CallNotFoundError(call_id)
        return found

    async def act(
        self,
        call_id: str,
        kind: ActionKind,
        value: str | None = None,
        reason: str | None = None,
        target: str | None = None,
    ) -> CallState:
        call = self._call(call_id)
        async with call.lock:
            state, target = self._apply(call.state, kind, value, reason, target)
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
            call.state = self._amplify(call, kind, state)
            return call.state

    async def derive(self, call_id: str) -> CallState:
        """Send the Carta to the bandeja del despachador. Etapa ④ is done."""
        call = self._call(call_id)
        async with call.lock:
            try:
                state = engine.derive(call.state)
            except engine.AlreadyDerivedError:
                raise CannotDeriveError("La Carta ya fue derivada") from None
            except engine.NotDerivableError:
                raise CannotDeriveError(
                    "Para derivar, confirmá la ubicación y el tipo de incidente"
                ) from None
            now = datetime.now(UTC)
            self._dispatch.add_carta(call_id, state.line, now, state.carta)
            self._log.append(
                ActionRecord(
                    call_id=call_id,
                    at=now,
                    action="derive",
                    target="carta",
                    after=state.carta.model_dump_json(),
                )
            )
            call.state, call.sent = state, state.carta
            return state

    async def close(self, call_id: str) -> None:
        """The llamada ends: its state leaves memory; the registro and the bandeja stay."""
        call = self._call(call_id)
        async with call.lock:
            self._log.append(
                ActionRecord(
                    call_id=call_id,
                    at=datetime.now(UTC),
                    action="close",
                    after=json.dumps({"derived": call.state.derived}),
                )
            )
            del self._calls[call_id]

    def _amplify(self, call: _Call, kind: ActionKind, state: CallState) -> CallState:
        """After derivar, what the operador confirms goes to the despachador as an ampliación."""
        if call.sent is None:
            return state
        changes = cartas.diff(call.sent, state.carta)
        if not changes:
            return state
        ampliacion = Ampliacion(at=datetime.now(UTC), action=kind.value, changes=changes)
        self._dispatch.add_ampliacion(state.call_id, ampliacion)
        self._log.append(
            ActionRecord(
                call_id=state.call_id,
                at=ampliacion.at,
                action="ampliacion",
                target=kind.value,
                after=json.dumps([c.model_dump() for c in changes], ensure_ascii=False),
            )
        )
        call.sent = state.carta
        return engine.add_ampliacion(state, ampliacion)

    def _apply(
        self,
        state: CallState,
        kind: ActionKind,
        value: str | None,
        reason: str | None,
        target: str | None,
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
            case ActionKind.CHOOSE_TYPE:
                category, _ = _parse_type(value)
                if category is None:
                    raise InvalidActionValueError("Falta el tipo elegido")
                try:
                    return merge.choose_type(state, category), "incident"
                except merge.NoTypeDisputeError:
                    raise InvalidActionError(f"{category} no es un tipo en disputa") from None
            case ActionKind.SET_PRIORITY:
                if not (reason or "").strip():
                    raise InvalidActionValueError("Cambiar la prioridad requiere un motivo")
                try:
                    level = Priority(value or "")
                except ValueError:
                    raise InvalidActionValueError(f"Prioridad desconocida: {value!r}") from None
                return engine.set_priority(state, level, reason or ""), "priority"
            case ActionKind.CONFIRM_PREMARK | ActionKind.ANSWER_QUESTION | ActionKind.SKIP_QUESTION:
                question_id = _question_target(target)
                return self._act_on_question(state, kind, question_id, value), question_id
            case ActionKind.MARK_INSTRUCTION_READ:
                instruction_id = _instruction_target(target)
                try:
                    return engine.mark_instruction_read(state, instruction_id), instruction_id
                except engine.UnknownInstructionError:
                    raise InvalidActionError(
                        f"La instrucción {instruction_id!r} no corresponde a esta llamada"
                    ) from None
            case ActionKind.RESOLVE_CONTRADICTION:
                aviso_id = _aviso_target(target)
                try:
                    resolved = engine.resolve_contradiction(
                        state, aviso_id, _parse_resolution(value)
                    )
                except UnknownAvisoError:
                    raise InvalidActionError(
                        f"El aviso {aviso_id!r} no existe o ya fue resuelto"
                    ) from None
                return resolved, aviso_id

    def _act_on_question(
        self, state: CallState, kind: ActionKind, question_id: str, value: str | None
    ) -> CallState:
        try:
            if kind is ActionKind.CONFIRM_PREMARK:
                return engine.confirm_premark(state, question_id)
            if kind is ActionKind.SKIP_QUESTION:
                return engine.skip_question(state, question_id)
            return engine.answer_question(state, question_id, _parse_answer(value))
        except engine.UnknownQuestionError:
            raise InvalidActionError(f"La pregunta {question_id!r} no está en juego") from None
        except engine.NoPremarkError:
            raise InvalidActionError(f"La pregunta {question_id!r} no tiene pre-marca") from None

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


def _question_target(target: str | None) -> str:
    if not (target or "").strip():
        raise InvalidActionValueError("Falta la pregunta (target)")
    return (target or "").strip()


def _instruction_target(target: str | None) -> str:
    if not (target or "").strip():
        raise InvalidActionValueError("Falta la instrucción (target)")
    return (target or "").strip()


def _aviso_target(target: str | None) -> str:
    if not (target or "").strip():
        raise InvalidActionValueError("Falta el aviso (target)")
    return (target or "").strip()


def _parse_resolution(value: str | None) -> Resolution:
    try:
        return Resolution(value or "")
    except ValueError:
        raise InvalidActionValueError(
            f"Resolución desconocida: {value!r} (aceptar|mantener)"
        ) from None


def _parse_answer(value: str | None) -> SignalAnswer:
    try:
        return SignalAnswer(value or "")
    except ValueError:
        raise InvalidActionValueError(f"Respuesta desconocida: {value!r} (si|no|no_sabe)") from None


_SUMMARY_FIELDS: dict[str, set[str]] = {
    "location": {"street", "number", "cross_streets", "landmark", "confidence", "source"},
    "incident": {"category", "subtype", "confidence", "source"},
    "priority": {"level", "rule", "overridden_by_operator"},
}


def _summary(state: CallState, target: str) -> str | None:
    for aviso in state.avisos:
        if aviso.id == target:
            return _aviso_summary(state, aviso)
    for item in state.instructions:
        if item.instruction_id == target:
            return item.model_dump_json(include={"read"})
    if target not in _SUMMARY_FIELDS:
        return _question_summary(state, target)
    dato = getattr(state, target)
    if not isinstance(dato, BaseModel):
        return None
    return dato.model_dump_json(include=_SUMMARY_FIELDS[target])


def _aviso_summary(state: CallState, aviso: Aviso) -> str:
    """The aviso's status and the dato it is about, as it stands."""
    if aviso.target in _SUMMARY_FIELDS:
        dato = _summary(state, aviso.target)
    else:
        signal = next((s for s in state.signals if s.signal_id.value == aviso.target), None)
        dato = signal.model_dump_json(include={"value", "confidence"}) if signal else None
    return json.dumps(
        {
            "aviso": aviso.text,
            "status": aviso.status.value,
            aviso.target: json.loads(dato) if dato else None,
        },
        ensure_ascii=False,
    )


def _question_summary(state: CallState, question_id: str) -> str:
    """Where a pregunta stands: its checklist item, or the señal and skip of the universal."""
    for item in state.checklist:
        if item.question_id == question_id:
            return item.model_dump_json(include={"status", "value", "source"})
    signal = next((s for s in state.signals if s.signal_id.value == question_id), None)
    return json.dumps(
        {
            "value": signal.value.value if signal else None,
            "source": signal.source.value if signal else None,
            "skipped": question_id in state.skipped_questions,
        }
    )
