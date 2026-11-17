"""The contradicción of the demo over the API: «Antes dijo 1540, ahora dice 1450» (issue #8)."""

import json
from typing import Any

from fastapi.testclient import TestClient

from app.calls.action_log import ActionLog

CASE_001 = "SFX-REC-2026-001"
ALTURA = "No, perdón, es en el 1450"


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _replay(client: TestClient) -> dict[str, Any]:
    sample = client.get(f"/api/samples/{CASE_001}").json()
    state = _ok(client.post("/api/calls", json={"line": sample["line"], "sample_id": CASE_001}))
    for turn in sample["turns"]:
        state = _ok(client.post(f"/api/calls/{state['call_id']}/turns", json=turn))
    return state


def _act(client: TestClient, call_id: str, **action: str) -> dict[str, Any]:
    return _ok(client.post(f"/api/calls/{call_id}/actions", json=action))


def _say(client: TestClient, call_id: str, text: str) -> dict[str, Any]:
    turn = {"speaker": "llamante", "text": text}
    return _ok(client.post(f"/api/calls/{call_id}/turns", json=turn))


def _log(client: TestClient) -> ActionLog:
    log: ActionLog = client.app.state.action_log  # type: ignore[attr-defined]
    return log


def _derived(client: TestClient) -> str:
    call_id: str = _replay(client)["call_id"]
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    _ok(client.post(f"/api/calls/{call_id}/derive"))
    return call_id


def test_accepting_the_contradiction_after_derivar_sends_an_ampliacion(client: TestClient) -> None:
    call_id = _derived(client)
    state = _say(client, call_id, ALTURA)
    assert state["location"]["number"]["value"] == 1540
    (aviso,) = state["avisos"]
    assert aviso["text"] == "Antes dijo 1540, ahora dice 1450"
    assert aviso["status"] == "pendiente"
    assert state["ampliaciones"] == []

    state = _act(client, call_id, kind="resolve_contradiction", target=aviso["id"], value="aceptar")
    assert state["location"]["number"]["value"] == 1450
    assert state["avisos"][0]["status"] == "aceptado"
    (ampliacion,) = state["ampliaciones"]
    assert ampliacion["action"] == "resolve_contradiction"
    change = next(c for c in ampliacion["changes"] if c["key"] == "ubicacion.direccion")
    assert "1540" in change["before"] and "1450" in change["after"]
    assert client.get("/api/dispatch").json()[0]["ampliaciones"] == [ampliacion]

    record = next(r for r in _log(client).for_call(call_id) if r.action == "resolve_contradiction")
    assert record.target == aviso["id"]
    assert record.before is not None and record.after is not None
    assert json.loads(record.before)["status"] == "pendiente"
    after = json.loads(record.after)
    assert after["status"] == "aceptado"
    assert after["location"]["number"]["value"] == 1450


def test_keeping_the_old_altura_sends_nothing_and_is_logged(client: TestClient) -> None:
    call_id = _derived(client)
    aviso = _say(client, call_id, ALTURA)["avisos"][0]
    state = _act(
        client, call_id, kind="resolve_contradiction", target=aviso["id"], value="mantener"
    )
    assert state["location"]["number"]["value"] == 1540
    assert state["avisos"][0]["status"] == "mantenido"
    assert state["ampliaciones"] == []
    actions = [r.action for r in _log(client).for_call(call_id)]
    assert actions[-1] == "resolve_contradiction"


def test_without_confirmar_the_altura_changes_silently(client: TestClient) -> None:
    call_id = _replay(client)["call_id"]
    state = _say(client, call_id, ALTURA)
    assert state["location"]["number"]["value"] == 1450
    assert state["avisos"] == []


def test_resolving_a_bad_aviso_is_409_and_a_bad_value_is_422(client: TestClient) -> None:
    call_id = _derived(client)
    aviso = _say(client, call_id, ALTURA)["avisos"][0]
    url = f"/api/calls/{call_id}/actions"
    unknown = {"kind": "resolve_contradiction", "target": "aviso-9", "value": "aceptar"}
    assert client.post(url, json=unknown).status_code == 409
    bad = {"kind": "resolve_contradiction", "target": aviso["id"], "value": "quizás"}
    assert client.post(url, json=bad).status_code == 422
    no_target = {"kind": "resolve_contradiction", "value": "aceptar"}
    assert client.post(url, json=no_target).status_code == 422
