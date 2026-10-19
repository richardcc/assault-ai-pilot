from __future__ import annotations

import os
from fastapi.testclient import TestClient
from assault_backend.main import app

client = TestClient(app)


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["ai_engine"] == "EfficientZeroV2"


def test_engine_status():
    res = client.get("/api/engine/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["explanations_enabled"] is True


def test_scenarios_and_catalogs():
    res_scenarios = client.get("/api/ui/scenarios")
    assert res_scenarios.status_code == 200
    scenarios = res_scenarios.json().get("scenarios", [])
    assert len(scenarios) > 0

    res_pieces = client.get("/api/map_pieces")
    assert res_pieces.status_code == 200
    assert isinstance(res_pieces.json(), list)

    res_units = client.get("/api/units")
    assert res_units.status_code == 200
    assert isinstance(res_units.json(), list)


def test_game_lifecycle_and_ai_turn():
    # 1. Start game with first available scenario
    res_scenarios = client.get("/api/ui/scenarios")
    scenarios = res_scenarios.json().get("scenarios", [])
    scenario_id = scenarios[0]

    start_payload = {
        "scenario_id": scenario_id,
        "sides": {"US": "ai", "IT": "ai"},
    }
    res_start = client.post("/api/game/start", json=start_payload)
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "started"

    # 2. Get state
    res_state = client.get("/api/game/state")
    assert res_state.status_code == 200
    state = res_state.json()
    assert "units" in state
    assert len(state["units"]) > 0

    # 3. AI turn
    res_ai = client.post("/api/game/ai-turn")
    assert res_ai.status_code == 200
    ai_data = res_ai.json()
    assert "state" in ai_data
    assert "steps" in ai_data

    # 4. Game trace
    res_trace = client.get("/api/game/trace")
    assert res_trace.status_code == 200
    assert "events" in res_trace.json()


def test_ui_scenario_service_canonical_coordinates():
    from assault_backend.services.scenario_service_ui import load_ui_scenario
    ui_data = load_ui_scenario("battaglia_cittadina_2_1")
    assert "units" in ui_data
    assert len(ui_data["units"]) > 0

    for u in ui_data["units"]:
        assert "q" in u
        assert "r" in u
        assert "position" in u
        assert u["position"] == {"q": u["q"], "r": u["r"]}

    assert "map" in ui_data
    for piece in ui_data["map"]["pieces"]:
        assert "origin" in piece
        assert "q" in piece
        assert "r" in piece
        assert piece["origin"] == [piece["q"], piece["r"]]

