"""The Lector por reglas: always on, deterministic, and the whole lector in modo simulado."""

from collections.abc import Sequence

from app.engine.models import Line
from app.readers.models import ReaderOutput
from app.readers.rules.incident import read_incident
from app.readers.rules.location import read_location
from app.readers.rules.signals import read_signals
from app.transcript.models import Turn


class RulesReader:
    def read(self, turns: Sequence[Turn], line: Line | None = None) -> ReaderOutput:
        return ReaderOutput(
            location=read_location(turns),
            incident=read_incident(turns, line),
            signals=read_signals(turns),
        )
