from __future__ import annotations

import torch
from torch import nn


def _make_group_norm(channels: int) -> nn.GroupNorm:
    num_groups = min(8, channels)
    while channels % num_groups != 0 and num_groups > 1:
        num_groups -= 1
    return nn.GroupNorm(num_groups, channels)


class ResidualMLPBlock(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.act1 = nn.SiLU()
        self.fc2 = nn.Linear(dim, dim)
        self.ln2 = nn.LayerNorm(dim)
        self.act2 = nn.SiLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.act1(self.ln1(self.fc1(x)))
        z = self.ln2(self.fc2(z))
        return self.act2(x + z)


class ResidualConvBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.gn1 = _make_group_norm(channels)
        self.act1 = nn.SiLU()
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.gn2 = _make_group_norm(channels)
        self.act2 = nn.SiLU()

        # Squeeze-and-Excitation (SE) channel attention gating
        se_dim = max(4, channels // 4)
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, se_dim, kernel_size=1),
            nn.SiLU(),
            nn.Conv2d(se_dim, channels, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.act1(self.gn1(self.conv1(x)))
        z = self.gn2(self.conv2(z))
        z = z * self.se(z)
        return self.act2(x + z)


class MuZeroNetwork(nn.Module):
    """
    Optimized MuZero network with GroupNorm, Squeeze-and-Excitation,
    1x1 Conv bottlenecks, and latent state scaling.
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
    ):
        super().__init__()
        self.encoder_type = str(encoder_type).lower().strip()
        self.observation_channels = int(observation_channels)
        self.observation_height = int(observation_height)
        self.observation_width = int(observation_width)
        self.hidden_dim = int(hidden_dim)
        self.action_dim = int(action_dim)
        self.latent_shape = (self.hidden_dim, self.observation_height, self.observation_width)
        self.dynamics_blocks = max(1, int(dynamics_blocks))
        self.prediction_blocks = max(1, int(prediction_blocks))

        if self.encoder_type == "cnn":
            self.representation_input = nn.Sequential(
                nn.Conv2d(self.observation_channels, self.hidden_dim, kernel_size=3, padding=1, bias=False),
                _make_group_norm(self.hidden_dim),
                nn.SiLU(),
            )
            self.representation_tower = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim) for _ in range(max(1, int(prediction_blocks)))]
            )
            self.action_plane_dim = max(4, min(self.hidden_dim, 16))
            self.action_embedding = nn.Embedding(self.action_dim, self.action_plane_dim)
            self.dynamics_merge = nn.Sequential(
                nn.Conv2d(
                    self.hidden_dim + self.action_plane_dim,
                    self.hidden_dim,
                    kernel_size=3,
                    padding=1,
                    bias=False,
                ),
                _make_group_norm(self.hidden_dim),
                nn.SiLU(),
            )
            self.dynamics_state = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim) for _ in range(max(1, int(dynamics_blocks)))]
            )
            self.prediction_trunk = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim) for _ in range(max(1, int(prediction_blocks)))]
            )

            # Conv 1x1 bottlenecks
            head_channels = max(8, self.hidden_dim // 4)
            val_channels = max(4, self.hidden_dim // 8)
            flat_policy_dim = head_channels * self.observation_height * self.observation_width
            flat_val_dim = val_channels * self.observation_height * self.observation_width

            self.dynamics_reward = nn.Sequential(
                nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                nn.SiLU(),
                nn.Flatten(start_dim=1),
                nn.Linear(flat_val_dim, 64),
                nn.SiLU(),
                nn.Linear(64, 1),
            )
            self.prediction_policy = nn.Sequential(
                nn.Conv2d(self.hidden_dim, head_channels, kernel_size=1),
                nn.SiLU(),
                nn.Flatten(start_dim=1),
                nn.Linear(flat_policy_dim, action_dim),
            )
            self.prediction_value = nn.Sequential(
                nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                nn.SiLU(),
                nn.Flatten(start_dim=1),
                nn.Linear(flat_val_dim, 64),
                nn.SiLU(),
                nn.Linear(64, 1),
            )
            self.prediction_objective = nn.Sequential(
                nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                nn.SiLU(),
                nn.Flatten(start_dim=1),
                nn.Linear(flat_val_dim, 1),
            )
        else:
            self.representation = nn.Sequential(
                nn.Linear(observation_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.SiLU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.SiLU(),
            )
            self.dynamics_input = nn.Sequential(
                nn.Linear(hidden_dim + action_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.SiLU(),
            )
            self.dynamics_state = nn.Sequential(
                *[ResidualMLPBlock(hidden_dim) for _ in range(self.dynamics_blocks)]
            )
            self.prediction_trunk = nn.Sequential(
                *[ResidualMLPBlock(hidden_dim) for _ in range(self.prediction_blocks)]
            )
            self.dynamics_reward = nn.Sequential(
                nn.Linear(hidden_dim, 64),
                nn.SiLU(),
                nn.Linear(64, 1),
            )
            self.prediction_policy = nn.Linear(hidden_dim, action_dim)
            self.prediction_value = nn.Sequential(
                nn.Linear(hidden_dim, 64),
                nn.SiLU(),
                nn.Linear(64, 1),
            )
            self.prediction_objective = nn.Linear(hidden_dim, 1)

    def _scale_latent(self, s: torch.Tensor) -> torch.Tensor:
        """Normalize latent state representation to prevent drift during MCTS unrolls."""
        if s.dim() == 4:
            b = s.shape[0]
            flat = s.view(b, -1)
            s_min = flat.min(dim=-1, keepdim=True)[0].view(b, 1, 1, 1)
            s_max = flat.max(dim=-1, keepdim=True)[0].view(b, 1, 1, 1)
            denom = (s_max - s_min).clamp(min=1e-5)
            return (s - s_min) / denom
        elif s.dim() == 2:
            s_min = s.min(dim=-1, keepdim=True)[0]
            s_max = s.max(dim=-1, keepdim=True)[0]
            denom = (s_max - s_min).clamp(min=1e-5)
            return (s - s_min) / denom
        return s

    def initial_inference(self, observation: torch.Tensor, return_aux: bool = False):
        if self.encoder_type == "cnn":
            hidden = self._scale_latent(self.representation_tower(self.representation_input(observation)))
            pred_hidden = self.prediction_trunk(hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            value = self.prediction_value(pred_hidden)
            reward = torch.zeros_like(value)
            objective_logit = self.prediction_objective(pred_hidden)
        else:
            hidden = self._scale_latent(self.representation(observation))
            pred_hidden = self.prediction_trunk(hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            value = self.prediction_value(pred_hidden)
            reward = torch.zeros_like(value)
            objective_logit = self.prediction_objective(pred_hidden)
        if return_aux:
            return hidden, policy_logits, value, reward, {"objective_logit": objective_logit}
        return hidden, policy_logits, value, reward

    def recurrent_inference(self, hidden: torch.Tensor, action_onehot: torch.Tensor, return_aux: bool = False):
        if self.encoder_type == "cnn":
            if action_onehot.dim() == 1:
                action_emb = self.action_embedding(action_onehot.long())
            elif action_onehot.dim() == 2:
                if action_onehot.shape[-1] == 1:
                    action_emb = self.action_embedding(action_onehot.squeeze(-1).long())
                else:
                    action_emb = torch.matmul(action_onehot.float(), self.action_embedding.weight)
            else:
                action_idx = torch.argmax(action_onehot, dim=-1)
                action_emb = self.action_embedding(action_idx.long())

            action_planes = action_emb.unsqueeze(-1).unsqueeze(-1).expand(
                -1, -1, self.observation_height, self.observation_width
            )
            merged = self.dynamics_merge(torch.cat([hidden, action_planes], dim=1))
            next_hidden = self._scale_latent(self.dynamics_state(merged))
            reward = self.dynamics_reward(next_hidden)
            pred_hidden = self.prediction_trunk(next_hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            value = self.prediction_value(pred_hidden)
            objective_logit = self.prediction_objective(pred_hidden)
        else:
            x = torch.cat([hidden, action_onehot], dim=-1)
            next_hidden = self._scale_latent(self.dynamics_state(self.dynamics_input(x)))
            reward = self.dynamics_reward(next_hidden)
            pred_hidden = self.prediction_trunk(next_hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            value = self.prediction_value(pred_hidden)
            objective_logit = self.prediction_objective(pred_hidden)
        if return_aux:
            return next_hidden, policy_logits, value, reward, {"objective_logit": objective_logit}
        return next_hidden, policy_logits, value, reward
