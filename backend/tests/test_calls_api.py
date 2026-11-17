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


def _act(client: TestClient, call_id: str, **action: str) -> Any:
    return client.post(f"/api/calls/{call_id}/actions", json=action)


def test_case_001_is_incendio_en_comercio_p1_with_its_porque(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    assert state["incident"]["category"] == "INCENDIO_RESCATE"
    assert state["incident"]["subtype"] == "incendio_comercio"
    priority = state["priority"]
    assert priority["level"] == "P1"
    assert [(r["signal_id"], r["evidence"]["quote"]) for r in priority["reasons"]] == [
        ("persona_atrapada", "adentro quedó el cocinero"),
        ("humo", "humo negro al salón"),
    ]
    # Who stayed inside cannot be checked by the llamante: the checklist goes on (SPEC §5.7).
    assert state["next_question"]["id"] == "inc_gas"
    assert _stage(state, "que_pasa") == "actual"


def test_confirm_type_goes_to_the_action_log(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    confirmed = _act(client, call_id, kind="confirm_type").json()
    assert confirmed["incident"]["confidence"] == "confirmado"
    changed = _act(client, call_id, kind="confirm_type", value="DEFENSA_CIVIL:fuga_gas").json()
    assert (changed["incident"]["category"], changed["incident"]["source"]) == (
        "DEFENSA_CIVIL",
        "operador",
    )
    records = _log(client).for_call(call_id)
    assert [(r.action, r.target) for r in records] == [("confirm_type", "incident")] * 2
    assert records[1].after is not None and "fuga_gas" in records[1].after


def test_confirm_type_with_an_unknown_or_mismatched_value_is_422(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    assert _act(client, call_id, kind="confirm_type", value="VOLCANES").status_code == 422
    mismatch = _act(client, call_id, kind="confirm_type", value="DEFENSA_CIVIL:convulsion")
    assert mismatch.status_code == 422


def test_confirm_type_without_tipo_is_409(client: TestClient) -> None:
    call_id = client.post("/api/calls", json={"line": "911"}).json()["call_id"]
    assert _act(client, call_id, kind="confirm_type").status_code == 409


def test_set_priority_without_reason_is_422_and_not_logged(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    assert _act(client, call_id, kind="set_priority", value="P3").status_code == 422
    assert _act(client, call_id, kind="set_priority", value="P3", reason=" ").status_code == 422
    assert _log(client).for_call(call_id) == []


def test_set_priority_with_reason_is_logged(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    state = _act(
        client, call_id, kind="set_priority", value="P2", reason="el cocinero ya salió"
    ).json()
    assert state["priority"]["level"] == "P2"
    assert state["priority"]["overridden_by_operator"] == {
        "from_level": "P1",
        "reason": "el cocinero ya salió",
    }
    (record,) = _log(client).for_call(call_id)
    assert (record.action, record.target, record.reason) == (
        "set_priority",
        "priority",
        "el cocinero ya salió",
    )
    assert record.before is not None and '"P1"' in record.before
    assert record.after is not None and '"P2"' in record.after


def _item(state: dict[str, Any], question_id: str) -> dict[str, Any]:
    item: dict[str, Any] = next(i for i in state["checklist"] if i["question_id"] == question_id)
    return item


def test_case_001_premark_answer_and_skip_go_to_the_action_log(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    atrapados = _item(state, "inc_atrapados")
    assert (atrapados["status"], atrapados["evidence"]["quote"]) == (
        "pre_marcada",
        "adentro quedó el cocinero",
    )
    state = _act(client, call_id, kind="confirm_premark", target="inc_atrapados").json()
    assert _item(state, "inc_atrapados")["status"] == "respondida"
    state = _act(client, call_id, kind="answer_question", target="inc_gas", value="no").json()
    assert (_item(state, "inc_gas")["status"], _item(state, "inc_gas")["source"]) == (
        "respondida",
        "operador",
    )
    state = _act(client, call_id, kind="skip_question", target="inc_propagacion").json()
    assert _item(state, "inc_propagacion")["status"] == "salteada"
    assert _stage(state, "preguntas") == "hecha"
    records = _log(client).for_call(call_id)
    assert [(r.action, r.target) for r in records] == [
        ("confirm_premark", "inc_atrapados"),
        ("answer_question", "inc_gas"),
        ("skip_question", "inc_propagacion"),
    ]
    assert records[0].before is not None and "pre_marcada" in records[0].before
    assert records[2].after is not None and "salteada" in records[2].after


def test_question_actions_check_their_target_and_value(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    assert _act(client, call_id, kind="answer_question", value="si").status_code == 422
    answer = _act(client, call_id, kind="answer_question", target="inc_gas", value="tal vez")
    assert answer.status_code == 422
    assert _act(client, call_id, kind="skip_question", target="vial_casco").status_code == 409
    assert _act(client, call_id, kind="confirm_premark", target="inc_gas").status_code == 409
    assert _log(client).for_call(call_id) == []


def test_catalog_lists_signals_types_and_subtypes(client: TestClient) -> None:
    catalog = client.get("/api/catalog").json()
    assert len(catalog["signals"]) == 25
    assert len(catalog["types"]) == 6
    assert any(s["id"] == "incendio_comercio" for s in catalog["subtypes"])
    assert catalog["priority_rules"][0]["level"] == "P1"


def test_case_001_reads_the_instrucciones_into_the_action_log(client: TestClient) -> None:
    state = _replay(client, CASE_001)
    call_id = state["call_id"]
    critical = state["critical_instruction"]
    assert critical["text"] == "No vuelva a entrar al local por ningún motivo."
    assert state["instructions"][0] == critical
    assert _stage(state, "instrucciones") == "actual"
    for item in state["instructions"]:
        state = _act(
            client, call_id, kind="mark_instruction_read", target=item["instruction_id"]
        ).json()
    assert all(i["read"] for i in state["instructions"])
    assert _stage(state, "instrucciones") == "hecha"
    records = _log(client).for_call(call_id)
    assert [r.target for r in records] == [i["instruction_id"] for i in state["instructions"]]
    assert records[0].before == '{"read":false}' and records[0].after == '{"read":true}'


def test_mark_instruction_read_checks_its_target(client: TestClient) -> None:
    call_id = _replay(client, CASE_001)["call_id"]
    assert _act(client, call_id, kind="mark_instruction_read").status_code == 422
    missing = _act(client, call_id, kind="mark_instruction_read", target="no_agua_electrico")
    assert missing.status_code == 409
    assert _log(client).for_call(call_id) == []
