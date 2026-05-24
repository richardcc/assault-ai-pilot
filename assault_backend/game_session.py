from typing import Optional, Dict, Any
from pathlib import Path
import json

from assault_sim.sim_env import SimEnv
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.config.config_loader import load_sim_config


MAP_PIECE_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "assault_sim"
    / "assets"
    / "catalogs"
    / "map_piece_catalog.json"
)

SCENARIOS_PATH = (
    Path(__file__).resolve().parents[1]
    / "assault_sim"
    / "assets"
    / "scenarios"
)


class GameSession:
    def __init__(self):
        self.env: Optional[SimEnv] = None
        self.scenario_id: Optional[str] = None  # ✅ nuevo
        self.sides_config = {}

    # ---------------------------------------------
    def start(self, scenario_id: str, sides: Dict[str, str]):
        base_path = Path(__file__).resolve().parents[1]

        config_path = (
            base_path
            / "assault_sim"
            / "config"
            / "sim_config.yaml"
        )

        config = load_sim_config(str(config_path))

        config.data_root = (
            base_path
            / "assault_sim"
            / "assets"
        )

        config.scenario_name = scenario_id

        # ✅ guardar escenario (CLAVE)
        self.scenario_id = scenario_id
        self.sides_config = sides  
        self.env = SimEnv(
            config,
            debug_config=DebugConfig(enabled=True)
        )

        self.env.reset()

    # ---------------------------------------------
    def get_state(self) -> Dict[str, Any]:
        if self.env is None:
            return {"units": []}

        state = self.env.game_state
        runtime = self.env.runtime
        game_map = state.game_map

        # ✅ cargar catálogo
        with open(MAP_PIECE_CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        pieces_catalog = catalog.get("pieces", {})

        # ✅ UNITS
        units = []
        for u in state.units:
            if not getattr(u, "alive", True):
                continue
            if not u.position:
                continue

            units.append({
                "id": u.unit_id,
                "unit_key": str(u.unit_type.code),
                "q": u.position.q,
                "r": u.position.r,
                "side": u.side,
                "hp": getattr(u, "hp", None),
            })

        # ✅ HEXES
        raw_hexes = getattr(game_map, "hexes", [])

        hex_list = []
        for h in raw_hexes:
            q = getattr(h, "q", None)
            r = getattr(h, "r", None)

            if q is None or r is None:
                continue

            hex_list.append({
                "q": q,
                "r": r,
                "terrain": getattr(h, "terrain", None)
            })

        # ✅ SHAPE
        if hex_list:
            max_q = max(h["q"] for h in hex_list)
            max_r = max(h["r"] for h in hex_list)
            shape = [max_q + 1, max_r + 1]
        else:
            shape = [0, 0]

        # =========================================
        # ✅ ✅ FIX REAL → PIECES DESDE SCENARIO
        # =========================================
        pieces = []

        if self.scenario_id:
            scenario_path = SCENARIOS_PATH / f"{self.scenario_id}.json"

            if scenario_path.exists():
                with open(scenario_path, "r", encoding="utf-8") as f:
                    scenario = json.load(f)

                for piece in scenario.get("map", {}).get("pieces", []):
                    piece_id = piece.get("id")
                    origin = piece.get("origin", [0, 0])

                    pieces.append({
                        "id": piece_id,
                        "origin": origin,
                        "shape": pieces_catalog.get(piece_id, {}).get("shape", [1, 1]),
                    })

        # ✅ FINAL
        activated_units = []
        if hasattr(runtime, "activated_units"):
            activated_units = list(runtime.activated_units)
        return {
            "scenario_name": getattr(self.env.scenario, "name", None),

            "turn": getattr(state, "turn", 0),
            "active_side": getattr(runtime, "active_side", None),

            "shape": shape,
            "hexes": hex_list,
            "map": {
                "pieces": pieces
            },

            "units": units,
            "sides": self.sides_config,
            "activated_units": activated_units,
        }