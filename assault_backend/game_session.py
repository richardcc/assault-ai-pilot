from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime

from assault_sim.sim_env import SimEnv
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.config.config_loader import load_sim_config
from assault_sim.decision.mission_planner import MissionPlanner


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
        self.trace_events: list[dict] = []
        self.trace_path: Optional[Path] = None
        self.last_backend_ai_decision: Optional[dict] = None
        self.mission_planner: Optional[MissionPlanner] = None

    def _trace_file_path(self, scenario_id: str) -> Path:
        base_path = Path(__file__).resolve().parents[1]
        replay_dir = base_path / "assault_sim" / "session" / "replays"
        replay_dir.mkdir(parents=True, exist_ok=True)
        safe_scenario = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in str(scenario_id or "unknown"))
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return replay_dir / f"live_match_{safe_scenario}_{stamp}.jsonl"

    def _to_jsonable(self, obj):
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {str(k): self._to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._to_jsonable(v) for v in obj]
        if hasattr(obj, "q") and hasattr(obj, "r"):
            return {"q": getattr(obj, "q", None), "r": getattr(obj, "r", None)}
        if hasattr(obj, "__dict__"):
            try:
                return self._to_jsonable(vars(obj))
            except Exception:
                pass
        return str(obj)

    def _append_trace_event(self, event_type: str, payload: dict | None):
        trace_event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "seq": int(self._event_seq),
            "type": str(event_type or ""),
            "turn": int(getattr(getattr(self.env, "game_state", None), "turn", 0) or 0),
            "active_side": str(getattr(getattr(self.env, "runtime", None), "active_side", "") or ""),
            "payload": self._to_jsonable(payload or {}),
        }
        self.trace_events.append(trace_event)
        if self.trace_path is not None:
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_event, ensure_ascii=False) + "\n")

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
        self.trace_events = []
        self.trace_path = self._trace_file_path(scenario_id)
        self.last_backend_ai_decision = None
        self.mission_planner = MissionPlanner()
        with open(self.trace_path, "w", encoding="utf-8") as f:
            header = {
                "type": "MATCH_START",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "scenario_id": scenario_id,
                "sides_config": sides,
            }
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
        if self.env.event_bus:
            def on_event(event):
                # ✅ Collect only serializable events consumed by the UI.
                # UNIT_MOVED / MAP_STATE contain HexCoord objects that break JSON serialization.
                event_type = event.get("type")
                should_emit_ui = event_type in {"ACTION_EFFECT", "VP_CAPTURED"}
                should_trace = event_type in {"ACTION", "ACTION_EFFECT", "VP_CAPTURED", "TURN_END", "MATCH_END"}
                if not (should_emit_ui or should_trace):
                    return
                self._event_seq += 1
                if event_type in {"ACTION_EFFECT", "VP_CAPTURED"}:
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
                    event["id"] = self._event_seq
                    self.last_events.append(event)
                if should_trace:
                    self._append_trace_event(event_type, event.get("payload", {}))
            self.env.event_bus.subscribe(on_event)

        self.env.reset()

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
            "trace_path": str(self.trace_path) if self.trace_path is not None else None,
        }
        return payload