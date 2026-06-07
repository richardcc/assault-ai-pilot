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
        self.last_events = []
        self._event_seq = 0

    # ---------------------------------------------
    def start(self, scenario_id: str, sides: Dict[str, str]):
        base_path = Path(__file__).resolve().parents[1]

        config_path = (
            base_path
            / "assault_sim"
            / "config"
            / "sim_config.yaml"
        )

        config = load_sim_config(config_path)

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

        self.last_events = []
        if self.env.event_bus:
            def on_event(event):
                # ✅ Collect only serializable events consumed by the UI.
                # UNIT_MOVED / MAP_STATE contain HexCoord objects that break JSON serialization.
                if event.get("type") in {"ACTION_EFFECT", "VP_CAPTURED"}:
                    payload = event.get("payload", {})
                    if payload.get("action") == "RangedCombat":
                        defender = payload.get("defender")
                        fort = payload.get("fortification", {})
                        breakdown = payload.get("defense_breakdown", {})
                        print(
                            "[FORT_DEBUG]"
                            f" defender={defender}"
                            f" sector={breakdown.get('sector')}"
                            f" fort={fort.get('type')}"
                            f" fort_bonus={fort.get('bonus_dice')}"
                            f" base={breakdown.get('base_dice')}"
                            f" terrain={breakdown.get('terrain_bonus_dice')}"
                            f" fort_split={breakdown.get('fortification_bonus_dice')}"
                        )
                    # Stable id lets the frontend dedupe combat log entries
                    # regardless of which endpoint (step / ai-turn / state) delivers them.
                    self._event_seq += 1
                    event["id"] = self._event_seq
                    self.last_events.append(event)
            self.env.event_bus.subscribe(on_event)

        self.env.reset()
        try:
            self.env.step(None)
        except Exception:
            pass

        # ✅ Discard startup events (contain non-JSON-serializable objects like HexCoord)
        self.last_events.clear()

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

        # ✅ UNITS (include dead for roster; map layer hides hp <= 0)
        units = []
        for u in state.units:
            if not u.position:
                continue

            alive = getattr(u, "alive", True)
            units.append({
                "id": u.unit_id,
                "unit_key": str(u.unit_type.code),
                "q": u.position.q,
                "r": u.position.r,
                "side": u.side,
                "hp": 0 if not alive else getattr(u, "hp", None),
                "alive": alive,
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
                "terrain": getattr(h, "terrain", None),
                "fortification": game_map.get_hex_fortification(q, r),
                "fortification_meta": game_map.get_hex_fortification_data(q, r),
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
        victory_outcomes = None

        if self.scenario_id:
            scenario_path = SCENARIOS_PATH / f"{self.scenario_id}.json"

            if scenario_path.exists():
                with open(scenario_path, "r", encoding="utf-8") as f:
                    scenario = json.load(f)

                for piece in scenario.get("map", {}).get("pieces", []):
                    piece_id = piece.get("id")
                    origin = piece.get("origin", [0, 0])
                    rotation = int(piece.get("rotation", 0))

                    pieces.append({
                        "id": piece_id,
                        "origin": origin,
                        "rotation": rotation,
                        "shape": pieces_catalog.get(piece_id, {}).get("shape", [1, 1]),
                    })
                fortifications = scenario.get("map", {}).get("fortifications", [])
                victory_outcomes = scenario.get("victory_outcomes")
            else:
                fortifications = []
        else:
            fortifications = []

        # VP ownership (live) + initial owner from scenario definition.
        ownership_to_side = {
            ownership: side
            for side, ownership in getattr(state, "side_to_ownership", {}).items()
        }
        vps = []
        vp_score_live: dict[str, int] = {
            side: 0 for side in getattr(state, "side_to_ownership", {}).keys()
        }
        if getattr(state, "victory", None):
            for vp in state.victory.points:
                q, r = vp.hex_coords
                hs = state.hex_states.get((q, r))
                current_owner = (
                    ownership_to_side.get(hs.ownership)
                    if hs is not None
                    else None
                )
                vps.append({
                    "q": q,
                    "r": r,
                    "value": vp.per_turn,
                    "initial_owner": getattr(vp, "initial_owner", None),
                    "current_owner": current_owner,
                })
                if current_owner:
                    vp_score_live[current_owner] = vp_score_live.get(current_owner, 0) + int(vp.per_turn)

        # Scenario-level objective outcome (captured objectives table).
        victory_outcome_state = None
        if victory_outcomes and vps:
            tracked_side = str(victory_outcomes.get("tracked_side", "")).strip().upper()
            if tracked_side:
                captured = sum(1 for vp in vps if (vp.get("current_owner") or "").upper() == tracked_side)
                matched_row = None
                for row in victory_outcomes.get("table", []):
                    captured_range = row.get("captured", {}) if isinstance(row, dict) else {}
                    min_cap = int(captured_range.get("min", -10**9))
                    max_cap = int(captured_range.get("max", 10**9))
                    if min_cap <= captured <= max_cap:
                        matched_row = row
                        break
                victory_outcome_state = {
                    "tracked_side": tracked_side,
                    "metric": victory_outcomes.get("metric"),
                    "timing": victory_outcomes.get("timing"),
                    "captured": captured,
                    "objectives_total": len(vps),
                    "outcome": matched_row,
                }

        # ✅ FINAL
        activated_units = []
        if hasattr(runtime, "activated_units"):
            activated_units = list(runtime.activated_units)
        copied_events = self.last_events.copy()
        self.last_events.clear()

        payload = {
            "scenario_name": getattr(self.env.scenario, "name", None),

            "turn": getattr(state, "turn", 0),
            "active_side": getattr(runtime, "active_side", None),
            "done": bool(getattr(state, "done", False)),
            "winner": getattr(state, "winner", None),
            "end_reason": getattr(state, "end_reason", None),

            "shape": shape,
            "hexes": hex_list,
            "map": {
                "pieces": pieces,
                "fortifications": fortifications,
                "vps": vps,
            },

            "units": units,
            "sides": self.sides_config,
            "vp_score_live": vp_score_live,
            "victory_outcome": victory_outcome_state,
            "activated_units": activated_units,
            "last_events": copied_events,
        }
        return payload