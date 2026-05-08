"""
Simulation Environment (SimEnv)
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


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class SimEnv:
    def __init__(
        self,
        config: SimConfig,
        debug_config: DebugConfig | None = None,
        controller=None,
    ):
        self.config = config
        self.debug_config = debug_config or DebugConfig(enabled=False)
        self.controller = controller

        self.event_bus = EventBus() if self.debug_config.enabled else None

        self.scenario = None
        self.game_state: GameState | None = None
        self.runtime: RuntimeGameState | None = None

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

        # ✅ First turn always starts here
        self.runtime.start_turn()
        self.game_state = self.runtime.base_state

        if self.event_bus:
            self.event_bus.emit(
                {
                    "type": "RESET",
                    "payload": {
                        "scenario": self.scenario.name,
                        "turn": self.game_state.turn,
                    },
                }
            )

            self.event_bus.emit(
                {
                    "type": "MAP_STATE",
                    "payload": {
                        "turn": self.game_state.turn,
                        "game_map": self.game_state.game_map,
                        "units": self.game_state.units,
                        "vp_tracker": self.game_state.vp_tracker,
                        "game_state": self.game_state,
                    },
                }
            )

        return self.game_state

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        """
        Execute one simulation step.

        Semantics:
        - Apply exactly one action
        - Close the turn if no activations remain
        - Evaluate match end ONLY after full turn resolution
        """

        if action is None and self.controller is not None:
            action = self.controller.choose_action(self.game_state)

        if self.event_bus and action is not None:
            self.event_bus.emit(
                {
                    "type": "ACTION",
                    "payload": {
                        "turn": self.game_state.turn,
                        "action": action.__class__.__name__,
                        "active_unit": (
                            self.game_state.active_unit.unit_id
                            if self.game_state.active_unit
                            else None
                        ),
                    },
                }
            )

        # --- Apply action ---
        context = ExecutionContext(event_bus=self.event_bus)
        self.runtime.apply_action(action, context=context)
        self.game_state = self.runtime.base_state

        # -------------------------------------------------
        # TURN END
        # -------------------------------------------------
        if (
            self.runtime.turn_has_ended()
            and self.game_state.active_unit is None
        ):
            if self.event_bus:
                self.event_bus.emit(
                    {
                        "type": "TURN_END",
                        "payload": {
                            "turn": self.game_state.turn,
                            "reason": "engine_reported_turn_end",
                        },
                    }
                )

                self.event_bus.emit(
                    {
                        "type": "MAP_STATE",
                        "payload": {
                            "turn": self.game_state.turn,
                            "game_map": self.game_state.game_map,
                            "units": self.game_state.units,
                            "vp_tracker": self.game_state.vp_tracker,
                            "game_state": self.game_state,
                        },
                    }
                )

            # ✅ Close turn first
            self.runtime.end_turn()
            self.game_state = self.runtime.base_state

            # ✅ NOW check match end
            if self.runtime.is_match_over():
                reward = (
                    self.game_state.vp_tracker.total_points
                    if self.game_state.vp_tracker
                    else 0
                )
                return self.game_state, reward, True, {}

            # ✅ Start next turn only if match continues
            self.runtime.start_turn()
            self.game_state = self.runtime.base_state

            reward = (
                self.game_state.vp_tracker.total_points
                if self.game_state.vp_tracker
                else 0
            )
            return self.game_state, reward, False, {}

        # -------------------------------------------------
        # CONTINUE TURN
        # -------------------------------------------------
        reward = (
            self.game_state.vp_tracker.total_points
            if self.game_state.vp_tracker
            else 0
        )

        return self.game_state, reward, False, {}
