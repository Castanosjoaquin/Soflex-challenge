"""What a lector returns. Both lectores (reglas and IA) produce the same `ReaderOutput`."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.incidents import Subtype
from app.catalog.models import Category
from app.catalog.signals import SignalAnswer, SignalId


class Evidence(BaseModel):
    """A verbatim phrase of the relato, located by offsets on the original turno text."""

    model_config = ConfigDict(frozen=True)

    turn_index: int
    start: int
    end: int
    quote: str


class NumberKind(StrEnum):
    EXACTA = "exacta"  # "Corrientes 1540"
    AL = "al"  # "Scalabrini Ortiz al 800": a rounded block, not a door number
    ESQUINA = "esquina"  # "San Juan y Entre Ríos": an intersection, no number
    KM = "km"  # highways
    SN = "sn"  # "sin número"


class StreetNumber(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: int | None = None
    kind: NumberKind


class LocationReading(BaseModel):
    """The ubicación as the llamante said it, split into parts, with its evidence."""

    model_config = ConfigDict(frozen=True)

    said: str
    evidence: list[Evidence]
    street: str | None = None
    number: StreetNumber | None = None
    cross_streets: list[str] = Field(default_factory=list)
    landmark: str | None = None


class SignalReading(BaseModel):
    """A señal of the catalog the relato affirms, denies or leaves open, with its evidence."""

    model_config = ConfigDict(frozen=True)

    signal_id: SignalId
    value: SignalAnswer
    evidence: Evidence


class IncidentReading(BaseModel):
    """The tipo and subtipo the relato points to, with the phrases that point there.

    `runner_up` is set when another tipo came close: the lector is not sure which one it is.
    """

    model_config = ConfigDict(frozen=True)

    category: Category
    subtype: Subtype | None = None
    evidence: list[Evidence]
    runner_up: Category | None = None


class ReaderOutput(BaseModel):
    """One lectura of the whole relato."""

    model_config = ConfigDict(frozen=True)

    location: LocationReading | None = None
    incident: IncidentReading | None = None
    signals: list[SignalReading] = Field(default_factory=list)
