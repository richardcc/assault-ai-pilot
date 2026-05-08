import json
import os
from pathlib import Path

from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import hex_distance
from assault_sim.rl.state_encoder import encode_state


# -------------------------------------------------
# DEBUG TRACE
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class TrainingEnv:
    """
    Non-intrusive wrapper around SimEnv.

    Reward logic ONLY.
    No rules, no mechanics, no action selection.

    ✅ Includes:
    - directional movement reward
    - combat metrics
    """

    def __init__(
        self,
        sim_env,
        env_config_path: Path,
        scenario_override: str | None = None,
    ):
        self.sim = sim_env

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = json.load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        self.scenario_override = scenario_override
        self.current_step = 0

        # ---- reward memory ----
        self.prev_vp = 0
        self.prev_enemy_dist = None

        # ---- 📊 COMBAT METRICS ----
        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.heuristic_attacks = 0
        self.heuristic_damage = 0
        self.heuristic_kills = 0

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):
        state = self.sim.reset()

        self.current_step = 0
        self.prev_vp = state.vp_tracker.total_points if state.vp_tracker else 0
        self.prev_enemy_dist = None

        return encode_state(
            state,
            rl_side="US",
            max_turns=self.sim.scenario.max_turns,
        )

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        state = self.sim.game_state
        active = state.active_unit

        # Guard coherencia
        if active is None:
            action = None
        elif action is not None and action.unit_id != active.unit_id:
            action = WaitAction(active.unit_id)

        # -------------------------------------------------
        # 🔴 PRE-ACTION DISTANCE (KEY FIX)
        # -------------------------------------------------
        own_units = [u for u in state.units if u.alive and u.side == "US"]
        enemy_units = [u for u in state.units if u.alive and u.side != "US"]

        pre_dist = None
        if own_units and enemy_units:
            pre_dist = min(
                hex_distance(us.position, ge.position)
                for us in own_units
                for ge in enemy_units
            )

        # -------------------------------------------------
        # EXECUTION
        # -------------------------------------------------
        next_state, _, sim_done, info = self.sim.step(action)

        # -------------------------------------------------
        # COMBAT METRICS
        # -------------------------------------------------
        if isinstance(info, dict):
            dmg = info.get("damage", 0)
            killed = info.get("defender_killed", False)

            if dmg > 0:
                if active and active.side == "US":
                    self.rl_attacks += 1
                    self.rl_damage += dmg
                else:
                    self.heuristic_attacks += 1
                    self.heuristic_damage += dmg

            if killed:
                if active and active.side == "US":
                    self.rl_kills += 1
                else:
                    self.heuristic_kills += 1

        # -------------------------------------------------
        # BASE REWARD — VP DELTA
        # -------------------------------------------------
        current_vp = (
            next_state.vp_tracker.total_points
            if next_state.vp_tracker else 0
        )
        reward = current_vp - self.prev_vp
        self.prev_vp = current_vp

        # -------------------------------------------------
        # COMBAT REWARD
        # -------------------------------------------------
        if isinstance(info, dict):
            reward += 0.5 * info.get("damage", 0)
            if info.get("defender_killed"):
                reward += 3.0

        # -------------------------------------------------
        # 🔴 DIRECTIONAL MOVEMENT REWARD (CRITICAL FIX)
        # -------------------------------------------------
        next_own_units = [u for u in next_state.units if u.alive and u.side == "US"]
        next_enemy_units = [u for u in next_state.units if u.alive and u.side != "US"]

        if pre_dist is not None and next_own_units and next_enemy_units:
            post_dist = min(
                hex_distance(us.position, ge.position)
                for us in next_own_units
                for ge in next_enemy_units
            )

            delta = pre_dist - post_dist
            reward += 0.1 * delta   # ✅ local gradient

            self.prev_enemy_dist = post_dist

        # -------------------------------------------------
        # WAIT PENALTY
        # -------------------------------------------------
        if isinstance(action, WaitAction) and enemy_units:
            reward -= 0.05

        # -------------------------------------------------
        # EPISODE CONTROL
        # -------------------------------------------------
        self.current_step += 1
        done = sim_done

        if self.max_steps is not None and self.current_step >= self.max_steps:
            done = True

        return (
            encode_state(
                next_state,
                rl_side="US",
                max_turns=self.sim.scenario.max_turns,
            ),
            reward,
            done,
            info,
        )