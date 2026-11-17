"""Relato building blocks: who speaks and what they said."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Speaker(StrEnum):
    OPERADOR = "operador"
    LLAMANTE = "llamante"


class ParsedTurn(BaseModel):
    """A turno as it comes out of a raw transcript, before it joins a llamada."""

    model_config = ConfigDict(frozen=True)

    speaker: Speaker
    text: str


class Turn(ParsedTurn):
    """A turno inside a llamada: position in the relato and arrival time."""

    index: int
    at_ms: int
