from __future__ import annotations

import torch
from torch import nn


class ResidualMLPBlock(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.fc2 = nn.Linear(dim, dim)
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.act(self.fc1(x))
        z = self.fc2(z)
        return self.act(x + z)


class ResidualConvBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.act(self.conv1(x))
        z = self.conv2(z)
        return self.act(x + z)


class MuZeroNetwork(nn.Module):
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
                nn.Conv2d(self.observation_channels, self.hidden_dim, kernel_size=3, padding=1),
                nn.ReLU(),
            )
            self.representation_tower = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim) for _ in range(max(1, int(prediction_blocks)))]
            )
            self.action_embedding = nn.Embedding(self.action_dim, self.hidden_dim * self.observation_height * self.observation_width)
            self.dynamics_merge = nn.Sequential(
                nn.Linear(2 * self.hidden_dim * self.observation_height * self.observation_width, self.hidden_dim * self.observation_height * self.observation_width),
                nn.ReLU(),
            )
            self.dynamics_state = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim) for _ in range(max(1, int(dynamics_blocks)))]
            )
            self.prediction_trunk = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim) for _ in range(max(1, int(prediction_blocks)))]
            )
            flat_dim = self.hidden_dim * self.observation_height * self.observation_width
            self.dynamics_reward = nn.Sequential(
                nn.Linear(flat_dim, self.hidden_dim),
                nn.ReLU(),
                nn.Linear(self.hidden_dim, 1),
            )
            self.prediction_policy = nn.Linear(flat_dim, action_dim)
            self.prediction_value = nn.Linear(flat_dim, 1)
            self.prediction_objective = nn.Linear(flat_dim, 1)
        else:
            self.representation = nn.Sequential(
                nn.Linear(observation_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
            )
            self.dynamics_input = nn.Sequential(
                nn.Linear(hidden_dim + action_dim, hidden_dim),
                nn.ReLU(),
            )
            self.dynamics_state = nn.Sequential(
                *[ResidualMLPBlock(hidden_dim) for _ in range(self.dynamics_blocks)]
            )
            self.prediction_trunk = nn.Sequential(
                *[ResidualMLPBlock(hidden_dim) for _ in range(self.prediction_blocks)]
            )
            self.dynamics_reward = nn.Linear(hidden_dim, 1)
            self.prediction_policy = nn.Linear(hidden_dim, action_dim)
            self.prediction_value = nn.Linear(hidden_dim, 1)
            self.prediction_objective = nn.Linear(hidden_dim, 1)

    def initial_inference(self, observation: torch.Tensor, return_aux: bool = False):
        if self.encoder_type == "cnn":
            hidden = self.representation_tower(self.representation_input(observation))
            pred_hidden = self.prediction_trunk(hidden)
            pred_flat = torch.flatten(pred_hidden, start_dim=1)
            policy_logits = self.prediction_policy(pred_flat)
            value = self.prediction_value(pred_flat)
            reward = torch.zeros_like(value)
            objective_logit = self.prediction_objective(pred_flat)
        else:
            hidden = self.representation(observation)
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
            action_idx = torch.argmax(action_onehot, dim=-1)
            action_latent = self.action_embedding(action_idx).view(
                -1, self.hidden_dim, self.observation_height, self.observation_width
            )
            hidden_flat = torch.flatten(hidden, start_dim=1)
            action_flat = torch.flatten(action_latent, start_dim=1)
            merged = self.dynamics_merge(torch.cat([hidden_flat, action_flat], dim=-1))
            next_hidden = merged.view(-1, self.hidden_dim, self.observation_height, self.observation_width)
            next_hidden = self.dynamics_state(next_hidden)
            next_flat = torch.flatten(next_hidden, start_dim=1)
            reward = self.dynamics_reward(next_flat)
            pred_hidden = self.prediction_trunk(next_hidden)
            pred_flat = torch.flatten(pred_hidden, start_dim=1)
            policy_logits = self.prediction_policy(pred_flat)
            value = self.prediction_value(pred_flat)
            objective_logit = self.prediction_objective(pred_flat)
        else:
            x = torch.cat([hidden, action_onehot], dim=-1)
            next_hidden = self.dynamics_state(self.dynamics_input(x))
            reward = self.dynamics_reward(next_hidden)
            pred_hidden = self.prediction_trunk(next_hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            value = self.prediction_value(pred_hidden)
            objective_logit = self.prediction_objective(pred_hidden)
        if return_aux:
            return next_hidden, policy_logits, value, reward, {"objective_logit": objective_logit}
        return next_hidden, policy_logits, value, reward
