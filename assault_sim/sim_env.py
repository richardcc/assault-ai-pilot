"""
Simulation Environment (SimEnv)

ROLE:
- High-level coordinator of the simulation loop.
- Bridges the engine (RuntimeGameState), AI/controllers, and observability.

RESPONSIBILITIES:
- Load catalogs and scenario data.
- Create the initial GameState and RuntimeGameState.
- Orchestrate reset and step cycles.
- Dispatch chosen actions to the engine.
- Emit observability events through EventBus.
- Decide episode termination (MATCH_END, max_turns).

NON-RESPONSIBILITIES:
- Does NOT define gameplay rules.
- Does NOT decide unit activation rules.
- Does NOT decide turn lifecycle semantics.
- Does NOT inspect ActionCatalog for rule inference.

DESIGN RULE:
- SimEnv orchestrates WHEN things happen.
- The engine decides WHAT happens.
"""

import json
import os

from assault_sim.config.config_loader import SimConfig
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.core.scenario_loader import load_scenario

from assault_model.state.game_state import GameState
from assault_model.runtime.game_state_runtime import RuntimeGameState

from assault_sim.debug.debug_config import DebugConfig
from assault_sim.debug.event_bus import EventBus


# -------------------------------------------------
# DEVELOPMENT TRACE (NOT OBSERVABILITY)
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class SimEnv:
    """
    High-level simulation environment.

    This class is pure orchestration.
    """

    def __init__(self, config: SimConfig, debug_config: DebugConfig | None = None):
        self.config = config
        self.debug_config = debug_config or DebugConfig(enabled=False)

        self.event_bus = EventBus() if self.debug_config.enabled else None

        self.scenario = None
        self.game_state: GameState | None = None
        self.runtime: RuntimeGameState | None = None
        self.player_config: dict[str, dict] = {}

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):
        """
        Fully reset the simulation.

        - Load catalogs and scenario.
        - Create GameState and RuntimeGameState.
        - Emit RESET / UNIT_LOADED / MAP_STATE events.
        """

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

        # Controller configuration (optional)
        env_config_path = root / "env_config.json"
        if env_config_path.exists():
            with open(env_config_path, "r", encoding="utf-8") as f:
                env_config = json.load(f)
                self.player_config = env_config.get("players", {})
        else:
            self.player_config = {}

        # -------------------------------------------------
        # OBSERVABILITY
        # -------------------------------------------------
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

        # Start first turn
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
        Apply a single external action (agent intent).
        """

        # ---- OBSERVABILITY: ACTION INTENT ----
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

        # ---- ENGINE EXECUTION ----
        self.runtime.apply_action(action)
        self.game_state = self.runtime.base_state

        _trace(
            "ACTIVE_UNIT",
            unit=self.game_state.active_unit.unit_id
            if self.game_state.active_unit
            else None,
        )

        # ---- MATCH END (single side remaining) ----
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

        # ---- TURN END (ENGINE DECIDES) ----
        if self.runtime.turn_has_ended():
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

            self.runtime.end_turn()
            self.runtime.start_turn()
            self.game_state = self.runtime.base_state

        # ---- EPISODE END (max turns) ----
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