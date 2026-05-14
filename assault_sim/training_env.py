import json
import os
from pathlib import Path
from typing import Dict

from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import hex_distance
from assault_sim.rl.state_encoder import encode_state
from assault_sim.rewards.aggressive_reward import AggressiveReward


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class TrainingEnv:

    def __init__(
        self,
        sim_env,
        env_config_path: Path,
        rl_side: str,
        scenario_override: str | None = None,
    ):
        self.sim = sim_env
        self.rl_side = rl_side

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = json.load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        self.scenario_override = scenario_override
        self.current_step = 0

        self.reward_fn = AggressiveReward(rl_side)

        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.heuristic_attacks = 0
        self.heuristic_damage = 0
        self.heuristic_kills = 0

    # -------------------------------------------------
    # API LIMPIA (IMPORTANTE)
    # -------------------------------------------------
    @property
    def state(self):
        return self.sim.game_state

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):
        state = self.sim.reset()

        self.current_step = 0
        self.reward_fn.reset(state)

        return encode_state(
            state,
            rl_side=self.rl_side,
            max_turns=self.sim.scenario.max_turns,
        )

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        state = self.sim.game_state

        if state is None:
            raise RuntimeError("GameState is None")

        active = state.active_unit

        actor_side = active.side if active else None

        # -----------------------------
        # COHERENCE
        # -----------------------------
        if active is None:
            action = None
        elif action is not None and action.unit_id != active.unit_id:
            action = WaitAction(active.unit_id)

        # -----------------------------
        # SNAPSHOT BEFORE
        # -----------------------------
        hp_before: Dict[str, int] = {}
        alive_before: Dict[str, bool] = {}

        for u in state.units:
            hp_before[u.unit_id] = getattr(u, "hp", 0)
            alive_before[u.unit_id] = bool(u.alive)

        own_units = [u for u in state.units if u.alive and u.side == self.rl_side]
        enemy_units = [u for u in state.units if u.alive and u.side != self.rl_side]

        pre_dist = None
        if own_units and enemy_units:
            pre_dist = min(
                hex_distance(us.position, ge.position)
                for us in own_units for ge in enemy_units
            )

        # -----------------------------
        # STEP
        # -----------------------------
        next_state, _, sim_done, _ = self.sim.step(action)

        action_name = action.__class__.__name__ if action else ""
        is_attack = ("Ranged" in action_name) or ("Close" in action_name)

        if actor_side and is_attack:
            if actor_side == self.rl_side:
                self.rl_attacks += 1
            else:
                self.heuristic_attacks += 1

        # -----------------------------
        # SNAPSHOT AFTER
        # -----------------------------
        hp_after: Dict[str, int] = {}
        alive_after: Dict[str, bool] = {}

        for u in next_state.units:
            hp_after[u.unit_id] = getattr(u, "hp", 0)
            alive_after[u.unit_id] = bool(u.alive)

        # -----------------------------
        # DAMAGE & KILLS
        # -----------------------------
        for unit_id, before_hp in hp_before.items():
            after_hp = hp_after.get(unit_id, before_hp)
            damage = max(0, before_hp - after_hp)

            if damage > 0:
                if actor_side == self.rl_side:
                    self.rl_damage += damage
                else:
                    self.heuristic_damage += damage

            if alive_before.get(unit_id, False) and not alive_after.get(unit_id, True):
                if actor_side == self.rl_side:
                    self.rl_kills += 1
                else:
                    self.heuristic_kills += 1

        _trace(
            "COMBAT_SNAPSHOT",
            action=action_name,
            rl_damage=self.rl_damage,
            heuristic_damage=self.heuristic_damage,
            rl_kills=self.rl_kills,
            heuristic_kills=self.heuristic_kills,
        )

        # -----------------------------
        # DIST POST
        # -----------------------------
        next_own = [u for u in next_state.units if u.alive and u.side == self.rl_side]
        next_enemy = [u for u in next_state.units if u.alive and u.side != self.rl_side]

        post_dist = None
        if next_own and next_enemy:
            post_dist = min(
                hex_distance(us.position, ge.position)
                for us in next_own for ge in next_enemy
            )

        # -----------------------------
        # REWARD
        # -----------------------------
        reward = self.reward_fn.compute(
            state=state,
            next_state=next_state,
            action=action,
            active=active,
            info={},
            pre_dist=pre_dist,
            post_dist=post_dist,
        )

        # -----------------------------
        # DONE
        # -----------------------------
        self.current_step += 1
        done = sim_done

        if self.max_steps is not None and self.current_step >= self.max_steps:
            done = True

        info = {
            "rl_damage": self.rl_damage,
            "heuristic_damage": self.heuristic_damage,
            "rl_kills": self.rl_kills,
            "heuristic_kills": self.heuristic_kills,
            "done": done,
        }

        return (
            encode_state(
                next_state,
                rl_side=self.rl_side,
                max_turns=self.sim.scenario.max_turns,
            ),
            reward,
            done,
            info,
        )