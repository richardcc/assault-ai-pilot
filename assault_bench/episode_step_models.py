from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class StepCoreData:
    step: int
    game_turn: int
    turn: int
    active_side: str
    action: str
    action_kind: str
    chosen_prob: float
    margin: float
    mcts_entropy: float
    mcts_total_visits: int
    mcts_active_actions: int
    root_actions_for_explain: List[str]
    legal_actions_list: List[str]
    legal_actions_duplicates_collapsed: int
    legal_actions_decoded_target_qr: List[Dict[str, object]]
    acting_unit_action_catalog: List[Dict[str, object]]
    acting_unit_id: str
    acting_unit: object
    transition_reward: float
    transition_done: bool
    enemy_damage: float
    enemy_kills: int
    action_parts: List[str]
    target_q: Optional[int]
    target_r: Optional[int]
    attack_distance: float
    target_cover: float
    target_los: float
    capture_legal_count: int
    capture_like_action_taken: bool


@dataclass
class StepSignalData:
    mcts_prior_value: Optional[float]
    mcts_q_value: Optional[float]
    mcts_u_value: Optional[float]
    decision_score_value: Optional[float]
    selected_success_proxy: Optional[float]
    selected_success_component: Optional[float]
    selected_components: Dict[str, object]
    selected_vp_horizon_steps: Optional[float]
    selected_vp_horizon_signal: Optional[float]
    selected_vp_horizon_component: Optional[float]
    vp_horizon_source: str
    vp_horizon_available: bool
    objective_soft_component_value: Optional[float]
    objective_soft_source: str
    objective_soft_available: bool
    objective_soft_reason: str
    global_strategy_soft_component_value: Optional[float]
    global_strategy_soft_source: str
    global_strategy_soft_available: bool
    reaction_fire_soft_component_value: Optional[float]
    reaction_fire_soft_source: str
    reaction_fire_soft_available: bool
    reaction_exposure_component_value: Optional[float]
    reaction_exposure_source: str
    reaction_exposure_available: bool
    objective_had_opportunity: int
    objective_min_dist_before: float
    objective_min_dist_after: float
    objective_progress_delta: Optional[float]
    selected_tie_break_term: Optional[float]
    objective_converted: int
    objective_best_vp_id: str
    strategy_label: str
    vp_distance_vector: Dict[str, float]
    obs_enemy_reaction_fire_risk_value: Optional[float]


@dataclass
class StepPrefilterData:
    unit_prefilter_enabled: bool
    unit_prefilter_enabled_source: str
    unit_prefilter_selected_unit_id: str
    replan_evaluated_units: List[Dict[str, object]]
    unit_prefilter_constrained_count: Optional[int]
    unit_prefilter_constrained_count_source: str
    unit_prefilter_global_count: Optional[int]
    unit_prefilter_global_count_source: str
