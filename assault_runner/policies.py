# assault_runner/policies.py

import torch.nn as nn
from stable_baselines3.common.policies import MultiInputActorCriticPolicy

from assault.core.rationale import Rationale
from assault.core.actions.action_catalog import ACTION_CATALOG


# ==============================================================
# RL POLICY (EXPLAINABLE PPO)
# ==============================================================

class ExplainableActorCriticPolicy(MultiInputActorCriticPolicy):
    """
    PPO policy with an auxiliary rationale head.
    Used by training and inference.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.n_rationales = len(Rationale)

        self.rationale_head = nn.Linear(
            self.mlp_extractor.latent_dim_pi,
            self.n_rationales,
        )

        self.last_rationale_logits = None

    def _get_latent(self, features):
        latent_pi, latent_vf = self.mlp_extractor(features)
        self.last_rationale_logits = self.rationale_head(latent_pi)
        return latent_pi, latent_vf


# ==============================================================
# HEURISTIC ENEMY (DEFENSIVE, OBS-ONLY, EXTENDED)
# ==============================================================

class HeuristicEnemy:
    """
    Defensive heuristic enemy.

    Properties:
    - Uses ONLY obs (fair vs RL)
    - Tries to shoot when possible
    - Avoids close-range suicide
    - Moves towards VP when safe
    - Deterministic (no randomness)
    """

    name = "heuristic_enemy"

    def __init__(self):
        self.actions = {a.name: i for i, a in enumerate(ACTION_CATALOG)}

        self.MOVE_E = self.actions["MOVE_E"]
        self.MOVE_W = self.actions["MOVE_W"]
        self.MOVE_N = self.actions["MOVE_N"]
        self.MOVE_S = self.actions["MOVE_S"]
        self.RANGED_FIRE = self.actions.get("RANGED_FIRE")

    def act(self, obs) -> int:
        # ------------------------------
        # Read observation
        # ------------------------------
        dx = float(obs["dx_vp"][0])
        dy = float(obs["dy_vp"][0])
        enemy_dist = float(obs.get("enemy_dist", [50.0])[0])

        # ------------------------------
        # 1. If enemy in firing range → FIRE
        # ------------------------------
        # Conservative threshold (avoid melee)
        if self.RANGED_FIRE is not None and 2 <= enemy_dist <= 5:
            return self.RANGED_FIRE

        # ------------------------------
        # 2. If enemy too close → RETREAT
        # ------------------------------
        if enemy_dist < 2:
            # Move away from enemy / VP direction
            if abs(dx) >= abs(dy):
                return self.MOVE_W if dx > 0 else self.MOVE_E
            else:
                return self.MOVE_S if dy > 0 else self.MOVE_N

        # ------------------------------
        # 3. Move towards VP (objective play)
        # ------------------------------
        if abs(dx) >= abs(dy):
            return self.MOVE_E if dx > 0 else self.MOVE_W
        else:
            return self.MOVE_N if dy > 0 else self.MOVE_S
