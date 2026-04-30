"""
Rationale callback (OBSERVATIONAL ONLY).

IMPORTANT:
- This callback DOES NOT apply gradients.
- It does NOT train the rationale head.
- Rationale learning is implicit via PPO loss.
- This callback is for logging, analysis and debugging only.
"""

import os
import csv
import torch
from stable_baselines3.common.callbacks import BaseCallback

from assault_runner.rationale import (
    infer_rationale,
    decode_rationale_from_logits,
)


class RationaleLossCallback(BaseCallback):
    """
    Observational callback for explainable PPO.

    Responsibilities:
    - Explicitly call policy.forward()
    - Read rationale logits
    - Decode learned rationale
    - Emit rationale id for runtime consumption
    - Compare with heuristic baseline
    - Persist human-readable explanations

    ❌ Does NOT:
    - Backpropagate
    - Modify PPO loss
    """

    def __init__(self, verbose: int = 0, log_dir: str = "logs"):
        super().__init__(verbose)
        self.log_dir = log_dir
        self.csv_path = os.path.join(log_dir, "explanations.csv")
        self._csv_file = None
        self._csv_writer = None

    # --------------------------------------------------
    # Lifecycle hooks
    # --------------------------------------------------

    def _on_training_start(self):
        if self.verbose > 0:
            print("[RationaleCallback] Observational callback enabled")

        os.makedirs(self.log_dir, exist_ok=True)

        self._csv_file = open(
            self.csv_path, mode="w", newline="", encoding="utf-8"
        )
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "timestep",
            "unit_id",
            "action",
            "explanation",
        ])

    def _on_training_end(self):
        if self._csv_file:
            self._csv_file.close()

    # --------------------------------------------------
    # Main step hook
    # --------------------------------------------------

    def _on_step(self) -> bool:
        policy = self.model.policy

        # --------------------------------------------------
        # 1) Get current observation
        # --------------------------------------------------
        obs = self.locals.get("obs")
        if obs is None:
            return True

        # --------------------------------------------------
        # 2) Explicit forward pass (CRITICAL)
        # --------------------------------------------------
        with torch.no_grad():
            obs_tensor, _ = policy.obs_to_tensor(obs)
            outputs = policy.forward(obs_tensor)

            # Policy must return (action_dist, rationale_logits)
            if not isinstance(outputs, tuple) or len(outputs) != 2:
                return True

            _, rationale_logits = outputs
            if rationale_logits is None:
                return True

        # --------------------------------------------------
        # 3) Decode rationale (logits → int)
        # --------------------------------------------------
        learned_rationale = decode_rationale_from_logits(rationale_logits)
        learned_rationale = int(learned_rationale)

        # --------------------------------------------------
        # 4) Save for runtime / inference
        # --------------------------------------------------
        self.model._last_rationale_id = learned_rationale

        # --------------------------------------------------
        # 5) Access environment safely
        # --------------------------------------------------
        if self.training_env is None:
            return True

        env = self.training_env.envs[0]

        if not hasattr(env, "last_transition"):
            return True

        try:
            _, _, action_info = env.last_transition
        except Exception:
            return True

        unit_id = action_info.get("unit_id")
        action_name = action_info.get("action")
        explanation = action_info.get("explanation")

        if not explanation:
            return True

        # --------------------------------------------------
        # 6) Optional heuristic comparison
        # --------------------------------------------------
        prev_state, next_state, _ = env.last_transition
        heuristic = infer_rationale(prev_state, next_state, unit_id)

        # --------------------------------------------------
        # 7) Persist explanation to CSV
        # --------------------------------------------------
        if self._csv_writer:
            self._csv_writer.writerow([
                self.num_timesteps,
                unit_id,
                action_name,
                explanation,
            ])
            self._csv_file.flush()

        # --------------------------------------------------
        # 8) TensorBoard logging
        # --------------------------------------------------
        if self.logger:
            self.logger.record(
                "explanation/text",
                explanation,
                exclude=("stdout", "log", "json"),
            )

        # --------------------------------------------------
        # 9) Optional console output
        # --------------------------------------------------
        if self.verbose > 0:
            print(f"[Explanation] {explanation}")

        if self.verbose > 1:
            print(
                "[Rationale]"
                f" action={action_name} |"
                f" learned={learned_rationale} |"
                f" heuristic={heuristic}"
            )

        return True