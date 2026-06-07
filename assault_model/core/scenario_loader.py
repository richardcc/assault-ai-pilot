import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

from assault_model.core.scenario import Scenario
from assault_model.map.map import Map
from assault_model.map.map_piece import MapPieceDefinition
from assault_model.map.hex import Hex
from assault_model.map.hex_coord import HexCoord
from assault_model.units.unit_instance import UnitInstance
from assault_model.units.unit_type import UnitType
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.state.game_state import GameState
from assault_model.map.terrain_config import terrain_config


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class ScenarioLoaderError(Exception):
    pass


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _offset_hex(hex_: Hex, origin: Tuple[int, int]) -> Hex:
    return Hex(
        q=hex_.q + origin[0],
        r=hex_.r + origin[1],
        terrain=hex_.terrain,
    )


def _rotation_to_quarter_turns(rotation_deg: int) -> int:
    if rotation_deg % 90 != 0:
        raise ScenarioLoaderError(
            f"Invalid piece rotation {rotation_deg}. "
            "Rotation must be a multiple of 90 degrees."
        )
    return (rotation_deg // 90) % 4


def _rotate_local_coord(
    q: int,
    r: int,
    width: int,
    height: int,
    quarter_turns: int,
) -> Tuple[int, int]:
    """
    Rotate local piece coordinates clockwise in 90° steps.
    """
    if quarter_turns == 0:
        return q, r
    if quarter_turns == 1:
        return (height - 1 - r), q
    if quarter_turns == 2:
        return (width - 1 - q), (height - 1 - r)
    # quarter_turns == 3
    return r, (width - 1 - q)


def _is_adjacent_vertices(v_start: int, v_end: int) -> bool:
    if not (1 <= v_start <= 6 and 1 <= v_end <= 6):
        return False
    if v_start == v_end:
        return False
    # Adjacent on circular sequence 1..6
    return ((v_start % 6) + 1 == v_end) or ((v_end % 6) + 1 == v_start)


# -------------------------------------------------
# Main loader
# -------------------------------------------------
def load_scenario(
    scenario_path: Path,
    unit_catalog: Dict[str, UnitType],
    map_piece_catalog: Dict[str, MapPieceDefinition],
) -> Scenario:

    if not scenario_path.exists():
        raise ScenarioLoaderError(f"Scenario not found: {scenario_path}")

    raw = json.loads(scenario_path.read_text(encoding="utf-8"))

    # =================================================
    # MAP CONSTRUCTION
    # =================================================
    pieces_def = raw.get("map", {}).get("pieces", [])
    if not pieces_def:
        raise ScenarioLoaderError("Scenario map has no pieces")

    global_hexes: List[Hex] = []
    pending_hex_edges: List[
        Tuple[Tuple[int, int], Tuple[int, int], object]
    ] = []

    for entry in pieces_def:
        piece_id = entry["id"]

        if piece_id not in map_piece_catalog:
            raise ScenarioLoaderError(
                f"Map piece '{piece_id}' not found in catalog"
            )

        piece = map_piece_catalog[piece_id]
        origin = tuple(entry["origin"])
        rotation_deg = int(entry.get("rotation", 0))
        quarter_turns = _rotation_to_quarter_turns(rotation_deg)
        piece_width, piece_height = piece.shape

        # ✅ HEXES
        for h in piece.hexes:
            rq, rr = _rotate_local_coord(
                h.q,
                h.r,
                piece_width,
                piece_height,
                quarter_turns,
            )
            global_hexes.append(
                Hex(
                    q=rq + origin[0],
                    r=rr + origin[1],
                    terrain=h.terrain,
                )
            )

        # ✅ EDGES
        for (a, b), feature in piece.hex_edges.items():
            aq, ar = a
            bq, br = b
            aq, ar = _rotate_local_coord(
                aq,
                ar,
                piece_width,
                piece_height,
                quarter_turns,
            )
            bq, br = _rotate_local_coord(
                bq,
                br,
                piece_width,
                piece_height,
                quarter_turns,
            )
            pending_hex_edges.append(
                (
                    (aq + origin[0], ar + origin[1]),
                    (bq + origin[0], br + origin[1]),
                    feature,
                )
            )

    # ✅ check overlapping
    coords = [(h.q, h.r) for h in global_hexes]
    if len(coords) != len(set(coords)):
        raise ScenarioLoaderError("Overlapping hexes detected")

    game_map = Map(hexes=global_hexes)

    # =================================================
    # APPLY EDGE FEATURES
    # =================================================
    for a, b, feature in pending_hex_edges:
        game_map.add_hex_edge_feature(a, b, feature)

    # =================================================
    # APPLY FORTIFICATIONS (optional scenario overlays)
    # =================================================
    for fort in raw.get("map", {}).get("fortifications", []):
        q = int(fort["q"])
        r = int(fort["r"])
        fort_type = str(fort["type"])
        vertex_start = fort.get("vertex_start")
        vertex_end = fort.get("vertex_end")
        if game_map.get_hex(q, r) is None:
            raise ScenarioLoaderError(
                f"Fortification '{fort_type}' outside map at {(q, r)}"
            )
        if (vertex_start is None) != (vertex_end is None):
            raise ScenarioLoaderError(
                f"Fortification '{fort_type}' at {(q, r)} must define both "
                "vertex_start and vertex_end, or neither"
            )
        if vertex_start is not None and vertex_end is not None:
            vertex_start = int(vertex_start)
            vertex_end = int(vertex_end)
            if not _is_adjacent_vertices(vertex_start, vertex_end):
                raise ScenarioLoaderError(
                    f"Fortification '{fort_type}' at {(q, r)} has invalid edge "
                    f"({vertex_start},{vertex_end}). Vertices must be adjacent "
                    "in 1..6 circular order."
                )
        game_map.add_hex_fortification(
            q,
            r,
            fort_type,
            vertex_start=vertex_start,
            vertex_end=vertex_end,
        )

    # =================================================
    # UNIT INSTANTIATION
    # =================================================
    units: List[UnitInstance] = []

    for u in raw.get("units", []):

        unit_key = u["unit_key"]

        if unit_key not in unit_catalog:
            raise ScenarioLoaderError(
                f"UnitType '{unit_key}' not found in unit catalog"
            )

        pos_tuple = tuple(u["position"])
        if game_map.get_hex(*pos_tuple) is None:
            raise ScenarioLoaderError(
                f"Unit {u['unit_id']} outside map at {pos_tuple}"
            )

        pos = HexCoord(*pos_tuple)
        unit_type = unit_catalog[unit_key]

        units.append(
            UnitInstance(
                unit_id=u["unit_id"],
                unit_type=unit_type,
                side=u["side"],
                position=pos,
                experience=u.get("experience", "REGULAR"),
            )
        )

    # =================================================
    # SCENARIO
    # =================================================
    scenario = Scenario(
        name=raw["id"],
        game_map=game_map,
        units=units,
        max_turns=raw.get("max_turns"),
        vp_conditions=(
            VictoryConditions.from_json(raw["vp"])
            if "vp" in raw
            else None
        ),
        victory_outcomes=raw.get("victory_outcomes"),
    )
    scenario.terrain_config = terrain_config

    # =================================================
    # ✅ GAME STATE (SIN ACTIVACIÓN)
    # =================================================
    game_state = GameState(
        game_map=game_map,
        units=units,
        turn=1,
    )

    # ❌ ELIMINADO:
    # game_state.start_action_phase()

    scenario.initial_game_state = game_state

    return scenario