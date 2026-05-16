"""
Simulation Environment (SimEnv)
Low-level simulation driver.
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

        # ✅ protección contra loops infinitos
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

            self.runtime = RuntimeGameState(self.game_state, self.scenario)
            self.runtime.start_turn()
            self.game_state = self.runtime.base_state

            self._step_counter = 0  # reset loop guard

            if self.event_bus:
                self.event_bus.emit({
                    "type": "RESET",
                    "payload": {
                        "scenario": self.scenario.name,
                        "turn": self.game_state.turn,
                    },
                })

                # ✅ ✅ NUEVO: SCENARIO INITIALIZED
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

        # ✅ loop protection
        self._step_counter += 1
        if self._step_counter > self._max_steps:
            raise RuntimeError("Simulation overflow (infinite loop protection)")

        # controlador opcional
        if action is None and self.controller is not None:
            action = self.controller.choose_action(self.game_state)

        # -------------------------------------------------
        # DEBUG: NO ACTION
        # -------------------------------------------------
        if action is None and DEBUG_TRACE:
            blocked = [
                {
                    "unit": u.unit_id,
                    "suppressed": u.is_suppressed(),
                    "fallback": u.is_in_fallback(),
                }
                for u in self.game_state.units
                if not self.runtime._can_unit_act(u)
            ]

            print("[TRACE][NO_ACTION_AVAILABLE]", blocked)

        # ✅ ACTION EVENT
        if self.event_bus and action is not None:
            self.event_bus.emit({
                "type": "ACTION",
                "payload": {
                    "turn": self.game_state.turn,
                    "action": action.__class__.__name__,
                    "active_unit": (
                        self.game_state.active_unit.unit_id
                        if self.game_state.active_unit else None
                    ),
                },
            })

        # =================================================
        # ✅ AUTO-SKIP INVALID ACTIVE UNIT
        # =================================================
        active = self.game_state.active_unit

        if active and not self.runtime._can_unit_act(active):

            if DEBUG_TRACE:
                print(f"[TRACE][AUTO_SKIP] {active.unit_id}")

            if self.event_bus:
                self.event_bus.emit({
                    "type": "AUTO_SKIP",
                    "payload": {
                        "unit": active.unit_id,
                        "reason": (
                            "FALLBACK"
                            if active.is_in_fallback()
                            else "SUPPRESSED"
                        ),
                    },
                })

            self.runtime._consume_activation(active)
            self.runtime._advance_activation()

            self.game_state = self.runtime.base_state

            return self.game_state, 0.0, False, {}

        # -------------------------------------------------
        # APPLY ACTION
        # -------------------------------------------------
        context = ExecutionContext(event_bus=self.event_bus)

        self.runtime.apply_action(action, context=context)
        self.game_state = self.runtime.base_state

        # ✅ MAP AFTER ACTION
        self._emit_map_state()

        # ✅ MATCH END
        if self.game_state.done:
            self._emit_match_end()
            return self.game_state, 0.0, True, {}

        # -------------------------------------------------
        # TURN END (FIXED ✅)
        # -------------------------------------------------
        if self.runtime.turn_has_ended():

            if DEBUG_TRACE:
                print("[TRACE][TURN_EMPTY] advancing turn")

            self.runtime.end_turn()
            self.game_state = self.runtime.base_state

            if self.event_bus:
                self.event_bus.emit({
                    "type": "TURN_END",
                    "payload": {
                        "turn": self.game_state.turn,
                    },
                })

            self._emit_map_state()

            if self.game_state.done:
                self._emit_match_end()
                return self.game_state, 0.0, True, {}

            # ✅ siguiente turno
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

        self.event_bus.emit({
            "type": "MAP_STATE",
            "payload": {
                "turn": self.game_state.turn,
                "game_map": self.game_state.game_map,
                "units": self.game_state.units,
                "vp_tracker": self.game_state.vp_tracker,
                "game_state": self.game_state,
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
