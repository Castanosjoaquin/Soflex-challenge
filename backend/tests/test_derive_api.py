"""Etapa ④ end to end over the API, in modo simulado: derivar, ampliaciones, bandeja, cierre."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.calls.action_log import ActionLog
from app.config import REPO_ROOT, LLMProviderName, Settings
from app.main import create_app

CASE_001 = "SFX-REC-2026-001"
GARRAFA = "Sí, hay una garrafa grande al lado de la cocina."


def _replay(client: TestClient, sample_id: str) -> dict[str, Any]:
    sample = client.get(f"/api/samples/{sample_id}").json()
    state: dict[str, Any] = client.post(
        "/api/calls", json={"line": sample["line"], "sample_id": sample_id}
    ).json()
    for turn in sample["turns"]:
        state = _ok(client.post(f"/api/calls/{state['call_id']}/turns", json=turn))
    return state


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _act(client: TestClient, call_id: str, **action: str) -> dict[str, Any]:
    return _ok(client.post(f"/api/calls/{call_id}/actions", json=action))


def _stage(state: dict[str, Any], stage_id: str) -> dict[str, Any]:
    stage: dict[str, Any] = next(s for s in state["stages"] if s["id"] == stage_id)
    return stage


def _lines(carta: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *carta["where"],
        *carta["what"],
        *carta["priority"],
        *carta["at_risk"],
        *carta["instructions"],
    ]


def _log(client: TestClient) -> ActionLog:
    log: ActionLog = client.app.state.action_log  # type: ignore[attr-defined]
    return log


def test_case_001_derive_then_ampliacion_reaches_the_despachador(client: TestClient) -> None:
    # 1. abrir → turnos → confirmar ubicación y tipo → derivar
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    assert not state["can_derive"]
    _act(client, call_id, kind="confirm_location")
    state = _act(client, call_id, kind="confirm_type")
    assert state["can_derive"]
    assert _stage(state, "derivar") == {"id": "derivar", "status": "actual", "alert": True}
    state = _ok(client.post(f"/api/calls/{call_id}/derive"))
    assert state["derived"]
    assert _stage(state, "derivar")["status"] == "hecha"

    (inbox,) = client.get("/api/dispatch").json()
    assert inbox["call_id"] == call_id
    assert inbox["ampliaciones"] == []
    carta = inbox["carta"]
    assert "recursos" not in carta
    assert {d["value"] for d in carta["priority"]} >= {"P1"}
    assert any("1540" in d["value"] for d in carta["where"])

    # 2. nuevo turno «hay una garrafa» → confirmar la pre-marca de gas
    state = _ok(
        client.post(f"/api/calls/{call_id}/turns", json={"speaker": "llamante", "text": GARRAFA})
    )
    gas = next(i for i in state["checklist"] if i["question_id"] == "inc_gas")
    assert gas["status"] == "pre_marcada"
    # A turno alone amplifies nothing: only what the operador confirms.
    assert client.get("/api/dispatch").json()[0]["ampliaciones"] == []
    state = _act(client, call_id, kind="confirm_premark", target="inc_gas")

    # 3. la ampliación aparece en /api/dispatch
    (ampliacion,) = state["ampliaciones"]
    (inbox,) = client.get("/api/dispatch").json()
    assert inbox["ampliaciones"] == [ampliacion]
    assert ampliacion["action"] == "confirm_premark"
    gas_change = next(c for c in ampliacion["changes"] if c["key"] == "senal.gas")
    assert (gas_change["label"], gas_change["before"], gas_change["after"]) == ("Gas", None, "Sí")
    # The Carta as derivada stays as it was: the ampliación is added, not merged.
    assert all(d["key"] != "senal.gas" for d in _lines(inbox["carta"]))

    actions = [(r.action, r.target) for r in _log(client).for_call(call_id)]
    assert ("derive", "carta") in actions
    assert actions[-1] == ("ampliacion", "confirm_premark")


def test_derive_without_ubicacion_confirmed_is_409(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    _act(client, call_id, kind="confirm_type")
    response = client.post(f"/api/calls/{call_id}/derive")
    assert response.status_code == 409
    assert "ubicación" in response.json()["detail"]
    assert client.get("/api/dispatch").json() == []
    assert all(r.action != "derive" for r in _log(client).for_call(call_id))


def test_derive_twice_is_409_and_unknown_call_is_404(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    _ok(client.post(f"/api/calls/{call_id}/derive"))
    assert client.post(f"/api/calls/{call_id}/derive").status_code == 409
    assert client.post("/api/calls/nope/derive").status_code == 404
    assert len(client.get("/api/dispatch").json()) == 1


def test_carta_sends_pre_marcas_unconfirmed_and_lists_the_skipped_pregunta(
    client: TestClient,
) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    state = _act(client, call_id, kind="skip_question", target="inc_propagacion")
    carta = _ok(client.post(f"/api/calls/{call_id}/derive"))["carta"]
    atrapada = next(d for d in carta["at_risk"] if d["key"] == "senal.persona_atrapada")
    assert (atrapada["quote"], atrapada["confirmed"]) == ("adentro quedó el cocinero", False)
    assert all(d["origin"] in {"llamante", "sistema", "operador"} for d in _lines(carta))
    propagacion = next(i for i in state["checklist"] if i["question_id"] == "inc_propagacion")
    assert {"text": propagacion["text"], "skipped": True} in carta["missing"]
    atrapados = next(i for i in state["checklist"] if i["question_id"] == "inc_atrapados")
    assert atrapados["text"] not in {m["text"] for m in carta["missing"]}


def test_ampliaciones_follow_priority_location_and_instrucciones(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    _ok(client.post(f"/api/calls/{call_id}/derive"))
    critical = state["critical_instruction"]["instruction_id"]
    _act(client, call_id, kind="mark_instruction_read", target=critical)
    _act(client, call_id, kind="set_priority", value="P2", reason="El cocinero ya salió")
    state = _act(client, call_id, kind="correct_location", value="Av. Corrientes 1450")
    actions = [a["action"] for a in state["ampliaciones"]]
    assert actions == ["mark_instruction_read", "set_priority", "correct_location"]
    priority = next(c for c in state["ampliaciones"][1]["changes"] if c["key"] == "prioridad")
    assert (priority["before"], priority["after"]) == ("P1", "P2")
    address = next(
        c for c in state["ampliaciones"][2]["changes"] if c["key"] == "ubicacion.direccion"
    )
    assert "1540" in address["before"] and "1450" in address["after"]
    # Confirming the same thing again changes nothing in the Carta: no ampliación.
    state = _act(client, call_id, kind="mark_instruction_read", target=critical)
    assert len(state["ampliaciones"]) == 3


def test_dispatch_lists_the_most_recent_carta_first(client: TestClient) -> None:
    ids = []
    for _ in range(2):
        call_id = _replay(client, CASE_001)["call_id"]
        _act(client, call_id, kind="confirm_location")
        _act(client, call_id, kind="confirm_type")
        _ok(client.post(f"/api/calls/{call_id}/derive"))
        ids.append(call_id)
    assert [c["call_id"] for c in client.get("/api/dispatch").json()] == ids[::-1]


def test_close_drops_the_call_and_keeps_registro_and_bandeja(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    _ok(client.post(f"/api/calls/{call_id}/derive"))
    assert client.post(f"/api/calls/{call_id}/close").status_code == 204
    assert client.post(f"/api/calls/{call_id}/close").status_code == 404
    gone = client.post(f"/api/calls/{call_id}/turns", json={"speaker": "llamante", "text": "hola"})
    assert gone.status_code == 404
    assert _log(client).for_call(call_id)[-1].action == "close"
    assert [c["call_id"] for c in client.get("/api/dispatch").json()] == [call_id]


def test_bandeja_is_append_only(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    _ok(client.post(f"/api/calls/{call_id}/derive"))
    db = client.app.state.settings.database_path  # type: ignore[attr-defined]
    with sqlite3.connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM cartas")
    with sqlite3.connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE cartas SET carta = '{}'")


def test_add_note_goes_to_the_carta_and_the_registro(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    state = _act(client, call_id, kind="add_note", value="  Se escuchan gritos de fondo  ")
    assert state["notes"] == ["Se escuchan gritos de fondo"]
    (nota,) = state["carta"]["notes"]
    assert (nota["key"], nota["value"], nota["origin"]) == (
        "nota.1",
        "Se escuchan gritos de fondo",
        "operador",
    )
    record = _log(client).for_call(call_id)[-1]
    assert (record.action, record.target) == ("add_note", "nota.1")
    assert record.before is None and record.after == '"Se escuchan gritos de fondo"'

    blank = client.post(f"/api/calls/{call_id}/actions", json={"kind": "add_note", "value": " "})
    assert blank.status_code == 422
    assert _log(client).for_call(call_id)[-1].target == "nota.1"


def test_a_note_after_derivar_is_an_ampliacion(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    _act(client, call_id, kind="add_note", value="Llamante muy nervioso")
    _act(client, call_id, kind="confirm_location")
    _act(client, call_id, kind="confirm_type")
    _ok(client.post(f"/api/calls/{call_id}/derive"))
    state = _act(client, call_id, kind="add_note", value="El dueño espera en la esquina")
    (ampliacion,) = state["ampliaciones"]
    assert ampliacion["action"] == "add_note"
    assert ampliacion["changes"] == [
        {
            "key": "nota.2",
            "label": "Nota del operador",
            "before": None,
            "after": "El dueño espera en la esquina",
        }
    ]
    (inbox,) = client.get("/api/dispatch").json()
    assert [n["value"] for n in inbox["carta"]["notes"]] == ["Llamante muy nervioso"]


def test_despacho_reloads_as_a_panel_route(tmp_path: Path) -> None:
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<div id=root></div>")
    settings = Settings(
        llm_provider=LLMProviderName.MOCK,
        dataset_path=REPO_ROOT / "data" / "dataset_challenge_soflex.csv",
        database_path=tmp_path / "test.db",
        static_dir=static,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/despacho")
        assert response.status_code == 200
        assert "root" in response.text
        assert client.get("/api/dispatch").json() == []
