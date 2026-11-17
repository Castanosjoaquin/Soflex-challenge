"""Llamadas de demo extendidas (SPEC §5.1): loaded and validated at startup, replayed by the API.

Each demo is replayed turno by turno in modo simulado to check that the Lector por reglas sees
what the demo is written to show (DESIGN §4 and §11, guion del video).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.catalog.demos import DemoCallsError
from app.config import LLMProviderName, Settings
from app.main import create_app
from tests.conftest import DATASET

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_calls"


def _replay(client: TestClient, sample_id: str) -> list[dict[str, Any]]:
    """Every CallState after each turno."""
    sample = client.get(f"/api/samples/{sample_id}").json()
    state = client.post("/api/calls", json={"line": sample["line"], "sample_id": sample_id}).json()
    states = []
    for turn in sample["turns"]:
        response = client.post(
            f"/api/calls/{state['call_id']}/turns",
            json={"speaker": turn["speaker"], "text": turn["text"]},
        )
        assert response.status_code == 200, response.text
        state = response.json()
        states.append(state)
    return states


def _signals(state: dict[str, Any]) -> dict[str, str]:
    return {s["signal_id"]: s["value"] for s in state["signals"]}


def _premarked(state: dict[str, Any]) -> set[str]:
    return {q["question_id"] for q in state["checklist"] if q["status"] == "pre_marcada"}


def test_demos_come_first_and_marked(client: TestClient) -> None:
    samples = client.get("/api/samples").json()
    kinds = [s["kind"] for s in samples]
    assert kinds == ["demo"] * 6 + ["dataset"] * 30
    demos = samples[:6]
    assert len({d["category"] for d in demos}) == 6, "one demo per tipo de incidente"
    for demo in demos:
        assert demo["title"]
        assert all(t["delay_ms"] is not None for t in demo["turns"])
        assert len(demo["turns"]) > 2
    assert all(s["turns"][0]["delay_ms"] is None for s in samples[6:])


def test_pizzeria_follows_design_section_4(client: TestClient) -> None:
    sample = client.get("/api/samples/DEMO-01").json()
    texts = [t["text"] for t in sample["turns"]]
    assert texts[0] == "911 emergencias, ¿dónde es su urgencia?"
    assert texts[2] == "No vuelva a entrar al local. ¿Hay garrafas o gas cerca del fuego?"
    assert texts[3] == "Sí, hay una garrafa grande al lado de la cocina."
    assert texts[5] == "Arriba hay departamentos, ya sale humo por la ventana del primer piso."

    after_relato, _, after_garrafa, _, after_humo = _replay(client, "DEMO-01")[1:]
    assert after_relato["location"]["street_official"] == "AV. CORRIENTES"
    assert after_relato["location"]["number"] == {"value": 1540, "kind": "exacta"}
    assert after_relato["priority"]["level"] == "P1"
    assert after_relato["critical_instruction"] is not None
    assert "inc_gas" not in _premarked(after_relato)
    assert "inc_gas" in _premarked(after_garrafa)
    assert _signals(after_garrafa)["gas"] == "si"
    assert "inc_propagacion" in _premarked(after_humo)


def test_incomplete_address_then_altura_then_correction(client: TestClient) -> None:
    states = _replay(client, "DEMO-02")
    street_only = states[1]["location"]
    assert street_only["street_official"] == "AV. CORRIENTES"
    assert street_only["number"] is None
    assert street_only["confidence"] == "a_confirmar"
    assert states[3]["location"]["number"] == {"value": 1540, "kind": "al"}
    # Unconfirmed, the later altura wins (autocorrección); confirmed, it is a contradicción (#8).
    assert states[-1]["location"]["number"] == {"value": 1450, "kind": "al"}
    assert states[-1]["incident"]["category"] == "EMERGENCIA_MEDICA"
    assert "med_caida" in _premarked(states[-1])


def test_altura_change_after_confirming_keeps_the_confirmed_one(client: TestClient) -> None:
    sample = client.get("/api/samples/DEMO-02").json()
    state = client.post("/api/calls", json={"line": "911", "sample_id": "DEMO-02"}).json()
    call_id = state["call_id"]
    for i, turn in enumerate(sample["turns"]):
        body = {"speaker": turn["speaker"], "text": turn["text"]}
        state = client.post(f"/api/calls/{call_id}/turns", json=body).json()
        if i == 3:
            client.post(f"/api/calls/{call_id}/actions", json={"kind": "confirm_location"})
    assert state["location"]["number"] == {"value": 1540, "kind": "al"}
    assert state["location"]["confidence"] == "confirmado"


@pytest.mark.parametrize(
    ("sample_id", "category", "subtype", "street", "signals", "premarked"),
    [
        (
            "DEMO-03",
            "ACCIDENTE_VIAL",
            "choque_moto",
            "AV. SAN JUAN",
            {"motociclista": "si", "golpe_cabeza": "si", "derrame_combustible": "si"},
            {"vial_casco", "vial_moto", "vial_combustible"},
        ),
        (
            "DEMO-04",
            "DEFENSA_CIVIL",
            "arbol_caido",
            "AV. FOREST",
            {"persona_atrapada": "no", "cables_caidos": "si"},
            {"dc_atrapados", "dc_cables"},
        ),
        (
            "DEMO-05",
            "SERVICIOS_PUBLICOS",
            "rotura_cano_agua",
            "AV. MANUEL MONTES DE OCA",
            {"agua_sube": "si", "heridos": "no"},
            {"sp_agua", "sp_heridos"},
        ),
        (
            "DEMO-06",
            "CONVIVENCIA_SEGURIDAD",
            "rina",
            "SERRANO",
            {"arma_blanca": "si", "arma_fuego": "no", "heridos": "si"},
            {"cs_arma_blanca", "cs_arma_fuego", "cs_heridos", "cs_en_lugar"},
        ),
    ],
)
def test_demo_shows_what_it_is_written_for(
    client: TestClient,
    sample_id: str,
    category: str,
    subtype: str,
    street: str,
    signals: dict[str, str],
    premarked: set[str],
) -> None:
    final = _replay(client, sample_id)[-1]
    assert (final["incident"]["category"], final["incident"]["subtype"]) == (category, subtype)
    assert final["location"]["street_official"] == street
    assert signals.items() <= _signals(final).items()
    assert premarked <= _premarked(final)


def test_parse_pasted_text_with_prefixes(client: TestClient) -> None:
    text = "Operador: 911, ¿su emergencia?\nLlamante: Se prende fuego la cocina en Yerbal 2450."
    turns = client.post("/api/transcripts/parse", json={"text": text}).json()
    assert turns == [
        {"speaker": "operador", "text": "911, ¿su emergencia?"},
        {"speaker": "llamante", "text": "Se prende fuego la cocina en Yerbal 2450."},
    ]


def test_parse_pasted_text_without_prefixes_is_one_llamante_turn(client: TestClient) -> None:
    turns = client.post("/api/transcripts/parse", json={"text": "  hay humo  "}).json()
    assert turns == [{"speaker": "llamante", "text": "hay humo"}]


def _settings(tmp_path: Path, demo_dir: Path) -> Settings:
    return Settings(
        llm_provider=LLMProviderName.MOCK,
        dataset_path=DATASET,
        database_path=tmp_path / "test.db",
        static_dir=tmp_path / "no-static",
        demo_calls_dir=demo_dir,
    )


def _write_demo(directory: Path, **changes: Any) -> None:
    demo = json.loads((DEMO_DIR / "01-pizzeria-corrientes.json").read_text(encoding="utf-8"))
    demo.update(changes)
    directory.mkdir(exist_ok=True)
    (directory / "99-rota.json").write_text(json.dumps(demo), encoding="utf-8")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"line": "999"}, "99-rota.json"),
        ({"turns": [{"speaker": "llamante", "text": "hola"}]}, "99-rota.json"),
        ({"based_on": "SFX-REC-2026-999"}, "no es un caso del dataset"),
    ],
)
def test_invalid_demo_stops_startup(tmp_path: Path, changes: dict[str, Any], message: str) -> None:
    _write_demo(tmp_path / "demos", **changes)
    with (
        pytest.raises(DemoCallsError, match=message),
        TestClient(create_app(_settings(tmp_path, tmp_path / "demos"))),
    ):
        pass
