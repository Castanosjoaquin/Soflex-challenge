"""The Lector por reglas: always on, deterministic, and the whole lector in modo simulado."""

from collections.abc import Sequence

from app.readers.models import ReaderOutput
from app.readers.rules.location import read_location
from app.transcript.models import Turn


class RulesReader:
    def read(self, turns: Sequence[Turn]) -> ReaderOutput:
        return ReaderOutput(location=read_location(turns))
