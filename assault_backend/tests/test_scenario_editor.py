"""
assault_backend/tests/test_scenario_editor.py

Unit and integration tests for ScenarioEditorService and REST API endpoints.
Tests draft creation, editing, cloning, validation, publishing, and cleanup.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import pytest
from pathlib import Path

from assault_backend.services.scenario_editor_service import (
    scenario_editor_service,
    validate_scenario_payload,
    get_empty_scenario_template,
)
from tools.scenario_editor_server import ScenarioEditorHandler, ThreadingHTTPServer


@pytest.fixture(scope="module")
def running_scenario_editor_server():
    """Starts the standalone scenario editor server in a daemon thread on a test port."""
    test_port = 8797
    server = ThreadingHTTPServer(("127.0.0.1", test_port), ScenarioEditorHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{test_port}"
    server.shutdown()
    server.server_close()


def test_list_scenarios_returns_published_and_drafts():
    scenarios = scenario_editor_service.list_all_scenarios()
    assert len(scenarios) >= 2, "Expected at least canonical scenarios (mettete, battaglia)"
    
    # Check published canonicals
    published_ids = {s["id"] for s in scenarios if s["status"] == "published"}
    assert "battaglia_cittadina_2_1" in published_ids or "battaglia_cittadina" in published_ids
    assert "mettete_i_piedi_terra_1" in published_ids


def test_create_update_and_delete_draft():
    draft_id = "test_pytest_draft_01"
    
    # Clean up before
    scenario_editor_service.delete_draft(draft_id)

    # 1. Create draft
    draft = scenario_editor_service.create_draft(draft_id)
    assert draft["id"] == draft_id
    assert draft["status"] == "draft"
    assert (scenario_editor_service.drafts_dir / f"{draft_id}.json").exists()

    # 2. Update draft
    draft["name"] = "Pytest Updated Draft Title"
    draft["max_turns"] = 12
    updated = scenario_editor_service.update_draft(draft_id, draft)
    assert updated["name"] == "Pytest Updated Draft Title"
    assert updated["max_turns"] == 12

    # 3. Retrieve draft
    loaded = scenario_editor_service.get_scenario(draft_id, prefer_draft=True)
    assert loaded["name"] == "Pytest Updated Draft Title"
    assert loaded["max_turns"] == 12
    assert loaded["status"] == "draft"

    # 4. Delete draft
    deleted = scenario_editor_service.delete_draft(draft_id)
    assert deleted is True
    assert not (scenario_editor_service.drafts_dir / f"{draft_id}.json").exists()


def test_clone_existing_scenario():
    clone_id = "test_pytest_cloned_draft"
    scenario_editor_service.delete_draft(clone_id)

    # Clone canonical scenario
    cloned = scenario_editor_service.create_draft(
        scenario_id=clone_id,
        clone_from_id="battaglia_cittadina_2_1"
    )
    assert cloned["id"] == clone_id
    assert cloned["status"] == "draft"
    assert "units" in cloned
    assert len(cloned["units"]) > 0

    # Cleanup
    scenario_editor_service.delete_draft(clone_id)


def test_validation_schema():
    # 1. Valid scenario template
    valid_payload = get_empty_scenario_template("test_valid_scenario")
    is_valid, errors, warnings = validate_scenario_payload(valid_payload)
    assert is_valid is True, f"Expected valid template, got errors: {errors}"
    assert len(errors) == 0

    # 2. Invalid map piece
    invalid_payload = dict(valid_payload)
    invalid_payload["map"] = {"pieces": [{"id": "NON_EXISTENT_PIECE_XYZ", "origin": [0, 0]}]}
    is_valid, errors, _ = validate_scenario_payload(invalid_payload)
    assert is_valid is False
    assert any("does not exist in map piece catalog" in e for e in errors)

    # 3. Invalid unit key
    invalid_unit_payload = dict(valid_payload)
    invalid_unit_payload["units"] = [{
        "unit_id": "U1",
        "side": "US",
        "unit_key": "NON_EXISTING_UNIT_KEY_99",
        "position": [0, 0],
        "experience": "REGULAR"
    }]
    is_valid, errors, _ = validate_scenario_payload(invalid_unit_payload)
    assert is_valid is False
    assert any("references unknown unit_key" in e for e in errors)


def test_publish_and_unpublish_lifecycle():
    pub_draft_id = "test_lifecycle_publish_draft"
    pub_file = scenario_editor_service.scenarios_dir / f"{pub_draft_id}.json"
    
    # Cleanup before
    scenario_editor_service.delete_draft(pub_draft_id)
    if pub_file.exists():
        pub_file.unlink()

    # 1. Create valid draft
    draft = get_empty_scenario_template(pub_draft_id)
    scenario_editor_service.create_draft(pub_draft_id, data=draft)

    # 2. Publish draft
    pub_res = scenario_editor_service.publish_draft(pub_draft_id)
    assert pub_res["ok"] is True
    assert pub_res["status"] == "published"
    assert pub_file.exists()

    # Check that it loads as published
    pub_data = scenario_editor_service.get_scenario(pub_draft_id, prefer_draft=False)
    assert pub_data["status"] == "published"

    # 3. Unpublish scenario back to draft
    unpub_res = scenario_editor_service.unpublish_scenario(pub_draft_id)
    assert unpub_res["ok"] is True
    assert unpub_res["status"] == "draft"
    assert not pub_file.exists()
    assert (scenario_editor_service.drafts_dir / f"{pub_draft_id}.json").exists()

    # Final Cleanup
    scenario_editor_service.delete_draft(pub_draft_id)


def test_server_http_endpoints(running_scenario_editor_server):
    # 1. GET /
    req = urllib.request.Request(f"{running_scenario_editor_server}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Assault - Tactical Scenario Editor" in html
        assert "hexCanvas" in html

    # 2. GET /api/catalogs
    req_cat = urllib.request.Request(f"{running_scenario_editor_server}/api/catalogs")
    with urllib.request.urlopen(req_cat) as resp:
        assert resp.status == 200
        cat_data = json.loads(resp.read().decode("utf-8"))
        assert cat_data["ok"] is True
        assert len(cat_data["units"]) >= 19
        assert len(cat_data["map_pieces"]) >= 4

    # 3. GET /api/scenarios
    req_scen = urllib.request.Request(f"{running_scenario_editor_server}/api/scenarios")
    with urllib.request.urlopen(req_scen) as resp:
        assert resp.status == 200
        scen_data = json.loads(resp.read().decode("utf-8"))
        assert scen_data["ok"] is True
        assert scen_data["count"] > 0
