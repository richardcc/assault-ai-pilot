import json
from pathlib import Path


# ---------------------------------------------
# PATHS
# ---------------------------------------------
SCENARIOS_PATH = (
    Path(__file__).resolve()
    .parents[2]
    / "assault_sim"
    / "assets"
    / "scenarios"
)

MAP_PIECE_CATALOG_PATH = (
    Path(__file__).resolve()
    .parents[2]
    / "assault_sim"
    / "assets"
    / "catalogs"
    / "map_piece_catalog.json"
)


def load_ui_scenario(scenario_id: str) -> dict:
    """
    Build UI scenario from raw scenario + catalog data.
    Pure UI layer (no game state).
    """

    # ---------------------------------------------
    # LOAD SCENARIO
    # ---------------------------------------------
    scenario_path = SCENARIOS_PATH / f"{scenario_id}.json"

    if not scenario_path.exists():
        raise FileNotFoundError(scenario_id)

    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    # ---------------------------------------------
    # LOAD MAP PIECE CATALOG
    # ---------------------------------------------
    if not MAP_PIECE_CATALOG_PATH.exists():
        raise FileNotFoundError("map_piece_catalog.json")

    with open(MAP_PIECE_CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    pieces_catalog = catalog.get("pieces", {})

    # ---------------------------------------------
    # BUILD MAP
    # ---------------------------------------------
    ui_pieces = []
    hexes = []

    for piece in scenario.get("map", {}).get("pieces", []):
        piece_id = piece.get("id")
        origin_q, origin_r = piece.get("origin", [0, 0])

        piece_def = pieces_catalog.get(piece_id)

        if not piece_def:
            raise ValueError(f"Unknown map piece: {piece_id}")

        ui_pieces.append({
            "id": piece_id,
            "origin": [origin_q, origin_r],
            "shape": piece_def.get("shape", [1, 1]),
        })

        for h in piece_def.get("hexes", []):
            hexes.append({
                "q": origin_q + h.get("q", 0),
                "r": origin_r + h.get("r", 0),
                "terrain": h.get("terrain", "clear"),
            })

    # ---------------------------------------------
    # BUILD UNITS (STATIC ONLY)
    # ---------------------------------------------
    units = []

    for u in scenario.get("units", []):
        q, r = u.get("position", [0, 0])

        units.append({
            "id": u.get("unit_id"),
            "unit_key": u.get("unit_key"),
            "q": q,
            "r": r,
            "side": u.get("side"),
        })

    # ---------------------------------------------
    # FINAL
    # ---------------------------------------------
    return {
        "id": scenario.get("id"),
        "maxTurns": scenario.get("max_turns"),
        "shape": scenario.get("shape"),
        "map": {
            "pieces": ui_pieces
        },
        "hexes": hexes,
        "units": units,  # ⚠️ solo placeholder (se sustituye luego)
    }