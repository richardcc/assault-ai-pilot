from __future__ import annotations

import torch
from torch import nn
import torch.nn.functional as F

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


class HexagonalMaskConv2d(nn.Conv2d):
    """
    2D Convolution constrained to a 6-neighbor hexagonal topology.
    In hexagonal axial/offset representations, the corners (0, 0) and (2, 2)
    do not share a physical hexagonal edge. Applying a static binary mask ensures the network
    does not propagate spurious diagonal interactions across non-adjacent cells.
    """
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int = 3, padding: int = 1, bias: bool = False):
        super().__init__(in_channels, out_channels, kernel_size=kernel_size, padding=padding, bias=bias)
        if kernel_size == 3:
            # Hex neighbors in axial coordinates: 6 equidistant neighbors, 2 non-adjacent diagonal corners
            mask = torch.tensor([
                [0.0, 1.0, 1.0],
                [1.0, 1.0, 1.0],
                [1.0, 1.0, 0.0]
            ], dtype=torch.float32).view(1, 1, 3, 3)
            self.register_buffer("hex_mask", mask, persistent=False)
        else:
            self.hex_mask = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.hex_mask is not None:
            w = self.weight * self.hex_mask
            return F.conv2d(x, w, self.bias, self.stride, self.padding, self.dilation, self.groups)
        return super().forward(x)


class HexagonalDepthwiseSeparableConv2d(nn.Module):
    """
    Depthwise-Separable Hexagonal Convolution (Palma et al. 2025, Sec. 5):
    Applies a 6-neighbor masked 3x3 depthwise convolution per channel followed by
    a 1x1 pointwise projection, reducing FLOPs and parameters by ~70% on large maps.
    """
    def __init__(self, in_channels: int, out_channels: int, bias: bool = False):
        super().__init__()
        self.depthwise = nn.Conv2d(
            in_channels, in_channels, kernel_size=3, padding=1, groups=in_channels, bias=False
        )
        mask = torch.tensor([
            [0.0, 1.0, 1.0],
            [1.0, 1.0, 1.0],
            [1.0, 1.0, 0.0]
        ], dtype=torch.float32).view(1, 1, 3, 3)
        self.register_buffer("hex_mask", mask, persistent=False)
        self.pointwise = nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        w = self.depthwise.weight * self.hex_mask
        dw = F.conv2d(x, w, None, self.depthwise.stride, self.depthwise.padding, self.depthwise.dilation, self.depthwise.groups)
        return self.pointwise(dw)


class InputChannelGate(nn.Module):
    """
    Dynamic Input Channel Attention Gate (SENet / CBAM):
    Recalibrates raw observation channels (e.g., 32 channels) before the representation trunk
    and suppresses scenario-inactive dead channels.
    """
    def __init__(self, channels: int, reduction: int = 4):
        super().__init__()
        mid = max(4, int(channels) // max(1, int(reduction)))
        self.gate = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, mid, kernel_size=1),
            nn.SiLU(),
            nn.Conv2d(mid, channels, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Also zero out completely inactive channels so bias terms cannot leak noise
        active_mask = (x.abs().amax(dim=(-2, -1), keepdim=True) > 1e-6).to(x.dtype)
        return x * self.gate(x) * active_mask


class ResidualConvBlock(nn.Module):
    def __init__(self, channels: int, use_hex_mask: bool = True):
        super().__init__()
        conv_cls = HexagonalMaskConv2d if use_hex_mask else nn.Conv2d
        self.conv1 = conv_cls(channels, channels, kernel_size=3, padding=1, bias=False)
        self.gn1 = _make_group_norm(channels)
        self.act1 = nn.SiLU()
        self.conv2 = conv_cls(channels, channels, kernel_size=3, padding=1, bias=False)
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


class TemporalContextBlock(nn.Module):
    """
    Lightweight GRU-based temporal context cell to resolve POMDP state ambiguities
    under Fog of War / Hidden Information in tactical wargames (Palma et al., 2025).
    """
    def __init__(self, hidden_dim: int):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.gru_cell = nn.GRUCell(hidden_dim, hidden_dim)

    def forward(self, latent_pooled: torch.Tensor, prev_state: torch.Tensor | None = None) -> torch.Tensor:
        if prev_state is None:
            prev_state = torch.zeros_like(latent_pooled)
        return self.gru_cell(latent_pooled, prev_state)


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
        dynamics_recurrent_steps: int = 1,
        use_hex_mask: bool = True,
        use_recall: bool = True,
        enable_input_channel_gate: bool = False,
        enable_temporal_context: bool = False,
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
        self.dynamics_recurrent_steps = max(1, int(dynamics_recurrent_steps))
        self.use_hex_mask = bool(use_hex_mask)
        self.use_recall = bool(use_recall)
        self.enable_input_channel_gate = bool(enable_input_channel_gate)
        self.enable_temporal_context = bool(enable_temporal_context)
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
            conv_cls = HexagonalMaskConv2d if self.use_hex_mask else nn.Conv2d
            self.input_channel_gate = (
                InputChannelGate(self.observation_channels) if self.enable_input_channel_gate else None
            )
            self.temporal_context = (
                TemporalContextBlock(self.hidden_dim) if self.enable_temporal_context else None
            )
            self.representation_input = nn.Sequential(
                conv_cls(self.observation_channels, self.hidden_dim, kernel_size=3, padding=1, bias=False),
                _make_group_norm(self.hidden_dim),
                nn.SiLU(),
            )
            self.representation_tower = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim, use_hex_mask=self.use_hex_mask) for _ in range(max(1, int(prediction_blocks)))]
            )
            self.action_plane_dim = max(4, min(self.hidden_dim, 16))
            self.action_embedding = nn.Embedding(self.action_dim, self.action_plane_dim)
            self.dynamics_merge = nn.Sequential(
                conv_cls(
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
                *[ResidualConvBlock(self.hidden_dim, use_hex_mask=self.use_hex_mask) for _ in range(max(1, int(dynamics_blocks)))]
            )
            self.prediction_trunk = nn.Sequential(
                *[ResidualConvBlock(self.hidden_dim, use_hex_mask=self.use_hex_mask) for _ in range(max(1, int(prediction_blocks)))]
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

    def _adapt_spatial(self, t: torch.Tensor) -> torch.Tensor:
        """
        Adaptive Spatial Processing (Palma et al.):
        Ensures resolution invariance (16x16, 32x32, 64x64) for non-attention heads
        without modifying state_dict keys or trainable parameters.
        """
        if not self.use_spatial_attention and t.dim() == 4:
            if t.shape[-2] != self.observation_height or t.shape[-1] != self.observation_width:
                return F.adaptive_avg_pool2d(t, (self.observation_height, self.observation_width))
        return t

    def _gate_input_channels(self, observation: torch.Tensor) -> torch.Tensor:
        """Applies learned InputChannelGate when enabled."""
        if getattr(self, "input_channel_gate", None) is not None and observation.dim() == 4:
            return self.input_channel_gate(observation)
        return observation

    def update_temporal_context(
        self, hidden: torch.Tensor, prev_state: torch.Tensor | None = None
    ) -> torch.Tensor:
        """
        Updates POMDP / Fog-of-War GRU belief state from spatial or vector latent representation.
        Preserves 4D spatial latent shape (B, C, H, W) when hidden is 4D.
        """
        is_spatial = hidden.dim() == 4
        pooled = hidden.mean(dim=(-2, -1)) if is_spatial else hidden
        prev_vec = (
            prev_state.mean(dim=(-2, -1))
            if (prev_state is not None and prev_state.dim() == 4)
            else prev_state
        )
        if getattr(self, "temporal_context", None) is not None:
            ctx = self.temporal_context(pooled, prev_vec)
        elif prev_vec is None:
            ctx = pooled
        else:
            ctx = 0.5 * (pooled + prev_vec)
        if is_spatial:
            return self._scale_latent(hidden + ctx.unsqueeze(-1).unsqueeze(-1))
        return ctx

    def initial_inference(self, observation: torch.Tensor, return_aux: bool = False):
        if self.encoder_type == "cnn":
            obs_in = self._gate_input_channels(observation)
            hidden = self._scale_latent(self.representation_tower(self.representation_input(obs_in)))
            pred_hidden = self.prediction_trunk(hidden)
            head_in = self._adapt_spatial(pred_hidden)
            policy_logits = self.prediction_policy(head_in)
            if self.support_size > 0:
                val_logits = self.prediction_value(head_in)
                value = support_to_scalar(val_logits, support_size=self.support_size)
            else:
                value = self.prediction_value(head_in)
                val_logits = None
            reward = torch.zeros_like(value)
            rew_logits = torch.zeros_like(val_logits) if val_logits is not None else None
            objective_logit = self.prediction_objective(head_in)
            objective_intent_logits = (
                self.prediction_intent(head_in) if self.prediction_intent is not None else None
            )
            multi_vp_pred = (
                self.prediction_multi_vp(head_in) if self.prediction_multi_vp is not None else None
            )
            threat_map_pred = (
                self.prediction_threat_map(pred_hidden) if self.prediction_threat_map is not None else None
            )
            attrition_pred = (
                self.prediction_attrition(head_in) if self.prediction_attrition is not None else None
            )
            morale_pred = (
                self.prediction_morale(head_in) if self.prediction_morale is not None else None
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
            if getattr(self, "temporal_context", None) is not None:
                aux["temporal_context_state"] = self.update_temporal_context(hidden)
            return hidden, policy_logits, value, reward, aux
        return hidden, policy_logits, value, reward

    def recurrent_inference(
        self,
        hidden: torch.Tensor,
        action_onehot: torch.Tensor,
        return_aux: bool = False,
        recurrent_steps: int | None = None,
        use_recall: bool | None = None,
        no_grad_steps: int = 0,
    ):
        steps = max(
            1,
            int(
                recurrent_steps
                if recurrent_steps is not None
                else getattr(self, "dynamics_recurrent_steps", 1)
            ),
        )
        recall_active = bool(self.use_recall if use_recall is None else use_recall)
        n_nograd = max(0, min(steps - 1, int(no_grad_steps)))

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

            # Map-size agnostic dynamic expansion (supports 16x16, 32x32, 64x64 zero-shot)
            h_dim, w_dim = int(hidden.shape[-2]), int(hidden.shape[-1])
            action_planes = action_emb.unsqueeze(-1).unsqueeze(-1).expand(
                -1, -1, h_dim, w_dim
            )

            def _step_cnn(z_curr: torch.Tensor, step_idx: int) -> torch.Tensor:
                if step_idx == 0:
                    merged_in = self.dynamics_merge(torch.cat([hidden, action_planes], dim=1))
                    return self.dynamics_state(merged_in)
                if recall_active:
                    # Recall skip-connection (Palma et al. 2025, Fig. 1 / Bansal et al. 2022):
                    # Re-injects original step input (hidden, action_planes) at every recurrent step
                    recalled = self.dynamics_merge(
                        torch.cat([0.5 * (z_curr + hidden), action_planes], dim=1)
                    )
                    return self.dynamics_state(recalled)
                return self.dynamics_state(z_curr)

            z = hidden
            if n_nograd > 0:
                with torch.no_grad():
                    for s_idx in range(n_nograd):
                        z = _step_cnn(z, s_idx)
                z = z.detach()
            for s_idx in range(n_nograd, steps):
                z = _step_cnn(z, s_idx)
            next_hidden = self._scale_latent(z)

            rew_in = self._adapt_spatial(next_hidden)
            if self.support_size > 0:
                rew_logits = self.dynamics_reward(rew_in)
                reward = support_to_scalar(rew_logits, support_size=self.support_size)
            else:
                reward = self.dynamics_reward(rew_in)
                rew_logits = None
            pred_hidden = self.prediction_trunk(next_hidden)
            head_in = self._adapt_spatial(pred_hidden)
            policy_logits = self.prediction_policy(head_in)
            if self.support_size > 0:
                val_logits = self.prediction_value(head_in)
                value = support_to_scalar(val_logits, support_size=self.support_size)
            else:
                value = self.prediction_value(head_in)
                val_logits = None
            objective_logit = self.prediction_objective(head_in)
            objective_intent_logits = (
                self.prediction_intent(head_in) if self.prediction_intent is not None else None
            )
            multi_vp_pred = (
                self.prediction_multi_vp(head_in) if self.prediction_multi_vp is not None else None
            )
            threat_map_pred = (
                self.prediction_threat_map(pred_hidden) if self.prediction_threat_map is not None else None
            )
            attrition_pred = (
                self.prediction_attrition(head_in) if self.prediction_attrition is not None else None
            )
            morale_pred = (
                self.prediction_morale(head_in) if self.prediction_morale is not None else None
            )
        else:
            x = self.dynamics_input(torch.cat([hidden, action_onehot], dim=-1))
            z = x
            if n_nograd > 0:
                with torch.no_grad():
                    for s_idx in range(n_nograd):
                        z_in = 0.5 * (z + x) if (s_idx > 0 and recall_active) else z
                        z = self.dynamics_state(z_in)
                z = z.detach()
            for s_idx in range(n_nograd, steps):
                z_in = 0.5 * (z + x) if (s_idx > 0 and recall_active) else z
                z = self.dynamics_state(z_in)
            next_hidden = self._scale_latent(z)
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

