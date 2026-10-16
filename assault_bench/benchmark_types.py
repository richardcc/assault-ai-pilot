from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class BenchmarkResult:
    agent_name: str
    matchup_profile: str
    matchup_group: str
    measurement_goal: str
    policy_name: str
    policy_by_side: Dict[str, str]
    controller_by_side: Dict[str, str]
    episodes: int
    avg_return: float
    avg_steps: float
    terminal_rate: float
    timeout_rate: float
    non_timeout_resolution_rate: float
    win_rate: float
    resolved_non_timeout_win_rate: float
    terminal_reasons: Dict[str, float]
    vp_initial_avg_by_side: Dict[str, float]
    vp_final_avg_by_side: Dict[str, float]
    vp_net_avg_by_side: Dict[str, float]
    vp_gained_avg_by_side: Dict[str, float]
    vp_lost_avg_by_side: Dict[str, float]
    vp_final_distribution_by_side: Dict[str, Dict[str, float]]
    winner_side_counts: Dict[str, int]
    winner_side_rates: Dict[str, float]
    tracked_side: str
    tracked_metric: str
    tracked_captured_avg: float
    tracked_captured_distribution: Dict[str, float]
    scenario_outcome_counts: Dict[str, int]
    scenario_outcome_rates: Dict[str, float]
    scenario_outcome_class_counts: Dict[str, int]
    scenario_outcome_class_rates: Dict[str, float]
    scenario_outcome_class_counts_by_side: Dict[str, Dict[str, int]]
    scenario_outcome_class_rates_by_side: Dict[str, Dict[str, float]]
    tracked_outcome_bucket_counts: Dict[str, int]
    tracked_outcome_bucket_rates: Dict[str, float]
    opponent_outcome_bucket_counts: Dict[str, int]
    opponent_outcome_bucket_rates: Dict[str, float]
    phase_2_9_eval_kpis: Dict[str, float]
    phase_2_9_eval_kpis_by_side: Dict[str, Dict[str, float]]
    eval_decision_summary: Dict[str, object]
    eval_decisions_top: List[Dict[str, object]]
    eval_decision_steps_top: List[Dict[str, object]]
    seed_games: List[Dict[str, object]]
    profile_wall_s: float
    episode_wall_s_mean: float
    episode_wall_s_p50: float
    episode_wall_s_p95: float
    episodes_per_second: float
