from __future__ import annotations

import torch
from torch import nn

from agents.efficientzero_v2.core.network_base import EfficientZeroV2BaseNetwork


class EfficientZeroV2Network(EfficientZeroV2BaseNetwork):
    """
    Optimized EfficientZero V2 network with compact consistency projection bottleneck.
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
        objective_intent_classes: int = 0,
        multi_vp_feature_dim: int = 0,
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
            objective_intent_classes=objective_intent_classes,
            multi_vp_feature_dim=multi_vp_feature_dim,
        )
        self.consistency_proj_dim = int(max(16, consistency_proj_dim))
        if self.encoder_type == "cnn":
            proj_channels = max(8, self.hidden_dim // 4)
            self.consistency_projection = nn.Sequential(
                nn.Conv2d(self.hidden_dim, proj_channels, kernel_size=1, bias=False),
                nn.SiLU(),
                nn.AdaptiveAvgPool2d((4, 4)),
                nn.Flatten(start_dim=1),
                nn.Linear(proj_channels * 4 * 4, self.consistency_proj_dim),
                nn.SiLU(),
                nn.Linear(self.consistency_proj_dim, self.consistency_proj_dim),
            )
        else:
            self.consistency_projection = nn.Sequential(
                nn.Linear(self.hidden_dim, self.consistency_proj_dim),
                nn.SiLU(),
                nn.Linear(self.consistency_proj_dim, self.consistency_proj_dim),
            )

    def consistency_embedding(self, hidden: torch.Tensor) -> torch.Tensor:
        if self.encoder_type != "cnn" and hidden.dim() > 2:
            hidden = torch.flatten(hidden, start_dim=1)
        z = self.consistency_projection(hidden)
        return torch.nn.functional.normalize(z, dim=-1)
