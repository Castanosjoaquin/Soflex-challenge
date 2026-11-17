"""The corpus of the evaluación: the 30 dataset llamadas as they are and their variantes ruidosas,
each with its gold (SPEC §8).

Gold: the CSV columns for tipo, prioridad, calle and altura; the manual annotation of the 90
mandatorias (``data/eval/mandatorias_anotacion_manual.csv``) for the pre-marcas, with the señal
that answers each one (``data/eval/mandatorias_senales.csv``, empty when no señal does).
A variante ``sin_direccion`` has no calle nor altura to read: its gold is "none".
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from app.api import _LINE_BY_SOURCE
from app.catalog.loader import parse_dataset
from app.catalog.models import CatalogCase, Category, Priority
from app.catalog.signals import SignalId
from app.config import REPO_ROOT
from app.engine.models import Line
from app.eval.metrics import Mandatoria, gold_altura, gold_street
from app.eval.noise import NOISY_DIR, NoiseKind, load_variants
from app.transcript.models import ParsedTurn
from app.transcript.parser import parse_transcript

DATASET = REPO_ROOT / "data" / "dataset_challenge_soflex.csv"
EVAL_DIR = REPO_ROOT / "data" / "eval"
ORIGINAL = "original"


@dataclass(frozen=True)
class EvalCall:
    case_id: str
    variant: str  # "original" or a NoiseKind
    applied: bool  # False when the noise found nothing to change
    line: Line
    turns: list[ParsedTurn]
    street: str | None  # official name; None when the relato says no street
    altura: int | None
    category: Category
    priority: Priority
    mandatorias: tuple[Mandatoria, ...]


class CorpusError(RuntimeError):
    """The gold files do not match the dataset or each other."""


def load_mandatorias(eval_dir: Path = EVAL_DIR) -> dict[str, tuple[Mandatoria, ...]]:
    """The annotated mandatorias per case (by the dataset id's last three digits)."""
    annotation = _rows(eval_dir / "mandatorias_anotacion_manual.csv")
    signals = _rows(eval_dir / "mandatorias_senales.csv")
    if [(r["id"], r["mandatoria"]) for r in annotation] != [
        (r["id"], r["mandatoria"]) for r in signals
    ]:
        raise CorpusError("mandatorias_senales.csv no sigue a la anotación manual fila por fila")
    by_case: dict[str, list[Mandatoria]] = {}
    for note, link in zip(annotation, signals, strict=True):
        if note["estado_manual"] not in {"A", "P", "N"}:
            raise CorpusError(f"Estado desconocido en la anotación: {note['estado_manual']!r}")
        by_case.setdefault(note["id"], []).append(
            Mandatoria(
                case_id=note["id"],
                text=note["mandatoria"],
                answered=note["estado_manual"] in {"A", "P"},
                signal_ids=tuple(SignalId(s) for s in link["signal_ids"].split("|") if s),
            )
        )
    return {case: tuple(items) for case, items in by_case.items()}


def load_corpus(
    dataset: Path = DATASET, eval_dir: Path = EVAL_DIR, noisy_dir: Path = NOISY_DIR
) -> list[EvalCall]:
    """Every dataset llamada as it is, then its variantes ruidosas, kind by kind."""
    cases = {c.id: c for c in parse_dataset(dataset)}
    mandatorias = load_mandatorias(eval_dir)
    calls = [
        _call(case, ORIGINAL, True, parse_transcript(case.transcript), mandatorias)
        for case in cases.values()
    ]
    for kind in NoiseKind:
        for variant in load_variants(kind, noisy_dir):
            if variant.case_id not in cases:
                raise CorpusError(f"{kind}: {variant.case_id} no es un caso del dataset")
            case = cases[variant.case_id]
            calls.append(_call(case, kind.value, variant.applied, variant.turns, mandatorias))
    return calls


def _call(
    case: CatalogCase,
    variant: str,
    applied: bool,
    turns: list[ParsedTurn],
    mandatorias: dict[str, tuple[Mandatoria, ...]],
) -> EvalCall:
    says_location = variant == ORIGINAL or NoiseKind(variant).keeps_location
    return EvalCall(
        case_id=case.id,
        variant=variant,
        applied=applied,
        line=_LINE_BY_SOURCE.get(case.source, Line.L911),
        turns=turns,
        street=gold_street(case.street) if says_location else None,
        altura=gold_altura(case.street_number) if says_location else None,
        category=case.category,
        priority=case.priority,
        mandatorias=mandatorias.get(case.id[-3:], ()),
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
