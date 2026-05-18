import json
from pathlib import Path

# -------------------------------------------------
# PATHS
# -------------------------------------------------
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

# -------------------------------------------------
# LOAD RAW SCENARIO
# -------------------------------------------------
def load_scenario_raw(scenario_id: str) -> dict:
    """
    Load scenario JSON and RETURN WITH TERRAIN HEXES BUILT.
    """

    # -------------------------------------------------
    # Load scenario
    # -------------------------------------------------
    scenario_path = SCENARIOS_PATH / f"{scenario_id}.json"

    if not scenario_path.exists():
        raise FileNotFoundError(scenario_id)

    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    # -------------------------------------------------
    # Load map piece catalog
    # -------------------------------------------------
    if not MAP_PIECE_CATALOG_PATH.exists():
        raise FileNotFoundError("map_piece_catalog.json")

    with open(MAP_PIECE_CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    pieces_catalog = catalog.get("pieces", {})

    # -------------------------------------------------
    # BUILD HEXES WITH TERRAIN
    # -------------------------------------------------
    hexes = []

    for piece in scenario.get("map", {}).get("pieces", []):

        piece_id = piece["id"]
        origin_q, origin_r = piece["origin"]

        piece_def = pieces_catalog.get(piece_id)

        if not piece_def:
            print(f"[WARN] Missing piece in catalog: {piece_id}")
            continue

        piece_hexes = piece_def.get("hexes", [])

        for h in piece_hexes:
            hexes.append({
                "q": h["q"] + origin_q,
                "r": h["r"] + origin_r,
                "terrain": h.get("terrain", "unknown")
            })

    # -------------------------------------------------
    # ATTACH TO SCENARIO
    # -------------------------------------------------
    if "map" not in scenario:
        scenario["map"] = {}

    scenario["map"]["hexes"] = hexes

    # -------------------------------------------------
    return scenario
