from __future__ import annotations

import json
import random
from typing import Dict, List, Optional

from assault_bench.episode_support_utils import (
    assault_advantage_bucket as _es_assault_advantage_bucket,
    dedupe_candidates_action_unit as _es_dedupe_candidates_action_unit,
    resolve_vp_horizon_selected_fields as _es_resolve_vp_horizon_selected_fields,
)
from assault_bench.episode_runtime_helpers import (
    HEAD_NAMES,
    compute_coverage_status as _erh_compute_coverage_status,
    field as _erh_field,
    head_state as _erh_head_state,
    run_policy_mcts as _erh_run_policy_mcts,
    scenario_outcome_from_final_vp as _erh_scenario_outcome_from_final_vp,
    to_int_or_none as _erh_to_int_or_none,
    vp_control_counts as _erh_vp_control_counts,
)
from assault_bench.episode_action_planner import choose_action_with_mcts
from assault_bench.episode_trace_row_builder import build_trace_row
from assault_bench.episode_signal_resolution import resolve_step_signals
from assault_bench.episode_step_indexes import (
    build_candidate_index,
    build_legal_action_indexes,
    build_unit_index,
    first_or_by_action,
)
from assault_bench.episode_step_models import (
    StepCoreData,
    StepPrefilterData,
    StepSignalData,
)
from assault_bench.episode_mcts_post import (
    enrich_candidates_from_breakdown as _mcts_enrich_candidates_from_breakdown,
    resolve_action_and_root_metrics as _mcts_resolve_action_and_root_metrics,
)
from assault_bench.trace_metrics_utils import (
    extract_actor_combat_dice_signals as _tm_extract_actor_combat_dice_signals,
    extract_actor_damage_kills_from_runtime_events as _tm_extract_actor_damage_kills_from_runtime_events,
    extract_unit_suppressed_from_runtime_events as _tm_extract_unit_suppressed_from_runtime_events,
    metric_from_row as _tm_metric_from_row,
)
_extract_unit_suppressed_from_runtime_events = _tm_extract_unit_suppressed_from_runtime_events
extract_unit_suppressed_from_runtime_events = _tm_extract_unit_suppressed_from_runtime_events
from assault_bench.action_utils import (
    action_kind_from_id as _au_action_kind_from_id,
    count_capture_like_actions as _au_count_capture_like_actions,
    is_capture_like_action_kind as _au_is_capture_like_action_kind,
)
from assault_bench.decision_metrics import (
    build_eval_decision_summary as _dm_build_eval_decision_summary,
    compute_decision_diagnostics_kpis as _dm_compute_decision_diagnostics_kpis,
)
from assault_bench.decision_signals import (
    obs_enemy_reaction_fire_risk_for_step as _ds_obs_enemy_reaction_fire_risk_for_step,
    reaction_exposure_component_for_step as _ds_reaction_exposure_component_for_step,
    reaction_fire_soft_signal_for_step as _ds_reaction_fire_soft_signal_for_step,
    select_action_with_probability_tie_break as _ds_select_action_with_probability_tie_break,
    vp_horizon_soft_components_for_step as _ds_vp_horizon_soft_components_for_step,
)
from assault_bench.trace_metrics_utils import build_eval_decision_steps_top as _build_eval_decision_steps_top
from assault_bench.phase29_contract import build_head_diagnostics_eval as _build_head_diagnostics_eval
from assault_bench.benchmark_serialization import json_dumps as _json_dumps
from assault_bench.benchmark_entry import _build_arg_parser
from assault_bench.benchmark_runtime_utils import (
    resolve_bench_device as _resolve_bench_device,
    resolve_enabled_profiles as _resolve_enabled_profiles,
)

def _resolve_bench_device_choice(config_device_cfg: str, cli_device: str = "") -> str:
    raw_cli = str(cli_device or "").strip().lower()
    if raw_cli in {"cpu", "cuda", "auto"}:
        return _resolve_bench_device(raw_cli)
    return _resolve_bench_device(str(config_device_cfg or "auto"))

from assault_bench.decision_candidate_utils import canonicalize_decision_candidates
from assault_bench.episode_runner_helpers import (
    build_post_unit_snapshots,
    resolve_global_strategy_component,
)
from assault_bench.episode_prefilter_metrics import resolve_prefilter_counts
from assault_bench.phase29_bucket_utils import (
    finalize_phase29 as _p29_finalize_phase29,
    new_phase29_bucket as _p29_new_phase29_bucket,
)
from assault_bench.outcome_metrics import (
    compute_seed_side_outcome_metrics as _om_compute_seed_side_outcome_metrics,
    normalize_outcome_score as _om_normalize_outcome_score,
    outcome_bucket_from_class as _om_outcome_bucket_from_class,
    outcome_bucket_from_score as _om_outcome_bucket_from_score,
)
from assault_bench.unit_state_utils import (
    side_alive_snapshot as _us_side_alive_snapshot,
    side_hp_snapshot as _us_side_hp_snapshot,
    unit_snapshot_dict as _us_unit_snapshot_dict,
    unit_suppressed_state_from_raw as _us_unit_suppressed_state_from_raw,
    units_snapshot as _us_units_snapshot,
)
from assault_bench.vp_action_utils import (
    capturable_vp_hexes_for_side as _vp_capturable_vp_hexes_for_side,
    count_immediate_vp_capture_move_options as _vp_count_immediate_vp_capture_move_options,
    extract_vp_hexes as _vp_extract_vp_hexes,
    is_move_action_kind as _vp_is_move_action_kind,
    is_immediate_vp_capture_move_taken as _vp_is_immediate_vp_capture_move_taken,
    is_vp_capture_taken_for_metrics as _vp_is_vp_capture_taken_for_metrics,
    parse_action_target_hex as _vp_parse_action_target_hex,
)
from assault_bench.vp_explain_utils import axial_distance as _vx_axial_distance
from assault_bench.decision_explain import (
    _backfill_why_action_vs_vp_from_observed_transition,
    _build_why_action_vs_vp,
    _select_action_with_probability_tie_break,
)
from assault_bench.telemetry_models import normalize_side_key
from agents.efficientzero_v2.core.selfplay import (
    _unit_prefilter_ranking as ezv2_unit_prefilter_ranking,
)
from agents.efficientzero_v2.core.mcts import run_mcts_puct as run_mcts_puct_ezv2
from agents.efficientzero_v2.core.adapter_voec import EZV2VOECAdapter
from agents.efficientzero_v2.core.observation import observation_to_tensor
from agents.efficientzero_v2.core.objective_signals import objective_step_signal
from agents.efficientzero_v2.core.xai_signals import (
    observation_to_vector,
    priors_and_values_from_model,
    xai_dynamics_signals_for_action_from_hidden,
    xai_root_signals_from_root_cache,
    value_signs_from_to_play,
    xai_dynamics_signals_for_action,
    xai_root_signals_from_model,
)

run_mcts_puct = run_mcts_puct_ezv2
run_mcts_puct_muzero = run_mcts_puct_ezv2
MuZeroVOECAdapter = EZV2VOECAdapter


_action_kind_from_id = _au_action_kind_from_id
_is_capture_like_action_kind = _au_is_capture_like_action_kind
_count_capture_like_actions = _au_count_capture_like_actions
_capturable_vp_hexes_for_side = _vp_capturable_vp_hexes_for_side
_is_move_action_kind = _vp_is_move_action_kind
_obs_enemy_reaction_fire_risk_for_step = _ds_obs_enemy_reaction_fire_risk_for_step
_reaction_exposure_component_for_step = _ds_reaction_exposure_component_for_step
_reaction_fire_soft_signal_for_step = _ds_reaction_fire_soft_signal_for_step
_vp_horizon_soft_components_for_step = _ds_vp_horizon_soft_components_for_step


_count_immediate_vp_capture_move_options = _vp_count_immediate_vp_capture_move_options
_is_immediate_vp_capture_move_taken = _vp_is_immediate_vp_capture_move_taken
_is_vp_capture_taken_for_metrics = _vp_is_vp_capture_taken_for_metrics
_axial_distance = _vx_axial_distance
_parse_action_target_hex = _vp_parse_action_target_hex
_extract_vp_hexes = _vp_extract_vp_hexes
_resolve_vp_horizon_selected_fields = _es_resolve_vp_horizon_selected_fields


_outcome_bucket_from_class = _om_outcome_bucket_from_class
_normalize_outcome_score = _om_normalize_outcome_score
_outcome_bucket_from_score = _om_outcome_bucket_from_score
_build_eval_decision_summary = _dm_build_eval_decision_summary
_compute_seed_side_outcome_metrics = _om_compute_seed_side_outcome_metrics
_compute_decision_diagnostics_kpis = _dm_compute_decision_diagnostics_kpis
_side_hp_snapshot = _us_side_hp_snapshot
_side_alive_snapshot = _us_side_alive_snapshot
_normalize_side_key = normalize_side_key
_unit_suppressed_state_from_raw = _us_unit_suppressed_state_from_raw
_unit_snapshot_dict = _us_unit_snapshot_dict
_units_snapshot = _us_units_snapshot


def _benchmark_seed_task(payload: dict):
    from assault_bench.episode_runner import benchmark_seed_task as _episode_benchmark_seed_task

    return _episode_benchmark_seed_task(payload)


def _run_episode_with_policy(
    adapter: EZV2VOECAdapter,
    scenario_id: str,
    seed: int,
    policy_name: str,
    policy_by_side: Dict[str, str],
    max_steps: int,
    max_steps_override: int,
    mcts_simulations: int,
    mcts_c_puct: float,
    mcts_temperature: float,
    mcts_dirichlet_alpha: float = 0.3,
    mcts_dirichlet_epsilon: float = 0.0,
    mcts_q_clip_abs: float = 10.0,
    mcts_q_root_normalization_mode: str = "adaptive_minmax",
    mcts_q_root_normalization_strength: float = 0.35,
    mcts_value_rescale_mode: str = "tanh",
    mcts_value_rescale_temperature: float = 10.0,
    mcts_success_prob_enabled: bool = False,
    mcts_success_prob_alpha: float = 0.0,
    mcts_success_prob_center: float = 0.5,
    mcts_success_prob_scale: float = 0.5,
    mcts_success_prob_centered_clip_abs: float = 1.0,
    mcts_min_root_visits_per_action: int = 0,
    mcts_min_root_visits_top_n: int = 0,
    model=None,
    action_dim: int = 32,
    mcts_unroll_steps: int = 1,
    mcts_discount: float = 0.997,
    collect_flow_metrics: bool = True,
    decision_top_k: Optional[int] = None,
    unit_prefilter_enabled: bool = False,
    unit_prefilter_replan_enabled: bool = False,
    unit_prefilter_top_k: int = 1,
    unit_prefilter_vp_progress_weight: float = 1.0,
    unit_prefilter_capture_opportunity_weight: float = 2.0,
    unit_prefilter_threat_weight: float = 0.25,
    reward_shaping: Optional[Dict[str, object]] = None,
    trace_detail_level: str = "core",
):
    from assault_bench.episode_runner import run_episode_with_policy as _episode_run_episode_with_policy

    return _episode_run_episode_with_policy(
        adapter=adapter,
        scenario_id=scenario_id,
        seed=seed,
        policy_name=policy_name,
        policy_by_side=policy_by_side,
        max_steps=max_steps,
        max_steps_override=max_steps_override,
        mcts_simulations=mcts_simulations,
        mcts_c_puct=mcts_c_puct,
        mcts_temperature=mcts_temperature,
        mcts_dirichlet_alpha=mcts_dirichlet_alpha,
        mcts_dirichlet_epsilon=mcts_dirichlet_epsilon,
        mcts_q_clip_abs=mcts_q_clip_abs,
        mcts_q_root_normalization_mode=mcts_q_root_normalization_mode,
        mcts_q_root_normalization_strength=mcts_q_root_normalization_strength,
        mcts_value_rescale_mode=mcts_value_rescale_mode,
        mcts_value_rescale_temperature=mcts_value_rescale_temperature,
        mcts_success_prob_enabled=mcts_success_prob_enabled,
        mcts_success_prob_alpha=mcts_success_prob_alpha,
        mcts_success_prob_center=mcts_success_prob_center,
        mcts_success_prob_scale=mcts_success_prob_scale,
        mcts_success_prob_centered_clip_abs=mcts_success_prob_centered_clip_abs,
        mcts_min_root_visits_per_action=mcts_min_root_visits_per_action,
        mcts_min_root_visits_top_n=mcts_min_root_visits_top_n,
        model=model,
        action_dim=action_dim,
        mcts_unroll_steps=mcts_unroll_steps,
        mcts_discount=mcts_discount,
        collect_flow_metrics=collect_flow_metrics,
        decision_top_k=decision_top_k,
        unit_prefilter_enabled=unit_prefilter_enabled,
        unit_prefilter_replan_enabled=unit_prefilter_replan_enabled,
        unit_prefilter_top_k=unit_prefilter_top_k,
        unit_prefilter_vp_progress_weight=unit_prefilter_vp_progress_weight,
        unit_prefilter_capture_opportunity_weight=unit_prefilter_capture_opportunity_weight,
        unit_prefilter_threat_weight=unit_prefilter_threat_weight,
        reward_shaping=reward_shaping,
        trace_detail_level=trace_detail_level,
    )


def _run_episode_with_policy_impl(
    adapter: EZV2VOECAdapter,
    scenario_id: str,
    seed: int,
    policy_name: str,
    policy_by_side: Dict[str, str],
    max_steps: int,
    max_steps_override: int,
    mcts_simulations: int,
    mcts_c_puct: float,
    mcts_temperature: float,
    mcts_dirichlet_alpha: float = 0.3,
    mcts_dirichlet_epsilon: float = 0.0,
    mcts_q_clip_abs: float = 10.0,
    mcts_q_root_normalization_mode: str = "adaptive_minmax",
    mcts_q_root_normalization_strength: float = 0.35,
    mcts_value_rescale_mode: str = "tanh",
    mcts_value_rescale_temperature: float = 10.0,
    mcts_success_prob_enabled: bool = False,
    mcts_success_prob_alpha: float = 0.0,
    mcts_success_prob_center: float = 0.5,
    mcts_success_prob_scale: float = 0.5,
    mcts_success_prob_centered_clip_abs: float = 1.0,
    mcts_min_root_visits_per_action: int = 0,
    mcts_min_root_visits_top_n: int = 0,
    model=None,
    action_dim: int = 32,
    mcts_unroll_steps: int = 1,
    mcts_discount: float = 0.997,
    collect_flow_metrics: bool = True,
    decision_top_k: Optional[int] = None,
    unit_prefilter_enabled: bool = False,
    unit_prefilter_replan_enabled: bool = False,
    unit_prefilter_top_k: int = 1,
    unit_prefilter_vp_progress_weight: float = 1.0,
    unit_prefilter_capture_opportunity_weight: float = 2.0,
    unit_prefilter_threat_weight: float = 0.25,
    reward_shaping: Optional[Dict[str, object]] = None,
    trace_detail_level: str = "core",
):
    from assault_bench.episode_runner_impl import _run_episode_with_policy_impl as _episode_impl

    return _episode_impl(
        adapter=adapter,
        scenario_id=scenario_id,
        seed=seed,
        policy_name=policy_name,
        policy_by_side=policy_by_side,
        max_steps=max_steps,
        max_steps_override=max_steps_override,
        mcts_simulations=mcts_simulations,
        mcts_c_puct=mcts_c_puct,
        mcts_temperature=mcts_temperature,
        mcts_dirichlet_alpha=mcts_dirichlet_alpha,
        mcts_dirichlet_epsilon=mcts_dirichlet_epsilon,
        mcts_q_clip_abs=mcts_q_clip_abs,
        mcts_q_root_normalization_mode=mcts_q_root_normalization_mode,
        mcts_q_root_normalization_strength=mcts_q_root_normalization_strength,
        mcts_value_rescale_mode=mcts_value_rescale_mode,
        mcts_value_rescale_temperature=mcts_value_rescale_temperature,
        mcts_success_prob_enabled=mcts_success_prob_enabled,
        mcts_success_prob_alpha=mcts_success_prob_alpha,
        mcts_success_prob_center=mcts_success_prob_center,
        mcts_success_prob_scale=mcts_success_prob_scale,
        mcts_success_prob_centered_clip_abs=mcts_success_prob_centered_clip_abs,
        mcts_min_root_visits_per_action=mcts_min_root_visits_per_action,
        mcts_min_root_visits_top_n=mcts_min_root_visits_top_n,
        model=model,
        action_dim=action_dim,
        mcts_unroll_steps=mcts_unroll_steps,
        mcts_discount=mcts_discount,
        collect_flow_metrics=collect_flow_metrics,
        decision_top_k=decision_top_k,
        unit_prefilter_enabled=unit_prefilter_enabled,
        unit_prefilter_replan_enabled=unit_prefilter_replan_enabled,
        unit_prefilter_top_k=unit_prefilter_top_k,
        unit_prefilter_vp_progress_weight=unit_prefilter_vp_progress_weight,
        unit_prefilter_capture_opportunity_weight=unit_prefilter_capture_opportunity_weight,
        unit_prefilter_threat_weight=unit_prefilter_threat_weight,
        reward_shaping=reward_shaping,
        trace_detail_level=trace_detail_level,
    )

def _run_benchmark_impl(
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    checkpoint_path: str = "",
    muzero_config_path: str = "",
    mlflow_experiment: str = "assault_bench",
    mlflow_run_name: str = "",
    device: str = "",
) -> Dict:
    from assault_bench.benchmark_orchestrator import _run_benchmark_impl as _run_benchmark_impl_orchestrated

    return _run_benchmark_impl_orchestrated(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        muzero_config_path=muzero_config_path,
        mlflow_experiment=mlflow_experiment,
        mlflow_run_name=mlflow_run_name,
        device=device,
    )


def run_benchmark(
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    checkpoint_path: str = "",
    muzero_config_path: str = "",
    mlflow_experiment: str = "assault_bench",
    mlflow_run_name: str = "",
    device: str = "",
):
    from assault_bench.benchmark_orchestrator import run_benchmark as _orchestrated_run_benchmark

    return _orchestrated_run_benchmark(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        muzero_config_path=muzero_config_path,
        mlflow_experiment=mlflow_experiment,
        mlflow_run_name=mlflow_run_name,
        device=device,
    )


if __name__ == "__main__":
    from assault_bench.benchmark_entry import main as _benchmark_entry_main

    _benchmark_entry_main()
