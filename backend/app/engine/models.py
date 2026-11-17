"""State of a llamada as the copiloto understands it. Mirrored in frontend/src/api.ts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.incidents import Subtype
from app.catalog.models import Category, Priority
from app.catalog.signals import SignalAnswer, SignalId
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


class SignalValue(BaseModel):
    """What the llamada knows about one señal, and how sure it is."""

    model_config = ConfigDict(frozen=True)

    signal_id: SignalId
    value: SignalAnswer
    evidence: Evidence | None = None
    source: Source
    confidence: Confidence


class Incident(BaseModel):
    """Tipo and subtipo of the incidente, with the phrases that point to them."""

    model_config = ConfigDict(frozen=True)

    category: Category
    subtype: Subtype | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence
    source: Source


class PriorityReason(BaseModel):
    """One señal behind the prioridad, with the phrase that backs it."""

    model_config = ConfigDict(frozen=True)

    signal_id: SignalId
    value: SignalAnswer
    evidence: Evidence | None = None


class PriorityOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_level: Priority | None = None
    reason: str


class PriorityAssessment(BaseModel):
    """Prioridad and its porqué: the rule that fired and the señales behind it (SPEC §4)."""

    model_config = ConfigDict(frozen=True)

    level: Priority
    rule: str
    reasons: list[PriorityReason] = Field(default_factory=list)
    overridden_by_operator: PriorityOverride | None = None


class NextQuestion(BaseModel):
    """The one question the operador should ask now."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    signal_ids: list[SignalId] = Field(default_factory=list)


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
    sample_id: str | None = None
    turns: list[Turn] = Field(default_factory=list)
    location: Location | None = None
    incident: Incident | None = None
    signals: list[SignalValue] = Field(default_factory=list)
    priority: PriorityAssessment | None = None
    next_question: NextQuestion | None = None
    stages: list[Stage]
