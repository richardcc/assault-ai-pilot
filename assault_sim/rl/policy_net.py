import torch
import torch.nn as nn
import torch.nn.functional as F


class PolicyNet(nn.Module):
    """
    PPO Policy Network with dual decision heads.

    Outputs:
    - option_logits
    - attack_mode_logits
    - value
    """

    def __init__(self, input_dim: int, num_options: int):
        super().__init__()

        # -------------------------------------------------
        # ✅ SHARED ENCODER (MEJORADO)
        # -------------------------------------------------
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LayerNorm(128),          # ✅ estabilidad
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.LayerNorm(128),          # ✅ estabilidad
            nn.ReLU(),
        )

        # -------------------------------------------------
        # ✅ OPTION HEAD
        # -------------------------------------------------
        self.option_head = nn.Linear(128, num_options)

        # -------------------------------------------------
        # ✅ ATTACK MODE HEAD
        # -------------------------------------------------
        self.attack_mode_head = nn.Linear(128, 2)

        # -------------------------------------------------
        # ✅ VALUE HEAD
        # -------------------------------------------------
        self.value_head = nn.Linear(128, 1)

    # -------------------------------------------------
    def forward(self, x):

        features = self.backbone(x)

        option_logits = self.option_head(features)
        attack_mode_logits = self.attack_mode_head(features)
        value = self.value_head(features)

        return option_logits, attack_mode_logits, value
