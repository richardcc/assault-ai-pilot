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
    Non-intrusive wrapper around SimEnv.

    Purpose:
    - Acts as a thin coordination layer for training loops (RL or scripted).
    - Delegates ALL gameplay logic and action execution to SimEnv.
    - Computes rewards and enforces optional episode limits.

    IMPORTANT:
    - This class does NOT select gameplay actions.
    - This class does NOT modify SimEnv logic.
    - Observability / EventBus lifecycle is owned by SimEnv.
      TrainingEnv is intentionally agnostic to observability state.
    """

    def __init__(
        self,
        sim_env,
        env_config_path: Path,
        scenario_override: str | None = None,   # optional, not used yet
    ):
        self.sim = sim_env  # The real SimEnv instance

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = json.load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        # Stored for future use (curriculum / scenario selection)
        self.scenario_override = scenario_override

        self.current_step = 0
        self.prev_vp = 0

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):
        """
        Reset the environment and internal training state.

        Returns:
        - Initial observable GameState produced by SimEnv.
        """
        obs = self.sim.reset()

        self.current_step = 0
        self.prev_vp = obs.vp_tracker.total_points if obs.vp_tracker else 0

        return obs

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        """
        Execute one simulation step.

        Parameters:
        - action:
            * None   → delegate decision to SimEnv (controller-driven).
            * Action → must belong to the currently active unit.
        """

        state = self.sim.game_state
        active = state.active_unit

        _trace(
            "ACTION_IN",
            active=active.unit_id if active else None,
            action=getattr(action, "unit_id", None),
        )

        # -------------------------------------------------
        # ACTION COHERENCE GUARD
        # -------------------------------------------------
        # action=None MUST be passed through unchanged:
        # it means "let SimEnv ask its controller".
        if active is None:
            _trace("ACTION_BIND", result="no_active_unit")
            action = None

        elif action is not None and action.unit_id != active.unit_id:
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
                active=active.unit_id if active else None,
                action=getattr(action, "unit_id", None),
                result="ok_or_delegated",
            )

        # -------------------------------------------------
        # EXECUTION (DELEGATED TO SimEnv)
        # -------------------------------------------------
        obs, _, sim_done, info = self.sim.step(action)

        # -------------------------------------------------
        # REWARD COMPUTATION (VP DELTA)
        # -------------------------------------------------
        current_vp = obs.vp_tracker.total_points if obs.vp_tracker else 0
        reward = current_vp - self.prev_vp
        self.prev_vp = current_vp

        # -------------------------------------------------
        # EPISODE CONTROL
        # -------------------------------------------------
        self.current_step += 1

        done = sim_done
        if self.max_steps is not None and self.current_step >= self.max_steps:
            done = True

        return obs, reward, done, info