# assault_sim/training_env.py

import json
import os
from pathlib import Path

from assault_model.actions.status import WaitAction


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
    Wrapper NO intrusivo sobre SimEnv.

    - No modifica SimEnv
    - No toca debug ni observers
    - Coordina ejecución y reward
    - GARANTIZA coherencia action <-> active_unit
    """

    def __init__(self, sim_env, env_config_path: Path):
        self.sim = sim_env  # SimEnv REAL

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = json.load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        self.current_step = 0
        self.prev_vp = None

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):
        obs = self.sim.reset()

        self.current_step = 0

        if obs.vp_tracker:
            self.prev_vp = obs.vp_tracker.total_points
        else:
            self.prev_vp = 0

        return obs

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        """
        Delegación a SimEnv.step() con BLINDAJE + TRAZA.
        """

        state = self.sim.game_state
        active = state.active_unit

        # ---------- ACTION BIND TRACE (NUEVO) ----------
        _trace(
            "ACTION_IN",
            active=active.unit_id if active else None,
            action=getattr(action, "unit_id", None),
        )

        # ---------- BLINDAJE FUNDAMENTAL ----------
        if active is None:
            _trace("ACTION_BIND", result="no_active_unit")
            action = None

        elif action is None:
            _trace(
                "ACTION_BIND",
                active=active.unit_id,
                action=None,
                result="fixed_wait",
            )
            action = WaitAction(active.unit_id)

        elif action.unit_id != active.unit_id:
            _trace(
                "ACTION_BIND",
                active=active.unit_id,
                action=action.unit_id,
                result="fixed_wait",
            )
            action = WaitAction(active.unit_id)

        else:
            _trace(
                "ACTION_BIND",
                active=active.unit_id,
                action=action.unit_id,
                result="ok",
            )

        # ---------- EJECUCIÓN ----------
        obs, _, sim_done, info = self.sim.step(action)

        # ---------- REWARD ----------
        if obs.vp_tracker:
            current_vp = obs.vp_tracker.total_points
        else:
            current_vp = 0

        reward = current_vp - self.prev_vp
        self.prev_vp = current_vp

        self.current_step += 1

        done = sim_done
        if self.max_steps is not None and self.current_step >= self.max_steps:
            done = True

        return obs, reward, done, info