"""Trazas of each lectura (SPEC §5.11): what each step did, told in natural language.

The Lector con IA answers from a fake HTTP endpoint; in modo simulado only the rules read.
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.calls.service import CallService
from app.engine.models import Line, Mode, Source
from app.readers.ia.reader import IAStatus
from app.trace.models import ChangeKind, ReadingTrace, Step
from app.trace.narrate import duration, narrate
from app.transcript.models import Speaker
from tests.ia_fakes import SLOW
from tests.test_ia_combination import DERRUMBE, INCENDIO, PIZZERIA, POZO, service

CASE_001 = "SFX-REC-2026-001"

# Valid on the second try: a location with a cross street never said, and an invented señal.
INVENTED = {
    "location": {
        "said": "Montevideo y Paraná",
        "quote": "Montevideo y Paraná",
        "street": "Montevideo",
        "cross_streets": ["Paraná"],
    },
    "incident": INCENDIO,
    "signals": [{"id": "gas", "value": "si", "quote": "hay olor a gas en todo el local"}],
}


def read(svc: CallService, *texts: str, line: Line = Line.L911) -> list[ReadingTrace]:
    call_id = svc.open(line).call_id
    for text in texts or (PIZZERIA,):
        asyncio.run(svc.add_turn(call_id, Speaker.LLAMANTE, text))
    return svc.readings(call_id)


def texts(trace: ReadingTrace) -> list[str]:
    return [line.text for line in narrate(trace).lines]


def alerts(trace: ReadingTrace) -> list[str]:
    return [line.text for line in narrate(trace).lines if line.alert]


def test_a_retry_and_a_discarded_dato_read_in_natural_language(tmp_path: Path) -> None:
    (trace,) = read(service(tmp_path, ["esto no es JSON", INVENTED]))

    assert trace.mode is Mode.IA
    assert trace.ia is not None
    assert trace.ia.status is IAStatus.RETRIED
    assert [a.error is not None for a in trace.ia.attempts] == [True, False]
    assert {(d.source, d.target, d.quote) for d in trace.discarded} == {
        (Source.IA, "location", "Montevideo y Paraná"),
        (Source.IA, "gas", "hay olor a gas en todo el local"),
    }

    told = alerts(trace)
    retry = next(t for t in told if t.startswith("Lector con IA"))
    assert "El primer intento vino mal (No es JSON válido" in retry
    assert "el segundo intento fue válido" in retry
    evidence = next(t for t in told if t.startswith("Control de evidencia"))
    assert "2 descartados" in evidence
    assert "la ubicación del lector con IA: «Montevideo y Paraná» no aparece en el relato" in (
        evidence
    )
    assert "Gas del lector con IA" in evidence


def test_every_step_is_timed(tmp_path: Path) -> None:
    (trace,) = read(service(tmp_path, [{"incident": INCENDIO}]))
    assert [s.step for s in trace.steps] == [Step.RELATO, Step.REGLAS, Step.IA, Step.COMBINACION]
    assert all(s.ms >= 0 for s in trace.steps)
    assert trace.total_ms == sum(s.ms for s in trace.steps)
    assert narrate(trace).title.endswith(f"· IA · {duration(trace.total_ms)}")


def test_mock_mode_traces_the_rules_and_what_changed(tmp_path: Path) -> None:
    first, second = read(service(tmp_path, None), "Hola.", PIZZERIA)

    assert first.ia is None and first.mode is Mode.SIMULADO
    assert first.changes == []
    assert "Lector con IA: no está configurado; lee solo el de reglas." in texts(first)
    assert "Prioridad: todavía sin calcular." in texts(first)

    assert second.index == 2 and second.turns == 2
    kinds = {c.kind for c in second.changes}
    assert {ChangeKind.LOCATION, ChangeKind.INCIDENT, ChangeKind.SIGNAL} <= kinds
    assert {ChangeKind.PREMARK, ChangeKind.PRIORITY} <= kinds
    told = texts(second)
    assert any(
        t.startswith("Lector por reglas: encontró 4 señales, la ubicación y el tipo") for t in told
    )
    assert "Prioridad: P1 (Persona atrapada con humo)." in told
    assert (
        "Checklist: «¿Hay personas atrapadas o adentro?» pre-marcada en sí, "
        "por «adentro quedó el cocinero»." in told
    )
    # One lector only: no control de evidencia and nothing to disagree about.
    assert not any(t.startswith("Control de evidencia") for t in told)
    assert alerts(second) == []


def test_disagreements_on_tipo_and_senal_are_traced(tmp_path: Path) -> None:
    answer = {
        "incident": DERRUMBE,
        "signals": [{"id": "persona_atrapada", "value": "si", "quote": "un pozo enorme"}],
    }
    (trace,) = read(service(tmp_path, [answer]), POZO, line=Line.L147)
    assert ("incident", "Servicios públicos", "Defensa civil") in {
        (d.target, d.rules, d.ia) for d in trace.disagreements
    }
    told = alerts(trace)
    assert "Los lectores no coinciden en el tipo: reglas Servicios públicos, IA Defensa civil." in (
        told
    )
    assert any(t.startswith("Tipo en disputa") for t in told)


def test_a_disagreeing_senal_stays_a_confirmar_in_the_traza(tmp_path: Path) -> None:
    answer = {
        "incident": INCENDIO,
        "signals": [
            {
                "id": "persona_atrapada",
                "value": "no",
                "quote": "la gente salió corriendo a la calle",
            }
        ],
    }
    (trace,) = read(service(tmp_path, [answer]))
    assert [(d.target, d.rules, d.ia) for d in trace.disagreements] == [
        ("persona_atrapada", "sí", "no")
    ]
    assert "Los dos lectores coinciden en el tipo." in texts(trace)
    assert "No coinciden en Persona atrapada: reglas sí, IA no; queda a confirmar." in alerts(trace)


def test_a_fallback_says_the_lectura_is_rules_only(tmp_path: Path) -> None:
    (broken,) = read(service(tmp_path, ["roto", "roto otra vez"]))
    (slow,) = read(service(tmp_path, [SLOW], timeout=0.05))
    assert broken.ia is not None and broken.ia.status is IAStatus.INVALID
    assert slow.ia is not None and slow.ia.status is IAStatus.TIMEOUT
    for trace in (broken, slow):
        assert trace.mode is Mode.REGLAS
        assert trace.discarded == [] and trace.disagreements == []
        assert any("Esta lectura es solo por reglas." in t for t in alerts(trace))
        assert narrate(trace).title.split(" · ")[1] == "solo reglas"


def _replay(client: TestClient, sample_id: str) -> dict[str, Any]:
    sample = client.get(f"/api/samples/{sample_id}").json()
    state: dict[str, Any] = client.post(
        "/api/calls", json={"line": sample["line"], "sample_id": sample_id}
    ).json()
    for turn in sample["turns"]:
        response = client.post(f"/api/calls/{state['call_id']}/turns", json=turn)
        assert response.status_code == 200, response.text
        state = response.json()
    return state


def test_readings_endpoint_tells_each_lectura(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    readings = client.get(f"/api/calls/{call_id}/readings").json()
    assert len(readings) == len(state["turns"])
    last = readings[-1]
    assert last["title"].startswith(f"Lectura #{len(state['turns'])} de la llamada {call_id}")
    assert all(set(line) == {"text", "alert"} for line in last["lines"])
    assert last["trace"]["mode"] == "simulado"
    assert last["trace"]["ia"] is None

    # The trazas outlive the llamada, and an unknown one is a 404.
    assert client.post(f"/api/calls/{call_id}/close").status_code == 204
    assert len(client.get(f"/api/calls/{call_id}/readings").json()) == len(readings)
    assert client.get("/api/calls/nope/readings").status_code == 404


def test_an_open_call_without_lecturas_has_no_trazas(client: TestClient) -> None:
    call_id = client.post("/api/calls", json={"line": "911"}).json()["call_id"]
    assert client.get(f"/api/calls/{call_id}/readings").json() == []


def test_trazas_are_append_only(client: TestClient, tmp_path: Path) -> None:
    _replay(client, CASE_001)
    with sqlite3.connect(tmp_path / "test.db") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE reading_traces SET idx = 0")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM reading_traces")
