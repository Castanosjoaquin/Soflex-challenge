"""The traza of one lectura (SPEC §5.11, DESIGN §9): what each step did and how long it took.

A traza is for the equipo técnico, not for the operador: it explains why the copiloto suggested
what it suggested. It is stored as the lectura ran and never edited.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.models import Priority
from app.engine.models import Mode, Source
from app.readers.ia.reader import IAReading
from app.readers.models import ReaderOutput
from app.transcript.models import Turn


class Step(StrEnum):
    RELATO = "relato"  # the turno joins the relato
    REGLAS = "reglas"  # Lector por reglas
    IA = "ia"  # Lector con IA, with its repair and retry
    COMBINACION = "combinacion"  # control de evidencia, both lectores as one, and the engine


class StepTime(BaseModel):
    model_config = ConfigDict(frozen=True)

    step: Step
    ms: float


class Discarded(BaseModel):
    """A dato a lector proposed and the control de evidencia dropped, with the reason."""

    model_config = ConfigDict(frozen=True)

    source: Source
    target: str  # "location", "incident" or a señal id
    quote: str
    reason: str


class Disagreement(BaseModel):
    """The two lectores read the same dato differently: a señal (sí against no) or the tipo."""

    model_config = ConfigDict(frozen=True)

    target: str  # "incident" or a señal id
    rules: str
    ia: str


class ChangeKind(StrEnum):
    LOCATION = "location"
    INCIDENT = "incident"
    TYPE_DISPUTE = "type_dispute"
    SIGNAL = "signal"
    PREMARK = "premark"
    PRIORITY = "priority"
    AVISO = "aviso"


class Change(BaseModel):
    """What the lectura changed in the llamada: a dato, the checklist, the prioridad, an aviso.

    `target` is the señal, pregunta clave or aviso id, or the kind itself for the rest;
    `before` is None for what is new.
    """

    model_config = ConfigDict(frozen=True)

    kind: ChangeKind
    target: str
    label: str
    before: str | None = None
    after: str | None = None
    quote: str | None = None


class ReadingTrace(BaseModel):
    """One lectura of a llamada, step by step."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    index: int  # 1 for the first lectura of the llamada
    at: datetime  # when the turno arrived
    turn: Turn  # the turno that triggered the lectura; its at_ms counts from the opening
    turns: int  # turnos in the relato
    mode: Mode
    steps: list[StepTime]
    rules: ReaderOutput
    ia: IAReading | None = None  # None in modo simulado
    # Control de evidencia: only when both lectores combine (the rules read their own phrases).
    proposed: int = 0
    discarded: list[Discarded] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    # How the llamada stands after the lectura: datos the operador confirmed, and the prioridad.
    confirmed: list[str] = Field(default_factory=list)  # "location", "incident"
    priority: Priority | None = None

    @property
    def total_ms(self) -> float:
        return sum(s.ms for s in self.steps)
