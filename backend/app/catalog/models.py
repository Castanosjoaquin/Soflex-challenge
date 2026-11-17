"""Reference catalog built from the provided synthetic dataset."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class Category(StrEnum):
    INCENDIO_RESCATE = "INCENDIO_RESCATE"
    EMERGENCIA_MEDICA = "EMERGENCIA_MEDICA"
    ACCIDENTE_VIAL = "ACCIDENTE_VIAL"
    DEFENSA_CIVIL = "DEFENSA_CIVIL"
    SERVICIOS_PUBLICOS = "SERVICIOS_PUBLICOS"
    CONVIVENCIA_SEGURIDAD = "CONVIVENCIA_SEGURIDAD"


class CatalogCase(BaseModel):
    """One documented incident from the dataset, normalized."""

    model_config = ConfigDict(frozen=True)

    id: str
    timestamp: str
    source: str
    category: Category
    subcategory: str
    priority: Priority
    transcript: str
    street: str
    street_number: str
    intersection: str
    neighborhood: str
    mandatory_questions: list[str] = Field(default_factory=list)
    answered_questions: list[str] = Field(default_factory=list)
    pending_questions: list[str] = Field(default_factory=list)
    prearrival_instructions: str
    detected_risks: str
    recommended_resources: str
    dispatch_notes: str
