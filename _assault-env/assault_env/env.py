import json
import os
import random
import numpy as np
import gymnasium
from gymnasium import spaces

from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.unit import Unit, Experience
from assault.core.turns.activation_controller import ActivationController

from assault.core.actions.action_catalog import ACTION_CATALOG
from assault.core.actions.movement_action import MovementAction
from assault.core.actions.movement_executor import MovementExecutor
from assault.core.actions.ranged_fire_action import RangedFireAction
from assault.core.actions.ranged_fire_executor import RangedFireExecutor
from assault.core.actions.assault_action import AssaultAction
from assault.core.actions.assault_executor import AssaultExecutor

from assault.core.combat.ranged_fire import RangedFireResolver
from assault.core.combat.assault import AssaultResolver

from assault_runner.policies import HeuristicEnemy
from assault_runner.explanation.textualizer import explain_action


class AssaultEnv(gymnasium.Env):
    metadata = {"render_modes": []}

    def __init__(self, *, scenario_id: str, rl_side: str = "A", seed: int = 0, debug: bool = False):
        super().__init__()

        self.DEBUG = debug
        self.scenario_id = scenario_id
        self.rl_side = rl_side
        self.rng = random.Random(seed)

        self.state = None
        self.activation_controller = None
        self.current_unit = None
        self.current_round = 1
        self.last_obs = None

        self.nationality_to_side = {"US": "A", "GE": "B"}

        base_dir = os.path.dirname(__file__)
        self.data_dir = os.path.abspath(
            os.path.join(base_dir, "..", "..", "assault-engine", "core", "data")
        )

        self.unit_catalog = self._load_unit_catalog()
        self.scenario = self._load_scenario()

        self.ranged_fire_resolver = RangedFireResolver(self.unit_catalog, self.rng)
        self.assault_resolver = AssaultResolver(self.unit_catalog, self.rng)
        self.heuristic = HeuristicEnemy()

        self.observation_space = spaces.Dict({
            "dx_vp": spaces.Box(-20, 20, (1,), np.float32),
            "dy_vp": spaces.Box(-20, 20, (1,), np.float32),
            "on_vp": spaces.Box(0, 1, (1,), np.float32),
            "vp_owned": spaces.Box(0, 1, (1,), np.float32),
            "enemy_dist": spaces.Box(0, 50, (1,), np.float32),
        })
        self.action_space = spaces.Discrete(len(ACTION_CATALOG))

    # --------------------------------------------------
    def _debug(self, *args):
        if self.DEBUG:
            print(*args)

    def _load_unit_catalog(self):
        with open(os.path.join(self.data_dir, "unit_catalog.json"), encoding="utf-8") as f:
            return json.load(f)

    def _load_scenario(self):
        with open(os.path.join(self.data_dir, "scenarios", f"{self.scenario_id}.json"), encoding="utf-8") as f:
            return json.load(f)

    def _serialize_combat(self, combat_info):
        return None if combat_info is None else {
            "type": combat_info.__class__.__name__,
            "rolls": combat_info.rolls,
            "effects": combat_info.effects,
        }

    def _build_obs(self, unit: Unit) -> dict:
        ux, uy = unit.position
        enemy_dists = [
            abs(ux - e.position[0]) + abs(uy - e.position[1])
            for side, units in self.state.units.items()
            if side != unit.side
            for e in units.values()
            if e.is_alive()
        ]
        obs = {
            "dx_vp": np.array([0.0], np.float32),
            "dy_vp": np.array([0.0], np.float32),
            "on_vp": np.array([False], np.float32),
            "vp_owned": np.array([False], np.float32),
            "enemy_dist": np.array([min(enemy_dists) if enemy_dists else 50.0], np.float32),
        }
        self.last_obs = obs
        return obs

    # --------------------------------------------------
    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self.rng.seed(seed)

        self._debug("\n=== ASSAULT ENV START ===")
        self._debug(f"Side A (US): {'RL agent' if self.rl_side == 'A' else 'Heuristic enemy'}")
        self._debug(f"Side B (GE): {'RL agent' if self.rl_side == 'B' else 'Heuristic enemy'}")
        self._debug("========================\n")

        self.state = GameState()
        self.current_round = 1
        self.last_obs = None

        size = self.scenario["map"]["size"]
        for q in range(size["q_min"], size["q_max"] + 1):
            for r in range(size["r_min"], size["r_max"] + 1):
                self.state.add_hex(Hex(q=q, r=r, terrain="clear"))

        for u in self.scenario["units"]:
            side_id = self.nationality_to_side[u["side"]]
            card = self.unit_catalog[u["unit_key"]]
            unit = Unit(
                unit_id=u["unit_id"],
                unit_key=u["unit_key"],
                strength=card["max_strength"],
                position=tuple(u["position"]),
                experience=Experience[u.get("experience", "REGULAR")],
                statuses=set(),
            )
            unit.side = side_id
            unit.nationality = u["side"]
            self.state.add_unit(side_id, unit)
            self._debug(f"INIT UNIT {unit.unit_id} nationality={u['side']} side={side_id} pos={unit.position}")

        self._debug("\nUNITS BY SIDE:")
        for side, units in self.state.units.items():
            self._debug(f"  SIDE {side}:")
            for u in units.values():
                self._debug(f"    {u.unit_id} | strength={u.strength} | pos={u.position} | alive={u.is_alive()}")
        self._debug("")

        self.activation_controller = ActivationController(
            units_by_side=self.state.units,
            starting_side=list(self.state.units.keys())[0],
        )

        self.current_unit = self.activation_controller.next_unit_to_activate()
        self._debug(f"START ROUND 1 | first activation: {self.current_unit.unit_id}")

        return self._build_obs(self.current_unit), {}

    # --------------------------------------------------
    def step(self, action_index: int):
        frames = []
        reward = 0.0

        # ---- END MATCH BY MAX TURNS ----
        if self.current_round > self.scenario["max_turns"]:
            self._debug(f"END_MATCH reached max turns ({self.scenario['max_turns']})")
            self.state.update_vp_control()
            return self.last_obs, reward, True, False, {"frames": frames, "terminal": True}

        # ---- END TURN ----
        if self.current_unit is None:
            self._debug(f"END_TURN round {self.current_round}")
            self.state.update_vp_control()
            self.current_round += 1
            self.activation_controller.start_next_round()
            self.current_unit = self.activation_controller.next_unit_to_activate()
            obs = self._build_obs(self.current_unit) if self.current_unit else self.last_obs
            return obs, reward, False, False, {"frames": frames}

        unit = self.current_unit
        combat_info = None
        prev_state = self.state.snapshot()

        if unit.side != self.rl_side:
            action_index = int(self.heuristic.act(self.last_obs))

        spec = ACTION_CATALOG[int(action_index)]
        self._debug(f"ACTIVATE {unit.unit_id} side={unit.side} ACTION={spec.name}")

        if spec.name.startswith("MOVE_"):
            dq, dr = {"MOVE_E": (1,0), "MOVE_W":(-1,0), "MOVE_N":(0,1), "MOVE_S":(0,-1)}[spec.name]
            executor = MovementExecutor(self.state)
            action = MovementAction((unit.position[0]+dq, unit.position[1]+dr))
            if executor.can_execute(unit=unit, action=action):
                executor.execute(unit=unit, action=action)

        elif spec.name == "RANGED_FIRE":
            executor = RangedFireExecutor(self.state, self.ranged_fire_resolver)
            action = RangedFireAction()
            for side, units in self.state.units.items():
                if side != unit.side:
                    for enemy in units.values():
                        if enemy.is_alive() and executor.can_execute(attacker=unit, defender=enemy, action=action):
                            combat_info = executor.execute(attacker=unit, defender=enemy, action=action)
                            self._debug(f"[COMBAT:RANGED] {unit.unit_id} -> {enemy.unit_id}")
                            self._debug(f"  rolls: {combat_info.rolls}")
                            self._debug(f"  effects: {combat_info.effects}")
                            break

        elif spec.name == "ASSAULT":
            executor = AssaultExecutor(self.assault_resolver)
            action = AssaultAction()
            for side, units in self.state.units.items():
                if side != unit.side:
                    for enemy in units.values():
                        if enemy.is_alive():
                            combat_info = executor.execute(attacker=unit, defender=enemy, action=action)
                            if combat_info:
                                self._debug(f"[COMBAT:ASSAULT] {unit.unit_id} -> {enemy.unit_id}")
                                self._debug(f"  rolls: {combat_info.rolls}")
                                self._debug(f"  effects: {combat_info.effects}")
                            break
                    break

        frames.append({
            "round": self.current_round,
            "unit_id": unit.unit_id,
            "action": spec.name,
            "combat": self._serialize_combat(combat_info),
        })

        explanation = explain_action(prev_state=prev_state, next_state=self.state.snapshot(),
                                     unit_id=unit.unit_id, action=spec.name, report=combat_info, lang="en")
        if explanation:
            self._debug(f"[RATIONALE] {explanation}")

        self.activation_controller.mark_activated(unit)
        self.current_unit = self.activation_controller.next_unit_to_activate()
        return self._build_obs(self.current_unit) if self.current_unit else self.last_obs, reward, False, False, {"frames": frames}