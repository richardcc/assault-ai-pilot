from __future__ import annotations

import torch
from torch import nn

from agents.efficientzero_v2.core.network_base import EfficientZeroV2BaseNetwork


class EfficientZeroV2Network(EfficientZeroV2BaseNetwork):
    """
    Migration-safe EfficientZero network scaffold.

    Current behavior is MuZero-compatible with an additional projection head that
    will be used by upcoming consistency losses.
    """

    def __init__(
        self,
        observation_dim: int,
        hidden_dim: int,
        action_dim: int,
        encoder_type: str = "mlp",
        observation_channels: int = 8,
        observation_height: int = 16,
        observation_width: int = 16,
        dynamics_blocks: int = 1,
        prediction_blocks: int = 1,
        consistency_proj_dim: int = 128,
    ):
        super().__init__(
            observation_dim=observation_dim,
            hidden_dim=hidden_dim,
            action_dim=action_dim,
            encoder_type=encoder_type,
            observation_channels=observation_channels,
            observation_height=observation_height,
            observation_width=observation_width,
            dynamics_blocks=dynamics_blocks,
            prediction_blocks=prediction_blocks,
        )
        self.consistency_proj_dim = int(max(16, consistency_proj_dim))
        if self.encoder_type == "cnn":
            in_dim = self.hidden_dim * self.observation_height * self.observation_width
        else:
            in_dim = self.hidden_dim
        self.consistency_projection = nn.Sequential(
            nn.Linear(in_dim, self.consistency_proj_dim),
            nn.ReLU(),
            nn.Linear(self.consistency_proj_dim, self.consistency_proj_dim),
        )

    def consistency_embedding(self, hidden: torch.Tensor) -> torch.Tensor:
        if self.encoder_type == "cnn":
            hidden = torch.flatten(hidden, start_dim=1)
        z = self.consistency_projection(hidden)
        return torch.nn.functional.normalize(z, dim=-1)

