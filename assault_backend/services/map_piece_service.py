# services/map_piece_service.py

import json
from pathlib import Path

MAP_PIECE_CATALOG_PATH = (
    Path(__file__).resolve()
    .parents[2]
    / "assault_sim"
    / "assets"
    / "catalogs"
    / "map_piece_catalog.json"
)

def load_map_piece_catalog_raw() -> dict:
    if not MAP_PIECE_CATALOG_PATH.exists():
        raise FileNotFoundError("map_piece_catalog.json")

    with open(MAP_PIECE_CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_map_piece_raw(piece_id: str) -> dict:
    catalog = load_map_piece_catalog_raw()
    pieces = catalog.get("pieces", {})

    if piece_id not in pieces:
        raise FileNotFoundError(piece_id)

    return {
        "id": piece_id,
        **pieces[piece_id]
    }
