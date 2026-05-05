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

    Responsibilities:
    - Forward reset() and step() calls to SimEnv.
    - Track episode progress (step count, VP delta rewards).
    - Validate coherence between an explicit action and the active unit.
    - NEVER decide gameplay actions.

    IMPORTANT (New Architecture Semantics):
    - action=None DOES NOT mean "wait".
      It means: "delegate action selection to SimEnv and its controller".
    - TrainingEnv MUST NOT replace action=None with WaitAction.
    - Action decision authority belongs exclusively to the controller
      (heuristic or policy) wired into SimEnv.

    Design Rule:
    - SimEnv decides WHEN an action is required.
    - Controller decides WHICH action to take.
    - TrainingEnv only coordinates execution and evaluates outcomes.
    """

    def __init__(self, sim_env, env_config_path: Path):
        self.sim = sim_env  # The real SimEnv instance

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = json.load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

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
            * None      → delegate decision to SimEnv (controller-driven).
            * Action    → must belong to the currently active unit.

        Behavior:
        - If there is no active unit, the action is ignored.
        - If an explicit action targets a non-active unit,
          it is safely replaced with WaitAction for the active unit.
        - If action is None, it is passed through unchanged so
          SimEnv can request an action from its controller.

        Notes:
        - This method does NOT select actions.
        - This method does NOT apply gameplay rules.
        - It only enforces action ↔ active_unit coherence and computes rewards.
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
        # IMPORTANT:
        # action=None is intentional and means:
        #   "Let SimEnv ask its controller (heuristic/policy) for the action."
        # TrainingEnv must NOT convert action=None into WaitAction.
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