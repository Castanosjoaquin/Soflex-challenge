"""Números generales (SPEC §5.11): counted from the trazas and the registro, nothing else."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.calls.action_log import ActionLog, ActionRecord
from app.engine.models import Line, Mode
from app.readers.ia.reader import IAStatus
from app.readers.models import ReaderOutput
from app.trace import metrics
from app.trace.models import ReadingTrace, Step, StepTime
from app.trace.store import TraceStore
from app.transcript.models import Speaker, Turn
from tests.test_ia_combination import DERRUMBE, INCENDIO, PIZZERIA, POZO, service
from tests.test_traces import INVENTED

CASE_001 = "SFX-REC-2026-001"


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _replay(client: TestClient, sample_id: str) -> dict[str, Any]:
    sample = client.get(f"/api/samples/{sample_id}").json()
    state = _ok(client.post("/api/calls", json={"line": sample["line"], "sample_id": sample_id}))
    for turn in sample["turns"]:
        state = _ok(client.post(f"/api/calls/{state['call_id']}/turns", json=turn))
    return state


def test_without_llamadas_everything_is_zero(client: TestClient) -> None:
    body = _ok(client.get("/api/metrics"))
    assert (body["calls"], body["readings"], body["discarded_without_evidence"]) == (0, 0, 0)
    assert body["ia"]["readings"] == 0
    assert body["premarks"] == []
    assert body["time_to_derive_s"] == {
        "count": 0,
        "mean": None,
        "p50": None,
        "p95": None,
        "max": None,
    }


def test_mock_mode_metrics_from_a_derived_llamada(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    act = f"/api/calls/{call_id}/actions"
    _ok(client.post(act, json={"kind": "confirm_premark", "target": "inc_atrapados"}))
    # Answering a pre-marca with another value is correcting it.
    _ok(client.post(act, json={"kind": "answer_question", "target": "inc_evacuado", "value": "no"}))
    _ok(client.post(act, json={"kind": "confirm_location"}))
    _ok(client.post(act, json={"kind": "confirm_type"}))
    _ok(client.post(f"/api/calls/{call_id}/derive"))

    body = _ok(client.get("/api/metrics"))
    assert (body["calls"], body["readings"]) == (1, len(state["turns"]))
    assert body["latency_ms"]["reglas"]["count"] == len(state["turns"])
    assert body["latency_ms"]["total"]["count"] == len(state["turns"])
    assert body["latency_ms"]["ia"]["count"] == 0  # modo simulado: the IA never ran
    assert body["ia"]["readings"] == 0
    assert body["premarks"] == [
        {
            "question_id": "inc_atrapados",
            "text": "¿Hay personas atrapadas o adentro?",
            "confirmed": 1,
            "corrected": 0,
        },
        {
            "question_id": "inc_evacuado",
            "text": "¿Evacuaron el lugar?",
            "confirmed": 0,
            "corrected": 1,
        },
    ]
    derive = body["time_to_derive_s"]
    assert derive["count"] == 1 and 0 <= derive["max"] < 60


def test_ia_metrics_count_broken_answers_fallbacks_discards_and_disagreements(
    tmp_path: Path,
) -> None:
    disagreeing = {
        "incident": INCENDIO,
        "signals": [
            {
                "id": "persona_atrapada",
                "value": "no",
                "quote": "la gente salió corriendo a la calle",
            }
        ],
    }
    for replies, text, line in (
        (["esto no es JSON", INVENTED], PIZZERIA, Line.L911),  # retried, 2 discarded
        (["roto", "roto otra vez"], PIZZERIA, Line.L911),  # invalid: fallback
        ([disagreeing], PIZZERIA, Line.L911),  # ok, a señal en desacuerdo
        ([{"incident": DERRUMBE}], POZO, Line.L147),  # ok, tipo en disputa
    ):
        svc = service(tmp_path, replies)
        call_id = svc.open(line).call_id
        asyncio.run(svc.add_turn(call_id, Speaker.LLAMANTE, text))

    db = tmp_path / "log.db"
    counted = metrics.compute(TraceStore(db).all(), ActionLog(db).all())
    assert (counted.calls, counted.readings) == (4, 4)
    assert counted.ia.readings == 4
    assert counted.ia.by_status == {IAStatus.RETRIED: 1, IAStatus.INVALID: 1, IAStatus.OK: 2}
    assert counted.ia.broken_answers == 3  # the first try of the retry and both invalid ones
    assert counted.ia.fallbacks == 1
    assert counted.discarded_without_evidence == 2
    assert (counted.disagreements.tipo, counted.disagreements.signals) == (1, 1)
    assert counted.latency_ms["ia"].count == 4


def _trace(call_id: str, at: datetime, at_ms: int) -> ReadingTrace:
    return ReadingTrace(
        call_id=call_id,
        index=1,
        at=at,
        turn=Turn(index=0, at_ms=at_ms, speaker=Speaker.LLAMANTE, text="Hola"),
        turns=1,
        mode=Mode.SIMULADO,
        steps=[StepTime(step=Step.REGLAS, ms=4.0), StepTime(step=Step.COMBINACION, ms=2.0)],
        rules=ReaderOutput(),
    )


def test_time_to_derive_counts_from_the_opening_of_the_llamada() -> None:
    # The first turno came 5 s after the opening (10:00:00); derivada at 10:01:30.
    traces = [
        _trace("a", datetime(2026, 11, 17, 10, 0, 5, tzinfo=UTC), 5000),
        _trace("b", datetime(2026, 11, 17, 11, 0, 0, tzinfo=UTC), 0),  # never derivada
    ]
    records = [
        ActionRecord(call_id="a", at=datetime(2026, 11, 17, 10, 1, 30, tzinfo=UTC), action="derive")
    ]
    counted = metrics.compute(traces, records)
    assert counted.time_to_derive_s.count == 1
    assert counted.time_to_derive_s.max == 90.0
    assert counted.latency_ms["total"].p50 == 6.0
    assert counted.latency_ms["ia"].count == 0


def test_stats_use_the_nearest_rank() -> None:
    spread = metrics.stats([float(v) for v in range(1, 101)])
    assert (spread.count, spread.p50, spread.p95, spread.max, spread.mean) == (
        100,
        50.0,
        95.0,
        100.0,
        50.5,
    )
