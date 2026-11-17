"""The metrics of the evaluación (SPEC §8), as pure functions over the gold and what was read.

- **Calle**: the official name the copiloto reached against the official name of the CSV street.
- **Altura**: the number read against the CSV altura when it is a plain number. An altura with a
  note ("4500 (esquina)", "Km 7 (altura Parque Norte)", "S/N (…)") is never said in the relato
  (EDA §7): the gold there is "no altura", and reading none is the hit.
- **Pre-marcas**: per mandatoria of the manual annotation that a señal of the catalog answers,
  whether the copiloto knows that señal (pre-marked) against whether the relato answers it
  (annotated A or P). Mandatorias no señal answers cannot be pre-marked and stay out.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.catalog.signals import SignalAnswer, SignalId
from app.catalog.streets import match_street
from app.engine.models import CallState
from app.readers.models import ReaderOutput
from app.transcript.text import fold


@dataclass(frozen=True)
class Rate:
    hits: int
    total: int

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None

    def __add__(self, other: "Rate") -> "Rate":
        return Rate(self.hits + other.hits, self.total + other.total)


def rate(hits: Iterable[bool]) -> Rate:
    flags = list(hits)
    return Rate(sum(flags), len(flags))


# --- Ubicación -----------------------------------------------------------------------------------

_NOTE = re.compile(r"\s*\(.*?\)")


def gold_street(csv_street: str) -> str:
    """The official name of the CSV street, or the street itself, folded, when it is not in the
    list ("Carlos Pellegrini (Andén Subte Línea B)" keeps only the street)."""
    name = _NOTE.sub("", csv_street).strip()
    match = match_street(name)
    return match.official if match else fold(name)


def gold_altura(csv_altura: str) -> int | None:
    """The altura the relato says: the CSV value when it is a plain number, else None."""
    value = csv_altura.strip()
    return int(value) if value.isdigit() else None


def read_street(state: CallState) -> str | None:
    location = state.location
    if location is None or location.street is None:
        return None
    return location.street_official or fold(location.street)


def read_altura(state: CallState) -> int | None:
    location = state.location
    return location.number.value if location and location.number else None


# --- Pre-marcas ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Mandatoria:
    """A mandatoria of the dataset, as annotated by hand, and the señales that answer it."""

    case_id: str
    text: str
    answered: bool  # the relato answers it, at least implicitly (A or P)
    signal_ids: tuple[SignalId, ...]


@dataclass(frozen=True)
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def __add__(self, other: "Confusion") -> "Confusion":
        return Confusion(
            self.tp + other.tp, self.fp + other.fp, self.fn + other.fn, self.tn + other.tn
        )

    @property
    def precision(self) -> Rate:
        return Rate(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> Rate:
        return Rate(self.tp, self.tp + self.fn)


def known_signals(state: CallState) -> set[SignalId]:
    """The señales the llamada has a value for: each one pre-marks the questions tied to it."""
    return {s.signal_id for s in state.signals if s.value is not SignalAnswer.NO_SABE}


def premark_confusion(mandatorias: Sequence[Mandatoria], known: set[SignalId]) -> Confusion:
    total = Confusion()
    for m in mandatorias:
        if not m.signal_ids:
            continue
        marked = any(s in known for s in m.signal_ids)
        total += Confusion(
            tp=int(marked and m.answered),
            fp=int(marked and not m.answered),
            fn=int(not marked and m.answered),
            tn=int(not marked and not m.answered),
        )
    return total


# --- Lecturas ------------------------------------------------------------------------------------


def datos(output: ReaderOutput) -> int:
    """How many datos a lectura proposes: the ubicación, the tipo and each señal."""
    return (output.location is not None) + (output.incident is not None) + len(output.signals)
