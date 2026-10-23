"""
assault_backend/tests/test_map_piece_editor.py

Comprehensive tests for Map Piece Editor:
1. List pieces (published + drafts).
2. Create, update, and delete draft piece.
3. Clone existing published or draft piece.
4. Schema validation for boundaries and valid terrains.
5. Publish and unpublish lifecycle.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from assault_backend.main import app
from assault_backend.services.map_piece_editor_service import (
    map_piece_editor_service,
    MAP_PIECE_DRAFTS_DIR,
)

client = TestClient(app)


def test_list_map_pieces_returns_published_and_drafts():
    res = client.get("/api/editor/map_pieces")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["count"] >= 3
    piece_ids = [p["id"] for p in data["pieces"]]
    assert "S2" in piece_ids
    assert "S3" in piece_ids


def test_create_update_and_delete_draft_map_piece():
    draft_id = "test_custom_hill_9x8"
    try:
        # Create
        create_payload = {
            "id": draft_id,
            "description": "Custom tactical ridge 9x8",
            "shape": [9, 8],
            "hexes": [
                {"q": 2, "r": 2, "terrain": "hill"},
                {"q": 3, "r": 2, "terrain": "light_forest"},
                {"q": 4, "r": 2, "terrain": "building_single"},
            ],
            "hex_edges": [
                {"from": "2,2", "to": "3,2", "feature": "wall"}
            ],
        }
        res_create = client.post("/api/editor/map_pieces/draft", json=create_payload)
        assert res_create.status_code == 200
        assert res_create.json()["piece"]["id"] == draft_id
        assert res_create.json()["piece"]["is_draft"] is True

        # Verify in list
        res_list = client.get("/api/editor/map_pieces")
        p_ids = [p["id"] for p in res_list.json()["pieces"] if p["is_draft"]]
        assert draft_id in p_ids

        # Update
        update_payload = {
            "data": {
                "id": draft_id,
                "description": "Updated tactical ridge 9x8",
                "shape": [9, 8],
                "hexes": [
                    {"q": 2, "r": 2, "terrain": "hill"},
                    {"q": 3, "r": 2, "terrain": "heavy_forest"},
                ],
                "hex_edges": [],
            }
        }
        res_update = client.put(f"/api/editor/map_pieces/draft/{draft_id}", json=update_payload)
        assert res_update.status_code == 200
        assert res_update.json()["piece"]["description"] == "Updated tactical ridge 9x8"

    finally:
        # Delete
        res_del = client.delete(f"/api/editor/map_pieces/draft/{draft_id}")
        assert res_del.status_code == 200


def test_clone_map_piece():
    clone_id = "test_s2_variant_draft"
    try:
        res = client.post("/api/editor/map_pieces/S2/clone", json={"new_id": clone_id})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["piece"]["id"] == clone_id
        assert data["piece"]["shape"] == [9, 8]
        assert len(data["piece"]["hexes"]) >= 20
    finally:
        map_piece_editor_service.delete_draft(clone_id)


def test_validation_schema():
    # Invalid terrain and out of bounds
    invalid_data = {
        "id": "invalid_piece_test",
        "shape": [9, 8],
        "hexes": [
            {"q": 15, "r": 20, "terrain": "lava_flow"},
        ],
        "hex_edges": [
            {"from": "0,0", "to": "0,1", "feature": "electric_fence"}
        ]
    }
    res = client.post("/api/editor/map_pieces/validate", json={"data": invalid_data})
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["valid"] is False
    assert any("outside piece boundaries" in err for err in res_data["errors"])
    assert any("unknown terrain" in err for err in res_data["errors"])
    assert any("feature 'electric_fence'" in err for err in res_data["errors"])


def test_publish_and_unpublish_lifecycle():
    pub_id = "test_pub_map_piece_cycle"
    try:
        # Create draft
        draft_payload = {
            "id": pub_id,
            "description": "Lifecycle test piece",
            "shape": [9, 8],
            "hexes": [
                {"q": 0, "r": 0, "terrain": "brush"},
                {"q": 1, "r": 1, "terrain": "water"},
            ],
            "hex_edges": [],
        }
        res_create = client.post("/api/editor/map_pieces/draft", json=draft_payload)
        assert res_create.status_code == 200

        # Publish
        res_pub = client.post(f"/api/editor/map_pieces/draft/{pub_id}/publish")
        assert res_pub.status_code == 200
        assert res_pub.json()["piece"]["is_draft"] is False

        # Verify in catalog
        cat = map_piece_editor_service._load_catalog_dict()
        assert pub_id in cat["pieces"]

        # Unpublish
        res_unpub = client.post(f"/api/editor/map_pieces/{pub_id}/unpublish")
        assert res_unpub.status_code == 200
        assert res_unpub.json()["piece"]["is_draft"] is True

        # Verify removed from catalog
        cat2 = map_piece_editor_service._load_catalog_dict()
        assert pub_id not in cat2["pieces"]

    finally:
        # Cleanup
        map_piece_editor_service.delete_draft(pub_id)
        cat_clean = map_piece_editor_service._load_catalog_dict()
        if pub_id in cat_clean.get("pieces", {}):
            del cat_clean["pieces"][pub_id]
            map_piece_editor_service._save_catalog_dict(cat_clean)
