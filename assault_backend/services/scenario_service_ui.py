import json
from pathlib import Path

from assault_model.map.hex_coord import HexCoord


# ---------------------------------------------
# PATHS
# ---------------------------------------------
from assault_model.paths import SCENARIOS_DIR as SCENARIOS_PATH, MAP_PIECE_CATALOG_PATH


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
    units = []

    for piece in scenario.get("map", {}).get("pieces", []):
        piece_id = piece.get("id")
        origin_coord = HexCoord.from_any(piece.get("origin", piece))
        origin_q, origin_r = origin_coord.q, origin_coord.r

        piece_def = pieces_catalog.get(piece_id)

        if not piece_def:
            raise ValueError(f"Unknown map piece: {piece_id}")

        ui_pieces.append({
            "id": piece_id,
            "origin": [origin_q, origin_r],
            "q": origin_q,
            "r": origin_r,
            "shape": piece_def.get("shape", [1, 1]),
        })

        for h in piece_def.get("hexes", []):
            hq = int(h.get("q", 0))
            hr = int(h.get("r", 0))
            hexes.append({
                "q": origin_q + hq,
                "r": origin_r + hr,
                "terrain": h.get("terrain", "clear"),
            })

    # ---------------------------------------------
    # BUILD UNITS (STATIC ONLY)
    # ---------------------------------------------
    for u in scenario.get("units", []):
        u_coord = HexCoord.from_any(u.get("position", u))
        units.append({
            "id": u.get("unit_id"),
            "unit_key": u.get("unit_key"),
            "q": u_coord.q,
            "r": u_coord.r,
            "position": {"q": u_coord.q, "r": u_coord.r},
            "side": u.get("side"),
        })

    # ---------------------------------------------
    # SIDES & METADATA
    # ---------------------------------------------
    sides = list(
        dict.fromkeys(
            s
            for s in [
                scenario.get("attacker_side"),
                scenario.get("defender_side"),
            ]
            + [u.get("side") for u in units]
            if s
        )
    )

    # ---------------------------------------------
    # FINAL
    # ---------------------------------------------
    return {
        "id": scenario.get("id"),
        "maxTurns": scenario.get("max_turns"),
        "shape": scenario.get("shape"),
        "sides": sides,
        "map": {
            "pieces": ui_pieces,
            "fortifications": scenario.get("map", {}).get("fortifications", []),
        },
        "hexes": hexes,
        "units": units,
    }
