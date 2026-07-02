from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class DecisionEvent:
    iteration: int
    episode: int
    step: int
    chosen_action: str
    top_actions: List[str]
    top_probs: List[float]

    def to_payload(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class SearchEvent:
    iteration: int
    episode: int
    step: int
    node_count: int
    max_depth: int

    def to_payload(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class TrainStepEvent:
    iteration: int
    loss: float
    policy_loss: float
    value_loss: float
    reward_loss: float
    objective_loss: float = 0.0
    grad_norm: float = 0.0
    replay_age_mean: float = 0.0
    replay_age_max: float = 0.0

    def to_payload(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class TransitionEvent:
    iteration: int
    episode: int
    step: int
    game_turn: int
    action_id: str
    to_play: str
    reward_target: float
    done: bool
    terminal_reason: str
    timeout: bool
    action_kind: str = ""
    unit_id: str = ""
    unit_side: str = ""
    unit_key: str = ""
    unit_label: str = ""
    damage_dealt: float = 0.0
    kills_dealt: int = 0
    vp_captures: int = 0
    vp_control_before_by_side: Dict[str, int] = field(default_factory=dict)
    vp_control_after_by_side: Dict[str, int] = field(default_factory=dict)
    vp_gain_by_side: Dict[str, int] = field(default_factory=dict)
    vp_loss_by_side: Dict[str, int] = field(default_factory=dict)
    reward_components: Dict[str, float] = field(default_factory=dict)
    eligible_unit_ids: List[str] = field(default_factory=list)
    eligible_unit_count: int = 0
    legal_action_count: int = 0
    legal_attack_options: int = 0
    legal_capture_options: int = 0
    legal_reaction_options: int = 0
    objective_had_opportunity: int = 0
    objective_distance_before: float = -1.0
    objective_distance_after: float = -1.0
    objective_progress_delta: float = 0.0
    objective_converted: int = 0
    objective_vp_hexes_count: int = 0
    objective_vp_owner_count: int = 0
    objective_side_norm: str = ""
    mcts_entropy: float = 0.0
    mcts_margin: float = 0.0
    chosen_action_prob: float = 0.0
    predicted_value: float = 0.0
    mcts_total_visits: int = 0
    mcts_active_actions: int = 0
    attack_target_unit_id: str = ""
    attack_target_class_attempt: str = ""
    attack_target_class_damage: Dict[str, float] = field(default_factory=dict)
    attack_target_class_kills: Dict[str, int] = field(default_factory=dict)
    attack_distance_mean: float = -1.0
    attack_target_cover_mean: float = -1.0
    attack_target_los_block_mean: float = -1.0
    policy_top_actions: List[str] = field(default_factory=list)
    policy_top_probs: List[float] = field(default_factory=list)
    latent_top_indices: List[int] = field(default_factory=list)
    latent_top_values: List[float] = field(default_factory=list)
    latent_l2_norm: float = 0.0
    predicted_value_root: float = 0.0
    dynamics_pred_reward: float = 0.0
    dynamics_next_latent_l2: float = 0.0
    dynamics_delta_l2: float = 0.0
    acting_q: int = 0
    acting_r: int = 0
    target_q: int = 0
    target_r: int = 0

    def to_payload(self) -> Dict:
        return asdict(self)
