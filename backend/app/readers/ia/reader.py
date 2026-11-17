"""The Lector con IA: ask, validate, repair, retry once, and give up to the rules (SPEC §5.3).

A lectura never raises: when the model does not give a valid answer in time, the result says why
and carries no output, and the llamada goes on with the Lector por reglas (modo `reglas`).
What happened (each attempt, its error, what was dropped) stays in the result, for the trazas.
"""

import asyncio
import time
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.engine.models import Line
from app.readers.ia import prompt
from app.readers.ia.provider import ProviderError
from app.readers.ia.schema import InvalidAnswerError, Parsed, parse, repair
from app.readers.models import ReaderOutput
from app.transcript.models import Turn


class Completer(Protocol):
    async def complete(self, messages: list[dict[str, str]]) -> str: ...


class IAStatus(StrEnum):
    OK = "ok"  # valid at the first try
    REPAIRED = "repaired"  # valid after the local repair
    RETRIED = "retried"  # valid after the one retry
    INVALID = "invalid"  # still invalid after the retry: fallback
    TIMEOUT = "timeout"  # past the timeout: fallback
    ERROR = "error"  # the proveedor failed (HTTP, network): fallback


class Attempt(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw: str
    error: str | None = None
    repaired: bool = False


class IAReading(BaseModel):
    """One lectura of the Lector con IA. `output` is None when it fell back to the rules."""

    model_config = ConfigDict(frozen=True)

    status: IAStatus
    output: ReaderOutput | None = None
    attempts: list[Attempt] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)  # datos out of the lists or without quote
    error: str | None = None
    elapsed_ms: int = 0

    @property
    def fell_back(self) -> bool:
        return self.output is None


class IAReader:
    def __init__(self, completer: Completer, timeout_seconds: float) -> None:
        self._completer = completer
        self._timeout = timeout_seconds

    async def read(self, turns: Sequence[Turn], line: Line | None = None) -> IAReading:
        attempts: list[Attempt] = []
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout):
                reading = await self._read(turns, line, attempts)
        except (TimeoutError, httpx.TimeoutException):
            reading = IAReading(
                status=IAStatus.TIMEOUT, error=f"Sin respuesta en {self._timeout:g} s"
            )
        except ProviderError as exc:
            reading = IAReading(status=IAStatus.ERROR, error=str(exc))
        elapsed = round((time.monotonic() - started) * 1000)
        return reading.model_copy(update={"attempts": attempts, "elapsed_ms": elapsed})

    async def _read(
        self, turns: Sequence[Turn], line: Line | None, attempts: list[Attempt]
    ) -> IAReading:
        messages = prompt.messages(turns, line)
        raw = await self._completer.complete(messages)
        parsed, error, repaired = _validate(raw)
        attempts.append(Attempt(raw=raw, error=error, repaired=repaired))
        if parsed is not None:
            status = IAStatus.REPAIRED if repaired else IAStatus.OK
            return _valid(status, parsed)

        retry = [
            *messages,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": prompt.retry_message(error or "")},
        ]
        raw = await self._completer.complete(retry)
        parsed, error, repaired = _validate(raw)
        attempts.append(Attempt(raw=raw, error=error, repaired=repaired))
        if parsed is not None:
            return _valid(IAStatus.RETRIED, parsed)
        return IAReading(status=IAStatus.INVALID, error=error)


def _valid(status: IAStatus, parsed: Parsed) -> IAReading:
    return IAReading(status=status, output=parsed.output, dropped=parsed.dropped)


def _validate(raw: str) -> tuple[Parsed | None, str | None, bool]:
    """The parsed answer, else the error; and whether the local repair was needed."""
    try:
        return parse(raw), None, False
    except InvalidAnswerError as exc:
        error = str(exc)
    fixed = repair(raw)
    if fixed is None or fixed == raw:
        return None, error, False
    try:
        return parse(fixed), None, True
    except InvalidAnswerError:
        return None, error, False
