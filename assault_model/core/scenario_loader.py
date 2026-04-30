# assault_model/core/scenario_loader.py

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

from assault_model.core.scenario import Scenario
from assault_model.map.map import Map
from assault_model.map.map_piece import MapPieceDefinition
from assault_model.map.hex import Hex
from assault_model.units.unit_instance import UnitInstance
from assault_model.units.unit_type import UnitType
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.core.game_state import GameState


# DEBUG TRACE (configurable by environment)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class ScenarioLoaderError(Exception):
    """Raised when a scenario file cannot be loaded or is invalid."""


def _offset_hex(hex_: Hex, origin: Tuple[int, int]) -> Hex:
    return Hex(
        q=hex_.q + origin[0],
        r=hex_.r + origin[1],
        terrain=hex_.terrain,
    )


def load_scenario(
    scenario_path: Path,
    unit_catalog: Dict[str, UnitType],
    map_piece_catalog: Dict[str, MapPieceDefinition],
) -> Scenario:
    if not scenario_path.exists():
        raise ScenarioLoaderError(f"Scenario not found: {scenario_path}")

    raw = json.loads(scenario_path.read_text(encoding="utf-8"))

    # =================================================
    # Map construction from map pieces
    # =================================================
    pieces_def = raw.get("map", {}).get("pieces", [])
    if not pieces_def:
        raise ScenarioLoaderError("Scenario map has no pieces")

    global_hexes: List[Hex] = []

    # Temporary containers for offset state
    pending_hex_states: List[Tuple[Tuple[int, int], object]] = []
    pending_hex_edges: List[Tuple[Tuple[int, int], Tuple[int, int], object]] = []

    for entry in pieces_def:
        piece_id = entry["id"]
        if piece_id not in map_piece_catalog:
            raise ScenarioLoaderError(
                f"Map piece '{piece_id}' not found in catalog"
            )

        piece = map_piece_catalog[piece_id]
        origin = tuple(entry["origin"])

        # ---- Offset hexes ----
        for h in piece.hexes:
            global_hexes.append(_offset_hex(h, origin))

        # ---- Offset hex states ----
        for (q, r), state in piece.hex_states.items():
            global_coord = (q + origin[0], r + origin[1])
            pending_hex_states.append((global_coord, state))

        # ---- Offset hex edge features ----
        for (a, b), feature in piece.hex_edges.items():
            aq, ar = a
            bq, br = b
            pending_hex_edges.append(
                (
                    (aq + origin[0], ar + origin[1]),
                    (bq + origin[0], br + origin[1]),
                    feature,
                )
            )

    # ---- Sanity check: no overlapping hexes ----
    coords = [(h.q, h.r) for h in global_hexes]
    if len(coords) != len(set(coords)):
        raise ScenarioLoaderError("Overlapping hexes detected")

    game_map = Map(hexes=global_hexes)

    # =================================================
    # Attach hex states and edge features to the map
    # =================================================
    for (q, r), state in pending_hex_states:
        state.hex = game_map.get_hex(q, r)
        game_map.set_hex_state(q, r, state)

    for a, b, feature in pending_hex_edges:
        game_map.add_hex_edge_feature(a, b, feature)

    # =================================================
    # Unit instantiation (FROM CATALOG)
    # =================================================
    units: List[UnitInstance] = []

    for u in raw.get("units", []):
        unit_key = u["unit_key"]

        if unit_key not in unit_catalog:
            raise ScenarioLoaderError(
                f"UnitType '{unit_key}' not found in unit catalog"
            )

        pos = tuple(u["position"])
        if game_map.get_hex(*pos) is None:
            raise ScenarioLoaderError(
                f"Unit {u['unit_id']} outside map at {pos}"
            )

        unit_type = unit_catalog[unit_key]

        _trace(
            "SCENARIO_UNIT_TYPE",
            unit_id=u["unit_id"],
            unit_key=unit_key,
            attack_raw=unit_type._attack_raw,
            base_defense_raw=unit_type._base_defense_raw,
        )

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
    # Scenario object
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
    )

    # =================================================
    # Initial game state for simulation
    # =================================================
    game_state = GameState(
        game_map=game_map,
        units=units,
        turn=1,
    )
    game_state.start_action_phase()
    scenario.initial_game_state = game_state

    # =================================================
    # Emit UNIT_LOADED events (unchanged behavior)
    # =================================================
    event_bus = getattr(game_state, "event_bus", None)
    if event_bus:
        for unit in game_state.units:
            event_bus.emit(
                {
                    "type": "UNIT_LOADED",
                    "payload": {
                        "unit_id": unit.unit_id,
                        "side": unit.side,
                        "position": unit.position,
                        "hp": unit.hp,
                    },
                }
            )

    return scenario