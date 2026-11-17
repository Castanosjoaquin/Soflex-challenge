"""State of a llamada as the copiloto understands it. Mirrored in frontend/src/api.ts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.readers.models import Evidence, StreetNumber
from app.transcript.models import Turn


class Line(StrEnum):
    L911 = "911"
    L107 = "107"
    L103 = "103"
    L147 = "147"
    APP = "app"


class Mode(StrEnum):
    IA = "ia"
    REGLAS = "reglas"
    SIMULADO = "simulado"


class Confidence(StrEnum):
    CONFIRMADO = "confirmado"  # validated by the operador
    PROBABLE = "probable"  # verified evidence and nothing contradicts it
    A_CONFIRMAR = "a_confirmar"  # not enough backing


class Source(StrEnum):
    REGLAS = "reglas"
    IA = "ia"
    OPERADOR = "operador"


class Location(BaseModel):
    """Ubicación: what the llamante said and the dirección it points to."""

    model_config = ConfigDict(frozen=True)

    said: str
    evidence: list[Evidence] = Field(default_factory=list)
    street: str | None = None
    street_official: str | None = None  # filled by the official street matcher (SPEC §5.5)
    number: StreetNumber | None = None
    cross_streets: list[str] = Field(default_factory=list)
    landmark: str | None = None
    candidates: list[str] = Field(default_factory=list)
    confidence: Confidence
    source: Source


class StageId(StrEnum):
    UBICAR = "ubicar"
    QUE_PASA = "que_pasa"
    PREGUNTAS = "preguntas"
    DERIVAR = "derivar"
    INSTRUCCIONES = "instrucciones"


class StageStatus(StrEnum):
    HECHA = "hecha"
    ACTUAL = "actual"
    PENDIENTE = "pendiente"


class Stage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: StageId
    status: StageStatus


class CallState(BaseModel):
    model_config = ConfigDict(frozen=True)

    call_id: str
    line: Line
    mode: Mode
    turns: list[Turn] = Field(default_factory=list)
    location: Location | None = None
    stages: list[Stage]
