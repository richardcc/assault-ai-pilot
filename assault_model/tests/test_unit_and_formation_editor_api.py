"""
assault_model/tests/test_unit_and_formation_editor_api.py

Integration tests for tools/unit_editor_server.py REST endpoints and Formation mapping.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error
import pytest

from tools.unit_editor_server import UnitEditorHandler, ThreadingHTTPServer, load_formations, save_formations


@pytest.fixture(scope="module")
def running_editor_server():
    """Starts the editor HTTP server in a daemon thread on a test port."""
    test_port = 8799
    server = ThreadingHTTPServer(("127.0.0.1", test_port), UnitEditorHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{test_port}"
    server.shutdown()
    server.server_close()


def test_editor_index_html(running_editor_server):
    """Verify that root / returns HTML with English titles and formation section."""
    url = f"{running_editor_server}/"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Assault - Tactical Unit & Formation Catalog Editor" in html
        assert "Formation Catalog" in html
        assert "view-formations" in html
        assert "select-add-line" in html


def test_api_units_state(running_editor_server):
    """Verify /api/units/state returns catalog, staging, inventory, and traits."""
    url = f"{running_editor_server}/api/units/state"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "catalog" in data
        assert "staging" in data
        assert "traits" in data


def test_api_formations_lifecycle(running_editor_server):
    """Verify GET, POST /api/formations/save, and POST /api/formations/delete."""
    # 1. GET formations
    url_get = f"{running_editor_server}/api/formations"
    with urllib.request.urlopen(url_get) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "formations" in data
        assert "units" in data
        assert "US_INF_RIFLE" in data["formations"]

    # 2. POST save test formation
    test_id = "TEST_API_FORMATION"
    test_payload = {
        "id": test_id,
        "data": {
            "name": "Test Assault Troop",
            "side": "US",
            "command_rating": 9,
            "line_units": ["US_RIFLES_43", "US_RIFLES_43"],
            "heavy_weapons": ["US_BAZOOKA_TEAM"],
            "specialists": ["US_COMBAT_ENGINEERS_43"],
            "description": "Integration test formation."
        }
    }
    url_save = f"{running_editor_server}/api/formations/save"
    req_save = urllib.request.Request(
        url_save,
        data=json.dumps(test_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req_save) as resp:
        assert resp.status == 200
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data.get("ok") is True

    # Verify it persisted
    formations = load_formations()
    assert test_id in formations
    assert formations[test_id]["name"] == "Test Assault Troop"
    assert formations[test_id]["units"] == [
        "US_RIFLES_43", "US_RIFLES_43", "US_BAZOOKA_TEAM", "US_COMBAT_ENGINEERS_43"
    ]

    # 3. POST delete test formation
    url_del = f"{running_editor_server}/api/formations/delete"
    req_del = urllib.request.Request(
        url_del,
        data=json.dumps({"id": test_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req_del) as resp:
        assert resp.status == 200
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data.get("ok") is True

    formations_after = load_formations()
    assert test_id not in formations_after
