from __future__ import annotations

import torch
from torch import nn

from agents.efficientzero_v2.core.support import support_to_scalar


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


class SpatialAttentionBlock(nn.Module):
    """
    Spatial Attention Bottleneck: Computes 1x1 projection, GroupNorm, and a spatial
    gating map followed by AdaptiveAvgPool2d to preserve spatial topology while reducing dimension.
    """
    def __init__(self, in_channels: int, out_channels: int, pool_size: tuple[int, int] = (4, 4)):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False)
        self.norm = _make_group_norm(out_channels)
        self.act = nn.SiLU()
        self.spatial_gate = nn.Sequential(
            nn.Conv2d(out_channels, 1, kernel_size=1),
            nn.Sigmoid(),
        )
        self.pool = nn.AdaptiveAvgPool2d(pool_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.act(self.norm(self.conv(x)))
        gate = self.spatial_gate(h)
        return self.pool(h * gate)


class EfficientZeroV2BaseNetwork(nn.Module):
    """
    Local base network for EZv2 with GroupNorm, Squeeze-and-Excitation,
    1x1 Conv bottlenecks, spatial attention pooling, two-hot support, and latent state stabilization.
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
        objective_intent_classes: int = 0,
        multi_vp_feature_dim: int = 0,
        support_size: int = 0,
        use_spatial_attention: bool = False,
        enable_threat_head: bool = True,
        enable_attrition_head: bool = True,
        enable_morale_head: bool = True,
        morale_classes: int = 4,
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
        self.objective_intent_classes = max(0, int(objective_intent_classes))
        self.multi_vp_feature_dim = max(0, int(multi_vp_feature_dim))
        self.support_size = max(0, int(support_size))
        self.use_spatial_attention = bool(use_spatial_attention)
        self.enable_threat_head = bool(enable_threat_head)
        self.enable_attrition_head = bool(enable_attrition_head)
        self.enable_morale_head = bool(enable_morale_head)
        self.morale_classes = max(2, int(morale_classes))
        self.val_out_dim = (2 * self.support_size + 1) if self.support_size > 0 else 1

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

            head_channels = max(8, self.hidden_dim // 4)
            val_channels = max(4, self.hidden_dim // 8)

            if self.use_spatial_attention:
                pool_h, pool_w = 4, 4
                flat_policy_dim = head_channels * pool_h * pool_w
                flat_val_dim = val_channels * pool_h * pool_w
                self.dynamics_reward = nn.Sequential(
                    SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                    nn.Flatten(start_dim=1),
                    nn.Linear(flat_val_dim, 64),
                    nn.SiLU(),
                    nn.Linear(64, self.val_out_dim),
                )
                self.prediction_policy = nn.Sequential(
                    SpatialAttentionBlock(self.hidden_dim, head_channels, (pool_h, pool_w)),
                    nn.Flatten(start_dim=1),
                    nn.Linear(flat_policy_dim, action_dim),
                )
                self.prediction_value = nn.Sequential(
                    SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                    nn.Flatten(start_dim=1),
                    nn.Linear(flat_val_dim, 64),
                    nn.SiLU(),
                    nn.Linear(64, self.val_out_dim),
                )
                self.prediction_objective = nn.Sequential(
                    SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                    nn.Flatten(start_dim=1),
                    nn.Linear(flat_val_dim, 1),
                )
                self.prediction_intent = (
                    nn.Sequential(
                        SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, self.objective_intent_classes),
                    )
                    if self.objective_intent_classes > 0
                    else None
                )
                self.prediction_multi_vp = (
                    nn.Sequential(
                        SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, self.multi_vp_feature_dim),
                    )
                    if self.multi_vp_feature_dim > 0
                    else None
                )
                self.prediction_threat_map = (
                    nn.Sequential(
                        nn.Conv2d(self.hidden_dim, 16, kernel_size=3, padding=1, bias=False),
                        _make_group_norm(16),
                        nn.SiLU(),
                        nn.Conv2d(16, 1, kernel_size=1),
                    )
                    if self.enable_threat_head
                    else None
                )
                self.prediction_attrition = (
                    nn.Sequential(
                        SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, 64),
                        nn.SiLU(),
                        nn.Linear(64, 2),
                    )
                    if self.enable_attrition_head
                    else None
                )
                self.prediction_morale = (
                    nn.Sequential(
                        SpatialAttentionBlock(self.hidden_dim, val_channels, (pool_h, pool_w)),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, 64),
                        nn.SiLU(),
                        nn.Linear(64, self.morale_classes),
                    )
                    if self.enable_morale_head
                    else None
                )
            else:
                flat_policy_dim = head_channels * self.observation_height * self.observation_width
                flat_val_dim = val_channels * self.observation_height * self.observation_width

                self.dynamics_reward = nn.Sequential(
                    nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                    nn.SiLU(),
                    nn.Flatten(start_dim=1),
                    nn.Linear(flat_val_dim, 64),
                    nn.SiLU(),
                    nn.Linear(64, self.val_out_dim),
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
                    nn.Linear(64, self.val_out_dim),
                )
                self.prediction_objective = nn.Sequential(
                    nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                    nn.SiLU(),
                    nn.Flatten(start_dim=1),
                    nn.Linear(flat_val_dim, 1),
                )
                self.prediction_intent = (
                    nn.Sequential(
                        nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                        nn.SiLU(),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, self.objective_intent_classes),
                    )
                    if self.objective_intent_classes > 0
                    else None
                )
                self.prediction_multi_vp = (
                    nn.Sequential(
                        nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                        nn.SiLU(),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, self.multi_vp_feature_dim),
                    )
                    if self.multi_vp_feature_dim > 0
                    else None
                )
                self.prediction_threat_map = (
                    nn.Sequential(
                        nn.Conv2d(self.hidden_dim, 16, kernel_size=3, padding=1, bias=False),
                        _make_group_norm(16),
                        nn.SiLU(),
                        nn.Conv2d(16, 1, kernel_size=1),
                    )
                    if self.enable_threat_head
                    else None
                )
                self.prediction_attrition = (
                    nn.Sequential(
                        nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                        nn.SiLU(),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, 64),
                        nn.SiLU(),
                        nn.Linear(64, 2),
                    )
                    if self.enable_attrition_head
                    else None
                )
                self.prediction_morale = (
                    nn.Sequential(
                        nn.Conv2d(self.hidden_dim, val_channels, kernel_size=1),
                        nn.SiLU(),
                        nn.Flatten(start_dim=1),
                        nn.Linear(flat_val_dim, 64),
                        nn.SiLU(),
                        nn.Linear(64, self.morale_classes),
                    )
                    if self.enable_morale_head
                    else None
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
                nn.Linear(64, self.val_out_dim),
            )
            self.prediction_policy = nn.Linear(hidden_dim, action_dim)
            self.prediction_value = nn.Sequential(
                nn.Linear(hidden_dim, 64),
                nn.SiLU(),
                nn.Linear(64, self.val_out_dim),
            )
            self.prediction_objective = nn.Linear(hidden_dim, 1)
            self.prediction_intent = (
                nn.Linear(hidden_dim, self.objective_intent_classes)
                if self.objective_intent_classes > 0
                else None
            )
            self.prediction_multi_vp = (
                nn.Linear(hidden_dim, self.multi_vp_feature_dim)
                if self.multi_vp_feature_dim > 0
                else None
            )
            self.prediction_threat_map = (
                nn.Sequential(
                    nn.Linear(hidden_dim, 64),
                    nn.SiLU(),
                    nn.Linear(64, self.observation_height * self.observation_width),
                )
                if self.enable_threat_head
                else None
            )
            self.prediction_attrition = (
                nn.Sequential(
                    nn.Linear(hidden_dim, 64),
                    nn.SiLU(),
                    nn.Linear(64, 2),
                )
                if self.enable_attrition_head
                else None
            )
            self.prediction_morale = (
                nn.Sequential(
                    nn.Linear(hidden_dim, 64),
                    nn.SiLU(),
                    nn.Linear(64, self.morale_classes),
                )
                if self.enable_morale_head
                else None
            )
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
            if self.support_size > 0:
                val_logits = self.prediction_value(pred_hidden)
                value = support_to_scalar(val_logits, support_size=self.support_size)
            else:
                value = self.prediction_value(pred_hidden)
                val_logits = None
            reward = torch.zeros_like(value)
            rew_logits = torch.zeros_like(val_logits) if val_logits is not None else None
            objective_logit = self.prediction_objective(pred_hidden)
            objective_intent_logits = (
                self.prediction_intent(pred_hidden) if self.prediction_intent is not None else None
            )
            multi_vp_pred = (
                self.prediction_multi_vp(pred_hidden) if self.prediction_multi_vp is not None else None
            )
            threat_map_pred = (
                self.prediction_threat_map(pred_hidden) if self.prediction_threat_map is not None else None
            )
            attrition_pred = (
                self.prediction_attrition(pred_hidden) if self.prediction_attrition is not None else None
            )
            morale_pred = (
                self.prediction_morale(pred_hidden) if self.prediction_morale is not None else None
            )
        else:
            hidden = self._scale_latent(self.representation(observation))
            pred_hidden = self.prediction_trunk(hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            if self.support_size > 0:
                val_logits = self.prediction_value(pred_hidden)
                value = support_to_scalar(val_logits, support_size=self.support_size)
            else:
                value = self.prediction_value(pred_hidden)
                val_logits = None
            reward = torch.zeros_like(value)
            rew_logits = torch.zeros_like(val_logits) if val_logits is not None else None
            objective_logit = self.prediction_objective(pred_hidden)
            objective_intent_logits = (
                self.prediction_intent(pred_hidden) if self.prediction_intent is not None else None
            )
            multi_vp_pred = (
                self.prediction_multi_vp(pred_hidden) if self.prediction_multi_vp is not None else None
            )
            threat_map_pred = (
                self.prediction_threat_map(pred_hidden) if self.prediction_threat_map is not None else None
            )
            attrition_pred = (
                self.prediction_attrition(pred_hidden) if self.prediction_attrition is not None else None
            )
            morale_pred = (
                self.prediction_morale(pred_hidden) if self.prediction_morale is not None else None
            )
        if return_aux:
            aux = {"objective_logit": objective_logit}
            if val_logits is not None:
                aux["value_logits"] = val_logits
            if rew_logits is not None:
                aux["reward_logits"] = rew_logits
            if objective_intent_logits is not None:
                aux["objective_intent_logits"] = objective_intent_logits
            if multi_vp_pred is not None:
                aux["multi_vp_pred"] = multi_vp_pred
            if threat_map_pred is not None:
                aux["threat_map_pred"] = threat_map_pred
            if attrition_pred is not None:
                aux["attrition_pred"] = attrition_pred
            if morale_pred is not None:
                aux["morale_pred"] = morale_pred
            return hidden, policy_logits, value, reward, aux
        return hidden, policy_logits, value, reward

    def recurrent_inference(
        self, hidden: torch.Tensor, action_onehot: torch.Tensor, return_aux: bool = False
    ):
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
            if self.support_size > 0:
                rew_logits = self.dynamics_reward(next_hidden)
                reward = support_to_scalar(rew_logits, support_size=self.support_size)
            else:
                reward = self.dynamics_reward(next_hidden)
                rew_logits = None
            pred_hidden = self.prediction_trunk(next_hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            if self.support_size > 0:
                val_logits = self.prediction_value(pred_hidden)
                value = support_to_scalar(val_logits, support_size=self.support_size)
            else:
                value = self.prediction_value(pred_hidden)
                val_logits = None
            objective_logit = self.prediction_objective(pred_hidden)
            objective_intent_logits = (
                self.prediction_intent(pred_hidden) if self.prediction_intent is not None else None
            )
            multi_vp_pred = (
                self.prediction_multi_vp(pred_hidden) if self.prediction_multi_vp is not None else None
            )
            threat_map_pred = (
                self.prediction_threat_map(pred_hidden) if self.prediction_threat_map is not None else None
            )
            attrition_pred = (
                self.prediction_attrition(pred_hidden) if self.prediction_attrition is not None else None
            )
            morale_pred = (
                self.prediction_morale(pred_hidden) if self.prediction_morale is not None else None
            )
        else:
            x = torch.cat([hidden, action_onehot], dim=-1)
            next_hidden = self._scale_latent(self.dynamics_state(self.dynamics_input(x)))
            if self.support_size > 0:
                rew_logits = self.dynamics_reward(next_hidden)
                reward = support_to_scalar(rew_logits, support_size=self.support_size)
            else:
                reward = self.dynamics_reward(next_hidden)
                rew_logits = None
            pred_hidden = self.prediction_trunk(next_hidden)
            policy_logits = self.prediction_policy(pred_hidden)
            if self.support_size > 0:
                val_logits = self.prediction_value(pred_hidden)
                value = support_to_scalar(val_logits, support_size=self.support_size)
            else:
                value = self.prediction_value(pred_hidden)
                val_logits = None
            objective_logit = self.prediction_objective(pred_hidden)
            objective_intent_logits = (
                self.prediction_intent(pred_hidden) if self.prediction_intent is not None else None
            )
            multi_vp_pred = (
                self.prediction_multi_vp(pred_hidden) if self.prediction_multi_vp is not None else None
            )
            threat_map_pred = (
                self.prediction_threat_map(pred_hidden) if self.prediction_threat_map is not None else None
            )
            attrition_pred = (
                self.prediction_attrition(pred_hidden) if self.prediction_attrition is not None else None
            )
            morale_pred = (
                self.prediction_morale(pred_hidden) if self.prediction_morale is not None else None
            )
        if return_aux:
            aux = {"objective_logit": objective_logit}
            if val_logits is not None:
                aux["value_logits"] = val_logits
            if rew_logits is not None:
                aux["reward_logits"] = rew_logits
            if objective_intent_logits is not None:
                aux["objective_intent_logits"] = objective_intent_logits
            if multi_vp_pred is not None:
                aux["multi_vp_pred"] = multi_vp_pred
            if threat_map_pred is not None:
                aux["threat_map_pred"] = threat_map_pred
            if attrition_pred is not None:
                aux["attrition_pred"] = attrition_pred
            if morale_pred is not None:
                aux["morale_pred"] = morale_pred
            return next_hidden, policy_logits, value, reward, aux
        return next_hidden, policy_logits, value, reward

