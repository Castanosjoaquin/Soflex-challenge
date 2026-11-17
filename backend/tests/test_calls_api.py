import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.calls.action_log import ActionLog

CASE_001 = "SFX-REC-2026-001"


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


def _stage(state: dict[str, Any], stage_id: str) -> str:
    return str(next(s["status"] for s in state["stages"] if s["id"] == stage_id))


def _log(client: TestClient) -> ActionLog:
    log: ActionLog = client.app.state.action_log  # type: ignore[attr-defined]
    return log


def test_sample_comes_with_parsed_turns_and_line(client: TestClient) -> None:
    sample = client.get(f"/api/samples/{CASE_001}").json()
    assert sample["line"] == "911"
    assert [t["speaker"] for t in sample["turns"]] == ["operador", "llamante"]
    assert sample["turns"][1]["text"].startswith("Hola, por favor manden")


def test_open_call_starts_on_ubicar(client: TestClient) -> None:
    state = client.post("/api/calls", json={"line": "911"}).json()
    assert state["mode"] == "simulado"
    assert state["turns"] == []
    assert state["location"] is None
    assert [(s["id"], s["status"]) for s in state["stages"]] == [
        ("ubicar", "actual"),
        ("que_pasa", "pendiente"),
        ("preguntas", "pendiente"),
        ("derivar", "pendiente"),
        ("instrucciones", "pendiente"),
    ]


def test_open_call_with_unknown_sample_is_404(client: TestClient) -> None:
    assert client.post("/api/calls", json={"line": "911", "sample_id": "NOPE"}).status_code == 404


def test_case_001_open_turns_confirm(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    location = state["location"]
    assert location["street"] == "Av. Corrientes"
    assert location["number"] == {"value": 1540, "kind": "exacta"}
    assert location["cross_streets"] == ["Montevideo"]
    assert location["confidence"] == "probable"
    (evidence,) = location["evidence"]
    turn_text = state["turns"][evidence["turn_index"]]["text"]
    assert turn_text[evidence["start"] : evidence["end"]] == evidence["quote"]
    assert evidence["quote"] == "Av. Corrientes 1540 casi Montevideo"
    assert _stage(state, "ubicar") == "actual"

    call_id = state["call_id"]
    confirmed = client.post(
        f"/api/calls/{call_id}/actions", json={"kind": "confirm_location"}
    ).json()
    assert confirmed["location"]["confidence"] == "confirmado"
    assert _stage(confirmed, "ubicar") == "hecha"

    (record,) = _log(client).for_call(call_id)
    assert (record.action, record.target) == ("confirm_location", "location")
    assert record.before is not None and '"probable"' in record.before
    assert record.after is not None and '"confirmado"' in record.after


def test_correct_location_parses_the_typed_direccion(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    corrected = client.post(
        f"/api/calls/{state['call_id']}/actions",
        json={"kind": "correct_location", "value": "Av. Corrientes 1450", "reason": "oyó mal"},
    ).json()
    location = corrected["location"]
    assert (location["street"], location["number"]["value"]) == ("Av. Corrientes", 1450)
    assert location["said"] == "Av. Corrientes 1540 casi Montevideo"
    assert (location["source"], location["confidence"]) == ("operador", "confirmado")
    (record,) = _log(client).for_call(state["call_id"])
    assert record.reason == "oyó mal"


def test_confirm_without_location_is_409(client: TestClient) -> None:
    call_id = client.post("/api/calls", json={"line": "911"}).json()["call_id"]
    response = client.post(f"/api/calls/{call_id}/actions", json={"kind": "confirm_location"})
    assert response.status_code == 409
    assert _log(client).for_call(call_id) == []


def test_unknown_call_and_action(client: TestClient) -> None:
    assert (
        client.post("/api/calls/nope/turns", json={"speaker": "llamante", "text": "x"}).status_code
        == 404
    )
    assert (
        client.post("/api/calls/nope/actions", json={"kind": "confirm_location"}).status_code == 404
    )
    call_id = client.post("/api/calls", json={"line": "911"}).json()["call_id"]
    bad = client.post(f"/api/calls/{call_id}/actions", json={"kind": "derrumbar"})
    assert bad.status_code == 422


def test_all_dataset_calls_replay_with_a_location(client: TestClient) -> None:
    for sample in client.get("/api/samples").json():
        state = _replay(client, sample["id"])
        assert len(state["turns"]) == len(sample["turns"])
        assert state["location"] is not None, sample["id"]


def test_action_log_is_append_only(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    client.post(f"/api/calls/{state['call_id']}/actions", json={"kind": "confirm_location"})
    db_path = client.app.state.settings.database_path  # type: ignore[attr-defined]
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE action_log SET action = 'x'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM action_log")
    assert not hasattr(ActionLog, "update") and not hasattr(ActionLog, "delete")
