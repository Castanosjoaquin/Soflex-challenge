"""Números generales (SPEC §5.11, DESIGN §9), counted on demand from the trazas and the registro.

Nothing here keeps a counter of its own: every number is recomputed from what was stored, so it
can never disagree with the trazas or with the registro de acciones.

- Latencias, respuestas rotas, fallbacks, descartes and desacuerdos come from the trazas.
- Pre-marcas confirmadas vs. corregidas come from the registro: a `confirm_premark`, or an
  `answer_question` over a pre-marcada (same value: confirmed; another value: corrected).
- Tiempo hasta derivar: from the opening of the llamada (the first traza's `at` minus its
  turno's `at_ms`, which counts from the opening) to the `derive` record.
"""

import json
import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from app.calls.action_log import ActionRecord
from app.catalog.questions import KEY_QUESTIONS
from app.readers.ia.reader import IAStatus
from app.trace.models import ReadingTrace, Step

_FALLBACK = (IAStatus.INVALID, IAStatus.TIMEOUT, IAStatus.ERROR)


class Stats(BaseModel):
    """Count and spread of a set of durations, in the unit the field name says."""

    model_config = ConfigDict(frozen=True)

    count: int = 0
    mean: float | None = None
    p50: float | None = None
    p95: float | None = None
    max: float | None = None


class IAMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    readings: int = 0  # lecturas where the Lector con IA ran
    by_status: dict[IAStatus, int] = Field(default_factory=dict)
    # Answers that came out of the model unusable as they were: invalid or in need of repair.
    broken_answers: int = 0
    fallbacks: int = 0  # lecturas that stayed with the rules only
    dropped: int = 0  # datos out of the lists or without a quote, dropped from valid answers


class Disagreements(BaseModel):
    model_config = ConfigDict(frozen=True)

    tipo: int = 0
    signals: int = 0


class PremarkCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    text: str
    confirmed: int = 0
    corrected: int = 0


class Metrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    calls: int  # llamadas with at least one lectura
    readings: int
    latency_ms: dict[str, Stats]  # by step (relato, reglas, ia, combinacion) and "total"
    ia: IAMetrics
    discarded_without_evidence: int
    disagreements: Disagreements
    premarks: list[PremarkCount]
    time_to_derive_s: Stats


def compute(traces: Sequence[ReadingTrace], records: Sequence[ActionRecord]) -> Metrics:
    return Metrics(
        calls=len({t.call_id for t in traces}),
        readings=len(traces),
        latency_ms=_latencies(traces),
        ia=_ia(traces),
        discarded_without_evidence=sum(len(t.discarded) for t in traces),
        disagreements=Disagreements(
            tipo=sum(1 for t in traces for d in t.disagreements if d.target == "incident"),
            signals=sum(1 for t in traces for d in t.disagreements if d.target != "incident"),
        ),
        premarks=_premarks(records),
        time_to_derive_s=stats(_times_to_derive(traces, records)),
    )


def stats(values: Sequence[float]) -> Stats:
    if not values:
        return Stats()
    ordered = sorted(values)
    return Stats(
        count=len(ordered),
        mean=round(sum(ordered) / len(ordered), 1),
        p50=_percentile(ordered, 50),
        p95=_percentile(ordered, 95),
        max=ordered[-1],
    )


def _percentile(ordered: Sequence[float], p: int) -> float:
    """Nearest rank: the smallest value with at least p% of the values at or below it."""
    return ordered[max(math.ceil(p / 100 * len(ordered)) - 1, 0)]


def _latencies(traces: Sequence[ReadingTrace]) -> dict[str, Stats]:
    by_step: dict[str, list[float]] = {s.value: [] for s in Step}
    for trace in traces:
        for step in trace.steps:
            by_step[step.step.value].append(step.ms)
    latencies = {name: stats(values) for name, values in by_step.items()}
    latencies["total"] = stats([round(t.total_ms, 1) for t in traces])
    return latencies


def _ia(traces: Sequence[ReadingTrace]) -> IAMetrics:
    readings = [t.ia for t in traces if t.ia is not None]
    by_status: dict[IAStatus, int] = {}
    for reading in readings:
        by_status[reading.status] = by_status.get(reading.status, 0) + 1
    return IAMetrics(
        readings=len(readings),
        by_status=by_status,
        broken_answers=sum(
            1 for r in readings for a in r.attempts if a.error is not None or a.repaired
        ),
        fallbacks=sum(1 for r in readings if r.status in _FALLBACK),
        dropped=sum(len(r.dropped) for r in readings),
    )


def _premarks(records: Sequence[ActionRecord]) -> list[PremarkCount]:
    counts: dict[str, PremarkCount] = {}
    for record in records:
        if record.action not in ("confirm_premark", "answer_question") or not record.target:
            continue
        before = _json(record.before)
        if before.get("status") != "pre_marcada":
            continue
        after = _json(record.after)
        corrected = record.action == "answer_question" and after.get("value") != before.get("value")
        question_id = record.target
        question = KEY_QUESTIONS.get(question_id)
        count = counts.get(question_id) or PremarkCount(
            question_id=question_id, text=question.text if question else question_id
        )
        counts[question_id] = count.model_copy(
            update={
                "confirmed": count.confirmed + (not corrected),
                "corrected": count.corrected + corrected,
            }
        )
    return sorted(counts.values(), key=lambda c: c.question_id)


def _times_to_derive(
    traces: Sequence[ReadingTrace], records: Sequence[ActionRecord]
) -> list[float]:
    opened: dict[str, datetime] = {}
    for trace in traces:
        if trace.call_id not in opened:
            opened[trace.call_id] = trace.at - timedelta(milliseconds=trace.turn.at_ms)
    return [
        round((r.at - opened[r.call_id]).total_seconds(), 1)
        for r in records
        if r.action == "derive" and r.call_id in opened
    ]


def _json(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
