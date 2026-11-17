"""Llamadas de demo extendidas (SPEC §5.1): multi-turno, with a pause before each turno.

They live as JSON in `data/demo_calls/` and are validated at startup: a broken file stops the
app with a message naming the file, instead of failing later in the middle of a replay.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.engine.models import Line
from app.transcript.models import ParsedTurn


class DemoTurn(ParsedTurn):
    """A turno of a demo call, with the pause before it during live replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    delay_ms: int = Field(ge=0, le=60_000)


class DemoCall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^DEMO-\d{2}$")
    line: Line
    title: str = Field(min_length=1)
    based_on: str = Field(description="The dataset case this call extends.")
    turns: list[DemoTurn] = Field(min_length=2)


class DemoCallsError(RuntimeError):
    """A demo call file is missing, unreadable or does not match the schema."""


def load_demo_calls(directory: Path, dataset_ids: set[str]) -> list[DemoCall]:
    """Read and validate every `*.json` in `directory`, ordered by file name."""
    if not directory.is_dir():
        raise DemoCallsError(f"No existe la carpeta de llamadas demo: {directory}")
    calls: list[DemoCall] = []
    for path in sorted(directory.glob("*.json")):
        try:
            call = DemoCall.model_validate_json(path.read_bytes())
        except ValidationError as exc:
            raise DemoCallsError(f"Llamada demo inválida en {path.name}:\n{exc}") from None
        if call.based_on not in dataset_ids:
            raise DemoCallsError(
                f"Llamada demo inválida en {path.name}: based_on {call.based_on!r} "
                "no es un caso del dataset"
            )
        if any(c.id == call.id for c in calls):
            raise DemoCallsError(f"Llamada demo inválida en {path.name}: id {call.id} repetido")
        calls.append(call)
    return calls
