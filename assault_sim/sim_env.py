# assault_sim/sim_env.py
#
# Simulation environment.
# Core logic only.
# NO direct printing.
# ALL visualization handled by observers.

import json

from assault_sim.config.config_loader import SimConfig
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.core.scenario_loader import load_scenario
from assault_model.core.game_state import GameState
from assault_model.core.game_state_runtime import RuntimeGameState
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.status import WaitAction
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.debug.event_bus import EventBus


class SimEnv:
    """
    High-level simulation environment.

    Responsibilities:
    - Load catalogs and scenario
    - Create GameState and RuntimeGameState
    - Emit structured events
    - Decide TURN_END and MATCH_END
    """

    def __init__(self, config: SimConfig, debug_config: DebugConfig | None = None):
        self.config = config
        self.debug_config = debug_config or DebugConfig(enabled=False)

        self.event_bus = EventBus() if self.debug_config.enabled else None

        self.scenario = None
        self.game_state = None
        self.runtime = None
        self.player_config: dict[str, dict] = {}

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
        self.runtime = RuntimeGameState(self.game_state)

        env_config_path = root / "env_config.json"
        if env_config_path.exists():
            with open(env_config_path, "r", encoding="utf-8") as f:
                env_config = json.load(f)
                self.player_config = env_config.get("players", {})
        else:
            self.player_config = {}

        if self.event_bus:
            self.game_state.event_bus = self.event_bus

            self.event_bus.emit(
                {
                    "type": "RESET",
                    "payload": {
                        "scenario": self.scenario.name,
                        "turn": self.game_state.turn,
                        "game_map": self.game_state.game_map,
                    },
                }
            )

            for unit in self.game_state.units:
                side_cfg = self.player_config.get(unit.side, {})
                self.event_bus.emit(
                    {
                        "type": "UNIT_LOADED",
                        "payload": {
                            "unit_id": unit.unit_id,
                            "side": unit.side,
                            "position": unit.position,
                            "controller": side_cfg.get("controller", "heuristic"),
                            "heuristic": side_cfg.get("heuristic", "HeuristicBase"),
                        },
                    }
                )

        # START FIRST TURN (TURN = 1)
        self.runtime.start_turn()
        self.game_state = self.runtime.base_state

        if self.event_bus:
            self.event_bus.emit(
                {
                    "type": "MAP_STATE",
                    "payload": {
                        "turn": self.game_state.turn,
                        "game_map": self.game_state.game_map,
                        "units": self.game_state.units,
                    },
                }
            )

        return self.game_state

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        """
        Apply one action and decide TURN_END and MATCH_END.
        """

        # ACTION event
        if self.event_bus and self.debug_config.log_actions:
            self.event_bus.emit(
                {
                    "type": "ACTION",
                    "payload": {
                        "turn": self.game_state.turn,
                        "action": action.__class__.__name__ if action else None,
                        "active_unit": (
                            self.game_state.active_unit.unit_id
                            if self.game_state.active_unit
                            else None
                        ),
                    },
                }
            )

        # Apply action
        self.runtime.apply_action(action)
        self.game_state = self.runtime.base_state

        # END-MATCH: last side standing
        alive_units = [u for u in self.game_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}

        if len(alive_sides) == 1:
            winner = next(iter(alive_sides))

            if self.event_bus:
                self.event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "winner": winner,
                            "reason": "last_side_standing",
                        },
                    }
                )

            reward = (
                self.game_state.vp_tracker.total_points
                if self.game_state.vp_tracker
                else 0
            )

            return self.game_state, reward, True, {}

        # END OF ACTIVATION (NOT TURN)
        if self.event_bus and self.debug_config.log_turns:
            self.event_bus.emit(
                {
                    "type": "TURN_STATE",
                    "payload": {
                        "turn": self.game_state.turn,
                        "active_unit": (
                            self.game_state.active_unit.unit_id
                            if self.game_state.active_unit
                            else None
                        ),
                    },
                }
            )

        # -------------------------------------------------
        # ✅ TURN_END (FORMAL CRITERION)
        # -------------------------------------------------
        if self._turn_has_ended():
            if self.event_bus:
                self.event_bus.emit(
                    {
                        "type": "TURN_END",
                        "payload": {
                            "turn": self.game_state.turn,
                            "reason": "no_activable_units",
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
                        },
                    }
                )

            # ✅ ADVANCE TURN CORRECTLY
            self.runtime.end_turn()     # incrementa turn
            self.runtime.start_turn()   # resetea activaciones
            self.game_state = self.runtime.base_state

        done = (
            self.scenario.max_turns is not None
            and self.game_state.turn > self.scenario.max_turns
        )

        reward = (
            self.game_state.vp_tracker.total_points
            if self.game_state.vp_tracker
            else 0
        )

        return self.game_state, reward, done, {}

    # =================================================
    # TURN-END CRITERION
    # =================================================
    def _turn_has_ended(self) -> bool:
        return len(self._activable_units()) == 0

    def _activable_units(self):
        gs = self.game_state
        catalog = ActionCatalog(gs)

        return [
            u
            for u in gs.units
            if self._is_unit_activable(u, gs, catalog)
        ]

    def _is_unit_activable(self, unit, gs, catalog) -> bool:
        if not unit.alive:
            return False

        if unit in gs.activation_state.activated:
            return False

        if getattr(unit, "suppressed", False):
            return False
        if getattr(unit, "fallback", False):
            return False

        prev_active = gs.activation_state.active_unit
        gs.activation_state.active_unit = unit
        try:
            actions = catalog.actions()
        finally:
            gs.activation_state.active_unit = prev_active

        real_actions = [a for a in actions if not isinstance(a, WaitAction)]
        return len(real_actions) > 0