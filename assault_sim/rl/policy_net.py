# assault_sim/rl/policy_net.py

import torch
import torch.nn as nn


class PolicyNet(nn.Module):
    """
    Actor-Critic network.

    Outputs:
    - policy logits (for action selection)
    - state value (for critic)
    """

    def __init__(self, input_dim, max_actions):
        super().__init__()

        # ✅ DEBUG prints (solo temporales)
        self.shared = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
        )
        # Actor head
        self.policy_head = nn.Linear(64, max_actions)

        # Critic head
        self.value_head = nn.Linear(64, 1)

    def forward(self, x):
        features = self.shared(x)

        logits = self.policy_head(features)
        value = self.value_head(features).squeeze(-1)

        return logits, value
