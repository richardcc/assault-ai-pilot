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
    Build UI scenario from scratch (no dependency on engine service).
    """

    # ---------------------------------------------
    # LOAD SCENARIO RAW FILE
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
    # BUILD HEXES (SIMPLE)
    # ---------------------------------------------
    hexes = []

    for piece in scenario.get("map", {}).get("pieces", []):
        piece_id = piece.get("id")
        origin_q, origin_r = piece.get("origin", [0, 0])

        piece_def = pieces_catalog.get(piece_id, {})
        piece_hexes = piece_def.get("hexes", [])

        for h in piece_hexes:
            hexes.append({
                "q": h.get("q", 0) + origin_q,
                "r": h.get("r", 0) + origin_r,
                "terrain": h.get("terrain", "clear")
            })

    # ---------------------------------------------
    # BUILD UNITS (SIMPLE)
    # ---------------------------------------------
    units = []

    for u in scenario.get("units", []):
        pos = u.get("position", [0, 0])

        units.append({
            "id": u.get("unit_id"),
            "q": pos[0],
            "r": pos[1],
            "side": u.get("side")
        })

    # ---------------------------------------------
    # RETURN UI STRUCTURE
    # ---------------------------------------------
    return {
        "id": scenario.get("id"),
        "maxTurns": scenario.get("max_turns"),
        "shape": scenario.get("shape"),

        "map": scenario.get("map"),

        "hexes": hexes,
        "units": units
    }
