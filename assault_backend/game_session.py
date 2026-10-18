from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime

from assault_sim.sim_env import SimEnv
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.config.config_loader import load_sim_config
from assault_sim.decision.mission_planner import MissionPlanner
from assault_model.core.victory_outcomes import evaluate_scenario_outcome
from assault_model.map.hex_coord import HexCoord


from assault_model.paths import MAP_PIECE_CATALOG_PATH, SCENARIOS_DIR as SCENARIOS_PATH, ASSETS_DIR


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
        self.last_telemetry: Optional[dict] = None
        self.mission_planner: Optional[MissionPlanner] = None
        self.ai_observability: dict = {
            "total_decisions": 0,
            "by_source": {},
            "ai_status_counts": {},
            "ezv2_status_counts": {},
            "corrected_count": 0,
            "recent_decisions": [],
        }

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

        from assault_model.paths import ASSETS_DIR
        config.data_root = ASSETS_DIR

        config.scenario_name = scenario_id

        # ✅ guardar escenario (CLAVE)
        self.scenario_id = scenario_id
        self.sides_config = {str(k).upper(): str(v).lower() for k, v in (sides or {}).items()}
        self.env = SimEnv(
            config,
            debug_config=DebugConfig(enabled=True)
        )

        self.last_events = []
        self.trace_events = []
        self.trace_path = self._trace_file_path(scenario_id)
        self.last_backend_ai_decision = None
        self.mission_planner = MissionPlanner()
        self.ai_observability = {
            "total_decisions": 0,
            "by_source": {},
            "ai_status_counts": {},
            "ezv2_status_counts": {},
            "corrected_count": 0,
            "recent_decisions": [],
        }
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
                # ✅ Collect serializable events consumed by the UI.
                event_type = event.get("type")
                should_emit_ui = event_type in {"ACTION_EFFECT", "VP_CAPTURED", "REACTION_FIRE", "REACTION_WINDOW", "UNIT_MOVED"}
                should_trace = event_type in {"ACTION", "ACTION_EFFECT", "VP_CAPTURED", "TURN_END", "MATCH_END", "REACTION_FIRE", "REACTION_WINDOW", "UNIT_MOVED"}
                if not (should_emit_ui or should_trace):
                    return
                self._event_seq += 1
                payload = self._to_jsonable(event.get("payload", {}))
                if event_type in {"ACTION_EFFECT", "VP_CAPTURED"}:
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
                if should_emit_ui:
                    # Stable id lets the frontend dedupe log entries regardless
                    # of which endpoint (step / ai-turn / state) delivers them.
                    safe_event = {
                        **event,
                        "id": self._event_seq,
                        "payload": payload,
                    }
                    self.last_events.append(safe_event)
                if should_trace:
                    self._append_trace_event(event_type, payload)
            self.env.event_bus.subscribe(on_event)

        self.env.reset()
        if getattr(self.env, "runtime", None) is not None:
            # Runtime is instantiated inside SimEnv.reset(); wire controller roles
            # after reset so interactive matches always trigger REACTION_WINDOW.
            self.env.runtime.side_controller_map = dict(self.sides_config)

        # ✅ Discard startup events (contain non-JSON-serializable objects like HexCoord)
        self.last_events.clear()

    # ---------------------------------------------
    def record_ai_decision(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        obs = self.ai_observability
        obs["total_decisions"] = int(obs.get("total_decisions", 0) or 0) + 1
        src = str(payload.get("source", "unknown") or "unknown")
        ai_status = str(payload.get("ai_status", payload.get("sb3_status", "unknown")) or "unknown")
        by_source = dict(obs.get("by_source", {}) or {})
        by_source[src] = int(by_source.get(src, 0) or 0) + 1
        obs["by_source"] = by_source
        ai_counts = dict(obs.get("ai_status_counts", {}) or {})
        ai_counts[ai_status] = int(ai_counts.get(ai_status, 0) or 0) + 1
        obs["ai_status_counts"] = ai_counts
        obs["sb3_status_counts"] = ai_counts  # backwards compatibility alias
        if bool(payload.get("corrected", False)):
            obs["corrected_count"] = int(obs.get("corrected_count", 0) or 0) + 1
        recent = list(obs.get("recent_decisions", []) or [])
        recent.append(self._to_jsonable(payload))
        obs["recent_decisions"] = recent[-30:]
        self.ai_observability = obs

    # ---------------------------------------------
    def get_state(self) -> Dict[str, Any]:
        if self.env is None or getattr(self.env, "game_state", None) is None:
            return {"units": []}

        state = self.env.game_state
        runtime = getattr(self.env, "runtime", None)
        game_map = getattr(state, "game_map", None)
        if game_map is None:
            return {"units": []}

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
            u_type = getattr(u, "unit_type", None)
            max_hp = getattr(u, "max_strength", None) or getattr(u_type, "max_strength", 2) or 2
            curr_hp = 0 if not alive else (getattr(u, "hp", None) if getattr(u, "hp", None) is not None else max_hp)
            health_pct = round(float(curr_hp) / max(1.0, float(max_hp)), 2)
            
            attack_raw = getattr(u_type, "_attack_raw", {}) if u_type else {}
            classification = str(getattr(u_type, "classification", "") or "")
            code = str(getattr(u_type, "code", "") or "")

            traits = list(getattr(u_type, "traits", []) or [])
            movement = int(getattr(u_type, "movement", 2) or 2)

            is_mortar = "MORTAR" in code or "BRIXIA" in code or classification == "INDIRECT_FIRE_UNIT"
            has_indirect = is_mortar or ("INDIRECT_FIRE" in attack_raw) or ("INDIRECT_FIRE" in traits)
            is_hmg = "MG" in code or "HMG" in code or "MMG" in code or "BREDA" in code or "BROWNING" in code
            is_assault = "RIFLE" in code or "RANGER" in code or "GRENADIER" in code or classification in {"STANDARD_INFANTRY", "SPECIALIZED_INFANTRY"}

            max_range = 10
            for t in traits:
                if t.startswith("MAX_RANGE_"):
                    try:
                        max_range = int(t.split("_")[-1])
                    except (ValueError, IndexError):
                        pass
            if is_mortar and max_range == 10:
                max_range = 8
            elif is_hmg and max_range == 10:
                max_range = 6

            tactical_role = "indirect_mortar" if is_mortar else ("suppression_mg" if is_hmg else ("assault_squad" if is_assault else "infantry"))

            units.append({
                "id": u.unit_id,
                "unit_key": str(u_type.code) if u_type else "UNKNOWN",
                "q": u.position.q,
                "r": u.position.r,
                "position": {"q": u.position.q, "r": u.position.r},
                "side": u.side,
                "hp": curr_hp,
                "max_hp": max_hp,
                "health_pct": health_pct,
                "tactical_role": tactical_role,
                "has_indirect_fire": has_indirect,
                "is_suppression_mg": is_hmg,
                "is_assault_squad": is_assault,
                "traits": traits,
                "movement": movement,
                "max_range": max_range,
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
                    origin_coord = HexCoord.from_any(piece.get("origin", piece))
                    rotation = int(piece.get("rotation", 0))

                    pieces.append({
                        "id": piece_id,
                        "origin": [origin_coord.q, origin_coord.r],
                        "q": origin_coord.q,
                        "r": origin_coord.r,
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
        if victory_outcomes and vps and runtime is not None:
            outcome = evaluate_scenario_outcome(state=runtime.base_state, scenario=runtime.scenario)
            if outcome.matched_table_row:
                victory_outcome_state = {
                    "tracked_side": outcome.tracked_side,
                    "metric": outcome.metric,
                    "timing": outcome.timing,
                    "captured": outcome.captured,
                    "objectives_total": outcome.objectives_total,
                    "outcome": outcome.matched_table_row,
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
            "pending_reaction": getattr(runtime, "pending_reaction", None) if runtime is not None else None,
            "last_events": copied_events,
            "trace_path": str(self.trace_path) if self.trace_path is not None else None,
            "ai_observability": self._to_jsonable(self.ai_observability),
            "telemetry": self.last_telemetry,
        }
        return payload