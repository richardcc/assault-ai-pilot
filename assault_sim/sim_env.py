"""
Simulation Environment (SimEnv)
Low-level simulation driver (execution only).
"""

import os

from assault_sim.config.config_loader import SimConfig
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.core.scenario_loader import load_scenario

from assault_model.state.game_state import GameState
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.runtime.execution_context import ExecutionContext

from assault_sim.debug.debug_config import DebugConfig
from assault_sim.debug.event_bus import EventBus
from assault_model.map.terrain_config import terrain_config

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


class SimEnv:
    def __init__(self, config: SimConfig, debug_config=None, controller=None):
        self.config = config
        self.debug_config = debug_config or DebugConfig(enabled=False)

        self.controller = controller  # not used (kept for compatibility)

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

        
        self.terrain_config = terrain_config
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
                            "modes": list(u.unit_type._attack_raw.keys()),
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

        self._step_counter += 1
        if self._step_counter > self._max_steps:
            raise RuntimeError("Simulation overflow (infinite loop protection)")

        if action is None and DEBUG_TRACE:
            print("[TRACE][NO_ACTION_AVAILABLE] (external scheduler handles it)")

        if self.event_bus and action is not None:
            self.event_bus.emit({
                "type": "ACTION",
                "payload": {
                    "turn": self.game_state.turn,
                    "action": action.__class__.__name__,
                    "unit_id": getattr(action, "unit", None).unit_id if getattr(action, "unit", None) else None,
                }
            })

        context = ExecutionContext(event_bus=self.event_bus)

        prev_turn = self.game_state.turn

        # -------------------------------------------------
        # APPLY ACTION
        # -------------------------------------------------
        self.runtime.apply_action(action, context=context)
        self.game_state = self.runtime.base_state

        # -------------------------------------------------
        # MAP UPDATE
        # -------------------------------------------------
        self._emit_map_state()

        # -------------------------------------------------
        # MATCH END
        # -------------------------------------------------
        if self.game_state.done:
            self._emit_match_end()
            return self.game_state, 0.0, True, {}

        # -------------------------------------------------
        # TURN CHANGE (runtime-driven)
        # -------------------------------------------------
        if self.game_state.turn != prev_turn:

            if DEBUG_TRACE:
                print("[TRACE][TURN_ADVANCED] new turn detected")

            if self.event_bus:
                self.event_bus.emit({
                    "type": "TURN_END",
                    "payload": {
                        "turn": prev_turn,
                    },
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
    # MAP STATE
    # -------------------------------------------------
    def _emit_map_state(self):
        if not self.event_bus:
            return

        game_map = self.game_state.game_map
        hexes = getattr(game_map, "hexes", [])

        # ✅ CALCULAR SHAPE (FIX CRÍTICO)
        max_q = max(h.q for h in hexes) if hexes else 0
        max_r = max(h.r for h in hexes) if hexes else 0
        shape = [max_q + 1, max_r + 1]

        # ✅ HEXES SERIALIZABLES
        hex_list = [
            {
                "q": h.q,
                "r": h.r,
                "terrain": getattr(h, "terrain", None)
            }
            for h in hexes
        ]

        # 🚨 NO ENVIAR PIECES DESDE AQUÍ
        # (porque SimEnv no los tiene)

        self.event_bus.emit({
            "type": "MAP_STATE",
            "state": self.game_state,
            "payload": {
                "turn": self.game_state.turn,
                "active_side": getattr(self.runtime, "active_side", None),
                "scenario_name": getattr(self.scenario, "name", None),

                "shape": shape,
                "hexes": hex_list,

                # ✅ 🔥 IMPORTANTE
                "map": {
                    "pieces": []
                },

                "units": [
                    {
                        "id": u.unit_id,
                        "unit_key": u.unit_type.code,
                        "q": u.position.q if u.position else None,
                        "r": u.position.r if u.position else None,
                        "side": u.side,
                        "hp": getattr(u, "hp", None),
                    }
                    for u in self.game_state.units
                ],
            },
    })

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
