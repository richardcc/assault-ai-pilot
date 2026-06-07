"""
Simulation Environment (SimEnv)
Low-level simulation driver (execution only).
"""

import os

from assault_sim.config.config_loader import SimConfig
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.core.scenario_loader import load_scenario
from assault_model.actions.action_catalog import ActionCatalog

from assault_model.state.game_state import GameState
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.runtime.execution_context import ExecutionContext

from assault_sim.debug.debug_config import DebugConfig
from assault_sim.debug.event_bus import EventBus
from assault_model.map.terrain_config import terrain_config
from assault_model.actions.status import WaitAction

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


class SimEnv:
    def __init__(self, config: SimConfig, debug_config=None, controller=None):
        self.config = config
        self.debug_config = debug_config or DebugConfig(enabled=False)

        self.controller = controller
        self.event_bus = EventBus() if self.debug_config.enabled else None

        self.scenario = None
        self.game_state = None
        self.runtime = None

        self._step_counter = 0
        self._max_steps = 10000

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):

        root = self.config.data_root

        unit_catalog = load_unit_catalog(root / self.config.unit_catalog)
        map_catalog = load_map_piece_catalog(root / self.config.map_piece_catalog)

        scenario_path = (
            root
            / self.config.scenario_folder
            / f"{self.config.scenario_name}.json"
        )

        self.scenario = load_scenario(scenario_path, unit_catalog, map_catalog)
        self.game_state = GameState.from_scenario(self.scenario)

        self.game_state.game_map.terrain_config = terrain_config

        self.runtime = RuntimeGameState(self.game_state, self.scenario)
        self.runtime.start_turn()
        self.game_state = self.runtime.base_state

        self._step_counter = 0

        if self.event_bus:

            self.event_bus.emit({
                "type": "RESET",
                "payload": {
                    "scenario": self.scenario.name,
                    "turn": self.game_state.turn,
                },
            })

            self.event_bus.emit({
                "type": "SCENARIO_INITIALIZED",
                "payload": {
                    "scenario": self.scenario.name,
                    "units": [
                        {
                            "unit_id": u.unit_id,
                            "type": u.unit_type.code,
                            "classification": u.unit_type.classification,
                            "side": u.side,
                            "position": u.position,
                        }
                        for u in self.game_state.units
                    ]
                },
            })

            self._emit_map_state()

        return self.game_state

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):


        if hasattr(action, "action_id"): pass
        elif isinstance(action, WaitAction): pass
        elif isinstance(action, str):
            action = self._resolve_action_by_id(action)
            if action is None:
                print("[ERROR] action could not be resolved ❌")
                return self.game_state, 0.0, False, {}
        elif action is None:
            action = WaitAction("SYSTEM")
        else:
            print("[ERROR] unsupported action type:", type(action))
            return self.game_state, 0.0, False, {}

        self._step_counter += 1
        if self._step_counter > self._max_steps:
            raise RuntimeError("Simulation overflow")

        if action is None and DEBUG_TRACE:
            print("[TRACE][NO_ACTION_AVAILABLE]")

        # ✅ ACTION EVENT
        if self.event_bus and action is not None:
            self.event_bus.emit({
                "type": "ACTION",
                "payload": {
                    "turn": self.game_state.turn,
                    "action": action.__class__.__name__,
                    "unit_id": getattr(action, "unit_id", None),
                    "target_unit_id": getattr(action, "target_id", None),
                    "action_id": getattr(action, "action_id", None),
                }
            })

        context = ExecutionContext(
            event_bus=self.event_bus,
            game_map=self.game_state.game_map,
        )

        prev_turn = self.game_state.turn

        # APPLY
        self.runtime.apply_action(action, context=context)
        self.game_state = self.runtime.base_state

        # UPDATE MAP
        self._emit_map_state()

        # END MATCH
        if self.game_state.done:
            self._emit_match_end()
            return self.game_state, 0.0, True, {}

        # TURN CHANGE
        if self.game_state.turn != prev_turn:

            if self.event_bus:
                self.event_bus.emit({
                    "type": "TURN_END",
                    "payload": {"turn": prev_turn},
                })

            self._emit_map_state()

            if self.game_state.done:
                self._emit_match_end()
                return self.game_state, 0.0, True, {}

            self.runtime.start_turn()
            self.game_state = self.runtime.base_state

            self._emit_map_state()

            return self.game_state, 0.0, False, {}

        return self.game_state, 0.0, False, {}

    # -------------------------------------------------
    # ✅ NEW: RESOLVE ACTION BY ID
    # -------------------------------------------------
    def _resolve_action_by_id(self, action_id: str):

        print(f"[DEBUG] resolving action_id: {action_id}")

        if not action_id:
            return None

        try:
            parts = action_id.split(":")
            unit_id = parts[1]
            print(f"[DEBUG] extracted unit_id: {unit_id}")
        except Exception:
            print("[DEBUG] failed to parse action_id")
            return None

        unit = next(
            (u for u in self.game_state.units if u.unit_id == unit_id),
            None
        )

        print(f"[DEBUG] found unit: {unit.unit_id if unit else None}")

        if unit is None:
            return None

        if not getattr(unit, "alive", True):
            print("[DEBUG] unit is dead — action rejected")
            return None

        catalog = ActionCatalog(
            self.game_state,
            unit,
            terrain_config=self.game_state.game_map.terrain_config
        )

        actions = catalog.actions()

        print(f"[DEBUG] available actions:")
        for a in actions:
            if getattr(a, "action_id", None) is None and isinstance(a, WaitAction):
                a.action_id = f"WAIT:{getattr(a, 'unit_id', unit_id)}"
            print("   ", getattr(a, "action_id", None))

        for a in actions:
            if getattr(a, "action_id", None) is None and isinstance(a, WaitAction):
                a.action_id = f"WAIT:{getattr(a, 'unit_id', unit_id)}"
            if getattr(a, "action_id", None) == action_id:
                print("[DEBUG] MATCH FOUND ✅")
                return a

        print("[DEBUG] NO MATCH ❌")
        return None


    # -------------------------------------------------
    # MAP STATE
    # -------------------------------------------------
    def _emit_map_state(self):
        if not self.event_bus:
            return

        game_map = self.game_state.game_map
        hexes = getattr(game_map, "hexes", [])

        max_q = max((h.q for h in hexes), default=0)
        max_r = max((h.r for h in hexes), default=0)
        shape = [max_q + 1, max_r + 1]

        hex_list = [
            {
                "q": h.q,
                "r": h.r,
                "terrain": h.get_terrain()
            }
            for h in hexes
        ]

        vps = []
        vp_tracker = getattr(self.game_state, "vp_tracker", None)

        if vp_tracker and getattr(vp_tracker, "conditions", None):
            for vp in getattr(vp_tracker.conditions, "points", []):
                vps.append(tuple(vp.hex_coords))

            event = {
            "type": "MAP_STATE",
            "state": self.game_state,

            "payload": {
                "turn": self.game_state.turn,
                "active_side": getattr(self.runtime, "active_side", None),
                "scenario_name": getattr(self.scenario, "name", None),

                "shape": shape,
                "hexes": hex_list,
                "vps": vps,

                "units": [
                    {
                        "id": u.unit_id,
                        "q": u.position.q if u.position else None,
                        "r": u.position.r if u.position else None,
                        "side": u.side,
                        "hp": getattr(u, "hp", None),
                    }
                    # 🛠️ ¡ARREGLADO AQUÍ! 
                    # Añadimos este filtro para que solo emita al visualizador las unidades vivas.
                    for u in self.game_state.units if getattr(u, "alive", True)
                ],
            },
        }

        self.event_bus.emit(event)



    # -------------------------------------------------
    # MATCH END
    # -------------------------------------------------
    def _emit_match_end(self):
        if not self.event_bus:
            return

        self.event_bus.emit({
            "type": "MATCH_END",
            "payload": {
                "winner": self.game_state.winner,
                "reason": self.game_state.end_reason,
                "turn": self.game_state.turn,
            },
        })