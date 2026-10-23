from __future__ import annotations

import random
from typing import Dict, List, Optional

from agents.efficientzero_v2.core.adapter_voec import EZV2VOECAdapter, EZV2VOECAdapter as MuZeroVOECAdapter
from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner
from assault_bench import runner as _runner

HEAD_NAMES = _runner.HEAD_NAMES
build_trace_row = _runner.build_trace_row
build_candidate_index = _runner.build_candidate_index
build_legal_action_indexes = _runner.build_legal_action_indexes
build_post_unit_snapshots = _runner.build_post_unit_snapshots
build_unit_index = _runner.build_unit_index
canonicalize_decision_candidates = _runner.canonicalize_decision_candidates
choose_action_with_mcts = _runner.choose_action_with_mcts
first_or_by_action = _runner.first_or_by_action
objective_step_signal = _runner.objective_step_signal
observation_to_tensor = _runner.observation_to_tensor
observation_to_vector = _runner.observation_to_vector
priors_and_values_from_model = _runner.priors_and_values_from_model
resolve_global_strategy_component = _runner.resolve_global_strategy_component
resolve_prefilter_counts = _runner.resolve_prefilter_counts
resolve_step_signals = _runner.resolve_step_signals
run_mcts_puct_ezv2 = _runner.run_mcts_puct_ezv2
run_mcts_puct_muzero = _runner.run_mcts_puct_muzero
value_signs_from_to_play = _runner.value_signs_from_to_play
xai_dynamics_signals_for_action_from_hidden = _runner.xai_dynamics_signals_for_action_from_hidden
xai_dynamics_signals_for_action = _runner.xai_dynamics_signals_for_action
xai_root_signals_from_root_cache = _runner.xai_root_signals_from_root_cache
xai_root_signals_from_model = _runner.xai_root_signals_from_model
ezv2_unit_prefilter_ranking = _runner.ezv2_unit_prefilter_ranking
StepCoreData = _runner.StepCoreData
StepPrefilterData = _runner.StepPrefilterData
StepSignalData = _runner.StepSignalData
_action_kind_from_id = _runner._action_kind_from_id
_backfill_why_action_vs_vp_from_observed_transition = _runner._backfill_why_action_vs_vp_from_observed_transition
_build_why_action_vs_vp = _runner._build_why_action_vs_vp
_compute_decision_diagnostics_kpis = _runner._compute_decision_diagnostics_kpis
_count_capture_like_actions = _runner._count_capture_like_actions
_count_immediate_vp_capture_move_options = _runner._count_immediate_vp_capture_move_options
_erh_compute_coverage_status = _runner._erh_compute_coverage_status
_erh_field = _runner._erh_field
_erh_head_state = _runner._erh_head_state
_erh_run_policy_mcts = _runner._erh_run_policy_mcts
_erh_scenario_outcome_from_final_vp = _runner._erh_scenario_outcome_from_final_vp
_erh_to_int_or_none = _runner._erh_to_int_or_none
_erh_vp_control_counts = _runner._erh_vp_control_counts
_es_assault_advantage_bucket = _runner._es_assault_advantage_bucket
_es_dedupe_candidates_action_unit = _runner._es_dedupe_candidates_action_unit
_es_resolve_vp_horizon_selected_fields = _runner._es_resolve_vp_horizon_selected_fields
_is_capture_like_action_kind = _runner._is_capture_like_action_kind
_is_immediate_vp_capture_move_taken = _runner._is_immediate_vp_capture_move_taken
_is_vp_capture_taken_for_metrics = _runner._is_vp_capture_taken_for_metrics
_mcts_enrich_candidates_from_breakdown = _runner._mcts_enrich_candidates_from_breakdown
_mcts_resolve_action_and_root_metrics = _runner._mcts_resolve_action_and_root_metrics
_normalize_outcome_score = _runner._normalize_outcome_score
_normalize_side_key = _runner._normalize_side_key
_obs_enemy_reaction_fire_risk_for_step = _runner._obs_enemy_reaction_fire_risk_for_step
_p29_finalize_phase29 = _runner._p29_finalize_phase29
_p29_new_phase29_bucket = _runner._p29_new_phase29_bucket
_parse_action_target_hex = _runner._parse_action_target_hex
_reaction_exposure_component_for_step = _runner._reaction_exposure_component_for_step
_reaction_fire_soft_signal_for_step = _runner._reaction_fire_soft_signal_for_step
_select_action_with_probability_tie_break = _runner._select_action_with_probability_tie_break
_side_alive_snapshot = _runner._side_alive_snapshot
_side_hp_snapshot = _runner._side_hp_snapshot
_tm_extract_actor_combat_dice_signals = _runner._tm_extract_actor_combat_dice_signals
_tm_extract_actor_damage_kills_from_runtime_events = _runner._tm_extract_actor_damage_kills_from_runtime_events
_tm_extract_unit_suppressed_from_runtime_events = _runner._tm_extract_unit_suppressed_from_runtime_events
_tm_metric_from_row = _runner._tm_metric_from_row
_units_snapshot = _runner._units_snapshot
_vp_horizon_soft_components_for_step = _runner._vp_horizon_soft_components_for_step


def _decorate_units_with_macro_plan(
    units_list: list[dict[str, object]],
    macro_plan,
    acting_unit_id: str = "",
    prior_boost: float = 0.0,
) -> list[dict[str, object]]:
    decorated = []
    for u in list(units_list or []):
        d = dict(u or {})
        uid = str(d.get("unit_id", "") or "")
        if macro_plan is not None and uid in getattr(macro_plan, "unit_roles", {}):
            role = str(macro_plan.get_role(uid))
            d["role_assigned"] = role
            d["active_role"] = role
            d["role_is_mutated"] = bool(macro_plan.is_mutated(uid))
            d["role_mutation_reason"] = str(macro_plan.get_mutation_reason(uid))
            d["prior_boost_applied"] = float(prior_boost) if uid == acting_unit_id else 0.0
            d["badge_label"] = role.replace("ROLE_", "")
        decorated.append(d)
    return decorated


def _run_episode_with_policy_impl(
    adapter: MuZeroVOECAdapter,
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
    macro_modulation_scale: float = 1.0,
):
    _head_state = _erh_head_state
    _compute_coverage_status = _erh_compute_coverage_status
    _to_int_or_none = _erh_to_int_or_none
    _field = _erh_field

    model_kind_local = "efficientzero_v2"

    def _run_policy_mcts(**kwargs):
        return _erh_run_policy_mcts(
            model_kind_local=model_kind_local,
            kwargs=kwargs,
            run_mcts_puct_ezv2_fn=run_mcts_puct_ezv2,
            run_mcts_puct_muzero_fn=run_mcts_puct_muzero,
        )

    def _new_phase29_bucket() -> Dict[str, float]:
        return _p29_new_phase29_bucket()

    def _finalize_phase29(bucket: Dict[str, float]) -> Dict[str, float]:
        return _p29_finalize_phase29(bucket)

    def _scenario_outcome_from_final_vp(final_vp_by_side: Dict[str, int]) -> Dict[str, object]:
        return _erh_scenario_outcome_from_final_vp(
            final_vp_by_side=final_vp_by_side,
            adapter=adapter,
            normalize_outcome_score_fn=_normalize_outcome_score,
        )

    def _vp_control_counts() -> Dict[str, int]:
        return _erh_vp_control_counts(adapter=adapter)

    obs = adapter.initial_state(scenario_id=scenario_id, seed=seed)
    initial_vp_by_side = _vp_control_counts()
    eval_side = ""
    eval_candidates: list[str] = []
    if policy_by_side:
        target_policy = str(policy_name or "mcts").strip().lower()
        eval_candidates = [
            _normalize_side_key(s)
            for s, pol in policy_by_side.items()
            if str(pol).strip().lower() == target_policy
        ]
        if len(eval_candidates) == 1:
            eval_side = eval_candidates[0]
        elif len(eval_candidates) > 1:
            # Self-play mirror: prioritize scenario designated tracked_side if present among candidates
            runtime = getattr(adapter.sim, "_runtime", None)
            scenario = getattr(runtime, "scenario", None) if runtime is not None else None
            vo = getattr(scenario, "victory_outcomes", None) if scenario is not None else None
            if vo is None and isinstance(scenario, dict):
                vo = scenario.get("victory_outcomes")
            sc_tracked = _normalize_side_key(str(dict(vo or {}).get("tracked_side", "")).strip())
            if sc_tracked and sc_tracked in eval_candidates:
                eval_side = sc_tracked
    if not eval_side:
        eval_side = str(obs.to_play) if obs.to_play is not None else ""
    scenario_turn_limit = None
    if hasattr(adapter.sim, "scenario_max_turns"):
        try:
            scenario_turn_limit = adapter.sim.scenario_max_turns()
        except Exception:
            scenario_turn_limit = None
    effective_max_steps = int(max_steps)
    unit_count = len(getattr(obs, "units", []) or [])
    if int(max_steps_override) > 0:
        effective_max_steps = int(max_steps_override)
    elif scenario_turn_limit is not None and int(scenario_turn_limit) > 0 and unit_count > 0:
        # Guarantee fidelity to scenario: allow sufficient step budget for all turns,
        # including unit activations, reaction/opportunity fire windows, and combat phases.
        # Step cap acts as a safety watchdog against infinite loops, not an early cutoff.
        scenario_step_budget = int(scenario_turn_limit) * max(int(unit_count) * 3, 25)
        effective_max_steps = max(int(max_steps), scenario_step_budget, 200)
    else:
        effective_max_steps = max(int(max_steps), 200)
    total_reward = 0.0
    steps = 0
    terminal = False
    timeout = False
    win = False
    terminal_reason = ""
    winner_side = ""
    timeout_reason = "turn_unit_budget"
    phase29 = _new_phase29_bucket()
    phase29_by_side: Dict[str, Dict[str, float]] = {}
    trace_rows_by_side: Dict[str, List[Dict[str, object]]] = {}
    sustained_advantage_turns_by_side: Dict[str, int] = {}
    pending_setup_strength_by_side: Dict[str, float] = {}
    macro_planner = MacroStrategyPlanner()
    trace_rows: List[Dict[str, object]] = []
    policy_by_side_norm = {
        _normalize_side_key(side): str(policy_name_for_side or "")
        for side, policy_name_for_side in dict(policy_by_side or {}).items()
        if _normalize_side_key(side)
    }
    if "GE" in policy_by_side_norm and "IT" not in policy_by_side_norm:
        policy_by_side_norm["IT"] = policy_by_side_norm["GE"]
    elif "IT" in policy_by_side_norm and "GE" not in policy_by_side_norm:
        policy_by_side_norm["GE"] = policy_by_side_norm["IT"]
    for _ in range(effective_max_steps):
        if adapter.sim.reached_turn_limit() and not adapter.terminal():
            timeout_reason = "scenario_turn_limit"
            break
        legal = adapter.legal_actions()
        if not legal:
            break
        legal_for_step = list(legal or [])
        legal_actions_raw = [str(a or "") for a in legal_for_step]
        legal_actions_list = list(dict.fromkeys(legal_actions_raw))
        legal_actions_duplicates_collapsed = max(
            0, int(len(legal_actions_raw) - len(legal_actions_list))
        )
        legal_for_step = list(legal_actions_list)
        obs_units = list(getattr(obs, "units", []) or [])
        obs_unit_by_id = build_unit_index(obs_units)
        obs_vp_hexes = list(getattr(obs, "vp_hexes", []) or [])
        obs_vp_owner_by_hex = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
        obs_terrain_type_by_hex = (
            dict(getattr(obs, "terrain_type_by_hex", {}) or {})
            if getattr(obs, "terrain_type_by_hex", None) is not None
            else {}
        )
        obs_terrain_cover_by_hex = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
        obs_terrain_los_block_by_hex = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
        obs_terrain_move_cost_by_hex = dict(getattr(obs, "terrain_move_cost_by_hex", {}) or {})
        obs_fortification_type_by_hex = (
            dict(getattr(obs, "fortification_type_by_hex", {}) or {})
            if getattr(obs, "fortification_type_by_hex", None) is not None
            else {}
        )
        obs_fortification_edge_by_hex = (
            dict(getattr(obs, "fortification_edge_by_hex", {}) or {})
            if getattr(obs, "fortification_edge_by_hex", None) is not None
            else {}
        )
        active_side = _normalize_side_key(obs.to_play) if obs.to_play is not None else ""
        side_hp_before = _side_hp_snapshot(obs_units)
        side_alive_before = _side_alive_snapshot(obs_units)
        active_policy = str(policy_by_side_norm.get(active_side, policy_name)).strip().lower() or str(policy_name)
        collect_this_step = bool(collect_flow_metrics and active_policy != "random")
        capture_legal_count = _count_capture_like_actions(legal_for_step)
        reaction_opts = [a for a in legal_actions_list if _action_kind_from_id(a).startswith("OPPORTUNITY_")]
        if collect_this_step and reaction_opts:
            phase29["reaction_window_count"] += 1
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["reaction_window_count"] += 1
        chosen_prob = 0.0
        margin = 0.0
        latent_top_dims = ""
        mcts_entropy = 0.0
        mcts_total_visits = 0
        mcts_active_actions = 0
        mcts_candidates_duplicates_collapsed = 0
        replan_evaluated_units: list[dict[str, object]] = []
        root_actions_for_explain: List[str] = [str(a) for a in list(legal_for_step or []) if str(a or "").strip()]
        unit_prefilter_requested = False
        acting_unit_id_probe = ""
        mcts_out = None
        policy_top_action = ""
        policy_overridden_by_mcts = None
        predicted_value_root = None
        dynamics_pred_reward = None
        dynamics_next_latent_l2 = None
        dynamics_delta_l2 = None
        policy_top_actions: List[str] = []
        policy_top_probs: List[float] = []
        latent_top_indices: List[int] = []
        latent_top_values: List[float] = []
        latent_l2_norm = None
        decision_top_k_effective = int(decision_top_k or 0)
        if decision_top_k_effective < 0:
            decision_top_k_effective = 0
        why_action_vs_vp: Dict[str, object] = {
            "top_k": int(decision_top_k_effective),
            "chosen_action_id": "",
            "vp_best_action_id": "",
            "delta_score": None,
            "score_components_priority": [],
            "explanation": "N/A (legacy telemetry)",
            "candidate_actions": [],
        }
        mcts_action_candidates: List[Dict[str, object]] = []
        head_states = {h: _head_state("none", "missing") for h in HEAD_NAMES}
        macro_plan = macro_planner.compute_macro_plan(obs)
        if active_policy == "random":
            action = random.choice(legal)
            head_states = {h: _head_state("none", "random_policy_no_model") for h in HEAD_NAMES}
        else:
            priors = None
            values = None
            signs = value_signs_from_to_play(obs, legal)
            xai_root = {}
            root_cache = {}
            if model is not None:
                if str(getattr(model, "encoder_type", "mlp")) == "cnn":
                    obs_vector = observation_to_tensor(
                        obs,
                        channels=int(getattr(model, "observation_channels", 38)),
                        height=int(getattr(model, "observation_height", 16)),
                        width=int(getattr(model, "observation_width", 16)),
                    )
                else:
                    obs_vector = observation_to_vector(obs)
                priors_payload = priors_and_values_from_model(
                    model=model,
                    observation=obs_vector,
                    legal_actions=legal,
                    action_dim=action_dim,
                    unroll_steps=mcts_unroll_steps,
                    discount=mcts_discount,
                    return_root_cache=True,
                )
                if isinstance(priors_payload, tuple) and len(priors_payload) >= 2:
                    priors = priors_payload[0]
                    values = priors_payload[1]
                    root_cache = dict(priors_payload[2] or {}) if len(priors_payload) >= 3 else {}
                else:
                    priors, values = {}, {}
                    root_cache = {}
                try:
                    if root_cache:
                        xai_root = xai_root_signals_from_root_cache(
                            root_cache=dict(root_cache or {}),
                            legal_actions=legal,
                            action_dim=action_dim,
                            topk=5,
                        )
                    else:
                        xai_root = xai_root_signals_from_model(
                            model=model,
                            observation=obs_vector,
                            legal_actions=legal,
                            action_dim=action_dim,
                            topk=5,
                        )
                    idxs = list(xai_root.get("latent_top_indices", []) or [])
                    latent_top_dims = ",".join(f"d{int(i)}" for i in idxs[:5])
                except Exception:
                    latent_top_dims = ""
                    xai_root = {}
            if isinstance(priors, dict) and priors:
                priors = macro_planner.modulate_priors(
                    priors,
                    macro_plan,
                    legal,
                    dict(obs_vp_owner_by_hex),
                    str(active_side),
                    modulation_scale=float(macro_modulation_scale),
                )
            unit_prefilter_requested = bool(unit_prefilter_enabled) or bool(unit_prefilter_replan_enabled)
            mcts_out = None
            action = ""
            planner = choose_action_with_mcts(
                legal_for_step=[str(a) for a in list(legal_for_step or [])],
                obs_units=list(obs_units or []),
                obs_vp_hexes=list(obs_vp_hexes or []),
                active_side=str(active_side),
                obs_vp_owner_by_hex=dict(obs_vp_owner_by_hex),
                unit_prefilter_enabled=bool(unit_prefilter_enabled),
                unit_prefilter_replan_enabled=bool(unit_prefilter_replan_enabled),
                unit_prefilter_top_k=int(unit_prefilter_top_k),
                unit_prefilter_vp_progress_weight=float(unit_prefilter_vp_progress_weight),
                unit_prefilter_capture_opportunity_weight=float(unit_prefilter_capture_opportunity_weight),
                unit_prefilter_threat_weight=float(unit_prefilter_threat_weight),
                terrain_cover_by_hex=dict(obs_terrain_cover_by_hex),
                terrain_los_block_by_hex=dict(obs_terrain_los_block_by_hex),
                priors=(dict(priors) if isinstance(priors, dict) else None),
                values=(dict(values) if isinstance(values, dict) else None),
                signs=(dict(signs) if isinstance(signs, dict) else None),
                mcts_simulations=int(mcts_simulations),
                mcts_c_puct=float(mcts_c_puct),
                mcts_temperature=float(mcts_temperature),
                mcts_dirichlet_alpha=float(mcts_dirichlet_alpha),
                mcts_dirichlet_epsilon=float(mcts_dirichlet_epsilon),
                mcts_q_clip_abs=float(mcts_q_clip_abs),
                mcts_q_root_normalization_mode=str(mcts_q_root_normalization_mode),
                mcts_q_root_normalization_strength=float(mcts_q_root_normalization_strength),
                mcts_value_rescale_mode=str(mcts_value_rescale_mode),
                mcts_value_rescale_temperature=float(mcts_value_rescale_temperature),
                mcts_success_prob_enabled=bool(mcts_success_prob_enabled),
                mcts_success_prob_alpha=float(mcts_success_prob_alpha),
                mcts_success_prob_center=float(mcts_success_prob_center),
                mcts_success_prob_scale=float(mcts_success_prob_scale),
                mcts_success_prob_centered_clip_abs=float(mcts_success_prob_centered_clip_abs),
                mcts_min_root_visits_per_action=int(mcts_min_root_visits_per_action),
                mcts_min_root_visits_top_n=int(mcts_min_root_visits_top_n),
                run_policy_mcts_fn=_run_policy_mcts,
                unit_prefilter_ranking_fn=ezv2_unit_prefilter_ranking,
            )
            unit_prefilter_requested = bool(planner.get("unit_prefilter_requested", False))
            mcts_out = planner.get("mcts_out", None)
            action = str(planner.get("action", "") or "")
            replan_evaluated_units = list(planner.get("replan_evaluated_units", []) or [])
            mcts_post = _mcts_resolve_action_and_root_metrics(
                mcts_out=mcts_out,
                sampled_action=str(action),
                side=str(active_side),
                obs_vp_hexes=list(obs_vp_hexes or []),
                vp_owner_by_hex=dict(obs_vp_owner_by_hex),
                select_action_with_probability_tie_break_fn=_select_action_with_probability_tie_break,
            )
            action = str(mcts_post["action"])
            action_selection_source = str(mcts_post["action_selection_source"])
            probs = list(mcts_post["probs"])
            visit_counts = list(mcts_post["visit_counts"])
            mcts_breakdown_by_action = dict(mcts_post["mcts_breakdown_by_action"])
            chosen_prob = float(mcts_post["chosen_prob"])
            margin = float(mcts_post["margin"])
            mcts_entropy = float(mcts_post["mcts_entropy"])
            mcts_total_visits = int(mcts_post["mcts_total_visits"])
            mcts_active_actions = int(mcts_post["mcts_active_actions"])
            visits_by_action = dict(mcts_post["visits_by_action"])
            root_actions_for_explain = list(mcts_post["root_actions_for_explain"])
            if not root_actions_for_explain:
                root_actions_for_explain = [str(a) for a in list(legal or []) if str(a or "").strip()]
            acting_unit_id_probe = str(action or "").split(":")
            acting_unit_id_probe = acting_unit_id_probe[1] if len(acting_unit_id_probe) > 1 else ""
            acting_unit_probe = obs_unit_by_id.get(str(acting_unit_id_probe), None)
            acting_q_probe = (
                _to_int_or_none(_field(acting_unit_probe, "q", None))
                if acting_unit_probe is not None
                else None
            )
            acting_r_probe = (
                _to_int_or_none(_field(acting_unit_probe, "r", None))
                if acting_unit_probe is not None
                else None
            )
            why_action_vs_vp = _build_why_action_vs_vp(
                legal_actions=root_actions_for_explain,
                chosen_action=str(action),
                priors_by_action=priors if isinstance(priors, dict) else None,
                values_by_action=values if isinstance(values, dict) else None,
                value_sign_by_action=signs if isinstance(signs, dict) else None,
                visits_by_action=visits_by_action,
                c_puct=float(mcts_c_puct),
                dynamics_pred_reward=None,
                acting_unit_q=acting_q_probe,
                acting_unit_r=acting_r_probe,
                step_units_snapshot=obs_units,
                vp_hexes=obs_vp_hexes,
                active_side=str(active_side),
                vp_owner_by_hex=dict(obs_vp_owner_by_hex),
                top_k=decision_top_k_effective,
                q_clip_abs=float(mcts_q_clip_abs),
                value_rescale_mode=str(mcts_value_rescale_mode),
                value_rescale_temperature=float(mcts_value_rescale_temperature),
            )
            mcts_action_candidates = list(
                why_action_vs_vp.get("candidate_actions", []) or []
            )
            chosen_action_text = str(action or "")
            mcts_action_candidates, mcts_candidates_duplicates_collapsed = _mcts_enrich_candidates_from_breakdown(
                mcts_action_candidates=list(mcts_action_candidates or []),
                mcts_breakdown_by_action=dict(mcts_breakdown_by_action),
                mcts_out=mcts_out,
                probs=list(probs),
                visit_total=int(mcts_total_visits),
                chosen_action_text=chosen_action_text,
                action_selection_source=str(action_selection_source),
                dedupe_candidates_fn=_es_dedupe_candidates_action_unit,
            )
            mcts_action_candidates = canonicalize_decision_candidates(
                candidate_rows=list(mcts_action_candidates or []),
                chosen_action_id=str(action),
                default_policy_prior_zero=False,
            )
            if isinstance(why_action_vs_vp, dict):
                why_action_vs_vp["candidate_actions"] = list(mcts_action_candidates)
                why_action_vs_vp["duplicates_collapsed"] = int(mcts_candidates_duplicates_collapsed)
            if model is not None:
                policy_top_actions = [str(a) for a in (xai_root.get("policy_top_actions", []) or [])]
                policy_top_probs = [float(v) for v in (xai_root.get("policy_top_probs", []) or [])]
                policy_top_action = str(policy_top_actions[0]) if policy_top_actions else ""
                policy_overridden_by_mcts = (
                    int(policy_top_action != str(action))
                    if policy_top_action
                    else None
                )
                latent_top_indices = [int(v) for v in (xai_root.get("latent_top_indices", []) or [])]
                latent_top_values = [float(v) for v in (xai_root.get("latent_top_values", []) or [])]
                latent_l2_norm = (
                    float(xai_root.get("latent_l2_norm", 0.0))
                    if xai_root.get("latent_l2_norm", None) is not None
                    else None
                )
                predicted_value_root = (
                    float(xai_root.get("predicted_value_root", 0.0))
                    if xai_root.get("predicted_value_root", None) is not None
                    else None
                )
                try:
                    if root_cache:
                        xai_dyn = xai_dynamics_signals_for_action_from_hidden(
                            model=model,
                            hidden=root_cache.get("hidden", None),
                            chosen_action_id=action,
                            action_dim=action_dim,
                        )
                    else:
                        xai_dyn = xai_dynamics_signals_for_action(
                            model=model,
                            observation=obs_vector,
                            chosen_action_id=action,
                            action_dim=action_dim,
                        )
                except Exception:
                    xai_dyn = {}
                dynamics_pred_reward = (
                    float(xai_dyn.get("dynamics_pred_reward", 0.0))
                    if xai_dyn.get("dynamics_pred_reward", None) is not None
                    else None
                )
                dynamics_next_latent_l2 = (
                    float(xai_dyn.get("dynamics_next_latent_l2", 0.0))
                    if xai_dyn.get("dynamics_next_latent_l2", None) is not None
                    else None
                )
                dynamics_delta_l2 = (
                    float(xai_dyn.get("dynamics_delta_l2", 0.0))
                    if xai_dyn.get("dynamics_delta_l2", None) is not None
                    else None
                )
                if isinstance(why_action_vs_vp, dict):
                    why_action_vs_vp["candidate_actions"] = list(mcts_action_candidates or [])
                head_states = {
                    "policy": _head_state(
                        "complete" if policy_top_actions and policy_top_probs else "partial",
                        "" if policy_top_actions and policy_top_probs else "policy_topk_missing",
                    ),
                    "value": _head_state(
                        "complete" if predicted_value_root is not None else "none",
                        "" if predicted_value_root is not None else "value_root_missing",
                    ),
                    "reward": _head_state(
                        "complete" if dynamics_pred_reward is not None else "none",
                        "" if dynamics_pred_reward is not None else "dynamics_reward_missing",
                    ),
                    "objective": _head_state("partial", "objective_signal_not_computed"),
                    "consistency": _head_state(
                        "complete" if (latent_top_indices and latent_top_values) else "partial",
                        "" if (latent_top_indices and latent_top_values) else "latent_topk_missing",
                    ),
                    "mcts": _head_state("complete", ""),
                }
                if "threat_coverage_ratio" in xai_root:
                    head_states["threat_map"] = _head_state("complete", "")
                if "predicted_exchange_ratio" in xai_root:
                    head_states["attrition"] = _head_state("complete", "")
                if "suppression_risk_score" in xai_root:
                    head_states["morale"] = _head_state("complete", "")
            else:
                head_states = {h: _head_state("none", "model_not_loaded") for h in HEAD_NAMES}
        action_kind = _action_kind_from_id(action)
        capture_like_action_taken = _is_capture_like_action_kind(action_kind)
        objective_signal = None
        objective_had_opportunity = 0
        objective_progress_delta = None
        objective_converted = 0
        objective_min_dist_before = -1.0
        objective_min_dist_after = -1.0
        objective_best_vp_id = ""
        vp_distance_vector = {}
        before_vp_owner = dict(obs_vp_owner_by_hex)
        telemetry_coverage_status, telemetry_coverage_reason = _compute_coverage_status(head_states)
        if collect_this_step:
            phase29["xai_decision_steps"] += 1
            phase29["xai_policy_confidence_sum"] += float(chosen_prob)
            phase29["xai_policy_margin_sum"] += float(margin)
            if str(latent_top_dims).strip():
                phase29["xai_latent_signal_steps"] += 1

            if "threat_coverage_ratio" in xai_root:
                phase29["threat_coverage_sum"] += float(xai_root.get("threat_coverage_ratio", 0.0))
                phase29["threat_max_sum"] += float(xai_root.get("threat_max", 0.0))
                phase29["threat_mean_sum"] += float(xai_root.get("threat_mean", 0.0))
                phase29["tactical_steps"] += 1
            if "predicted_exchange_ratio" in xai_root:
                phase29["attrition_exchange_sum"] += float(xai_root.get("predicted_exchange_ratio", 0.0))
                phase29["attrition_friendly_cas_sum"] += float(xai_root.get("predicted_friendly_casualties", 0.0))
                phase29["attrition_enemy_cas_sum"] += float(xai_root.get("predicted_enemy_casualties", 0.0))
                phase29["attrition_steps"] += 1
            if "suppression_risk_score" in xai_root:
                phase29["morale_risk_sum"] += float(xai_root.get("suppression_risk_score", 0.0))
                phase29["morale_steps"] += 1
            if "objective_pred_prob" in xai_root:
                phase29["objective_pred_prob_sum"] += float(xai_root.get("objective_pred_prob", 0.0))
                phase29["objective_steps"] += 1

            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["xai_decision_steps"] += 1
            side_bucket["xai_policy_confidence_sum"] += float(chosen_prob)
            side_bucket["xai_policy_margin_sum"] += float(margin)
            if str(latent_top_dims).strip():
                side_bucket["xai_latent_signal_steps"] += 1

            if "threat_coverage_ratio" in xai_root:
                side_bucket["threat_coverage_sum"] += float(xai_root.get("threat_coverage_ratio", 0.0))
                side_bucket["threat_max_sum"] += float(xai_root.get("threat_max", 0.0))
                side_bucket["threat_mean_sum"] += float(xai_root.get("threat_mean", 0.0))
                side_bucket["tactical_steps"] += 1
            if "predicted_exchange_ratio" in xai_root:
                side_bucket["attrition_exchange_sum"] += float(xai_root.get("predicted_exchange_ratio", 0.0))
                side_bucket["attrition_friendly_cas_sum"] += float(xai_root.get("predicted_friendly_casualties", 0.0))
                side_bucket["attrition_enemy_cas_sum"] += float(xai_root.get("predicted_enemy_casualties", 0.0))
                side_bucket["attrition_steps"] += 1
            if "suppression_risk_score" in xai_root:
                side_bucket["morale_risk_sum"] += float(xai_root.get("suppression_risk_score", 0.0))
                side_bucket["morale_steps"] += 1
            if "objective_pred_prob" in xai_root:
                side_bucket["objective_pred_prob_sum"] += float(xai_root.get("objective_pred_prob", 0.0))
                side_bucket["objective_steps"] += 1
        action_parts = str(action or "").split(":")
        acting_unit_id = action_parts[1] if len(action_parts) > 1 else ""
        acting_unit = obs_unit_by_id.get(str(acting_unit_id), None)
        transition = adapter.apply(action)
        transition_info = getattr(transition, "info", None)
        (
            attack_dice_rolls,
            defense_dice_rolls,
            attack_components_by_die,
            defense_components_by_die,
            runtime_events,
        ) = _tm_extract_actor_combat_dice_signals(
            transition_info=transition_info,
            acting_unit_id=str(acting_unit_id),
        )
        post_units = getattr(transition.state, "units", []) or []
        post_obs = adapter.observation()
        after_vp_owner = dict(getattr(post_obs, "vp_owner_by_hex", {}) or {})
        vp_captures_eval = 0
        for key, owner_before in before_vp_owner.items():
            owner_after = str(after_vp_owner.get(key, ""))
            if str(owner_before) != owner_after and owner_after == str(active_side):
                vp_captures_eval += 1
        immediate_capture_legal_count = _count_immediate_vp_capture_move_options(
            side=str(active_side),
            legal_actions=legal_for_step,
            vp_hexes=obs_vp_hexes,
            vp_owner_by_hex=before_vp_owner,
        )
        immediate_capture_taken = _is_immediate_vp_capture_move_taken(
            side=str(active_side),
            chosen_action_id=str(action),
            vp_hexes=obs_vp_hexes,
            before_vp_owner_by_hex=before_vp_owner,
            after_vp_owner_by_hex=after_vp_owner,
        )
        objective_signal = objective_step_signal(
            side=str(active_side),
            vp_hexes=obs_vp_hexes,
            legal_actions=legal_for_step,
            before_units=_units_snapshot(obs_units),
            before_vp_owner_by_hex=before_vp_owner,
            after_units=_units_snapshot(getattr(post_obs, "units", []) or []),
            after_vp_owner_by_hex=after_vp_owner,
            legal_capture_options=int(immediate_capture_legal_count),
            capture_taken=bool(immediate_capture_taken),
            vp_captures=int(vp_captures_eval),
            vp_gain_for_side=int(vp_captures_eval),
        )
        objective_had_opportunity = int(objective_signal.objective_had_opportunity)
        objective_progress_delta = float(objective_signal.objective_progress_delta)
        objective_converted = int(objective_signal.objective_converted)
        objective_min_dist_before = float(objective_signal.objective_min_dist_before)
        objective_min_dist_after = float(objective_signal.objective_min_dist_after)
        objective_best_vp_id = str(objective_signal.objective_best_vp_id)
        vp_distance_vector = dict(objective_signal.vp_distance_vector)
        why_action_vs_vp = _backfill_why_action_vs_vp_from_observed_transition(
            why_action_vs_vp=why_action_vs_vp,
            chosen_action=str(action),
            objective_progress_delta=objective_progress_delta,
            objective_best_vp_id=objective_best_vp_id,
            legal_actions=legal_actions_list,
        )
        mcts_action_candidates = list(why_action_vs_vp.get("candidate_actions", []) or [])
        candidate_by_action = build_candidate_index(list(mcts_action_candidates or []))
        selected_candidate = first_or_by_action(
            row_by_action=candidate_by_action,
            action_id=str(action),
            fallback_rows=list(mcts_action_candidates or []),
        )
        decision_rank = int(dict(selected_candidate or {}).get("decision_rank", 0) or 0)
        selected_candidate_dc = (
            dict((selected_candidate or {}).get("decision_components", {}) or {})
            if isinstance((selected_candidate or {}).get("decision_components", None), dict)
            else {}
        )
        strategy_label = str(
            selected_candidate_dc.get("tie_break_source", "")
            or why_action_vs_vp.get("explanation", "")
            or ""
        )
        if collect_this_step:
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            vp_capture_taken = _is_vp_capture_taken_for_metrics(
                vp_captures_eval=int(vp_captures_eval),
                objective_converted=int(objective_converted),
                immediate_capture_taken=bool(immediate_capture_taken),
                capture_like_action_taken=bool(capture_like_action_taken),
            )
            if int(objective_had_opportunity) > 0:
                phase29["xai_vp_capture_opportunity_steps"] += 1
                side_bucket["xai_vp_capture_opportunity_steps"] += 1
                if vp_capture_taken:
                    phase29["xai_vp_capture_taken_steps"] += 1
                    side_bucket["xai_vp_capture_taken_steps"] += 1
            if int(immediate_capture_legal_count) > 0:
                phase29["xai_vp_immediate_capture_opportunity_steps"] += 1
                side_bucket["xai_vp_immediate_capture_opportunity_steps"] += 1
                if immediate_capture_taken:
                    phase29["xai_vp_immediate_capture_taken_steps"] += 1
                    side_bucket["xai_vp_immediate_capture_taken_steps"] += 1
        if isinstance(head_states, dict):
            if objective_min_dist_before >= 0.0 and objective_min_dist_after >= 0.0:
                head_states["objective"] = _head_state("complete", "")
            else:
                head_states["objective"] = _head_state("partial", "objective_signal_missing_vp_context")
            telemetry_coverage_status, telemetry_coverage_reason = _compute_coverage_status(head_states)
        side_hp_after = _side_hp_snapshot(post_units)
        side_alive_after = _side_alive_snapshot(post_units)
        enemy_damage = 0.0
        enemy_kills = 0
        for side_k, hp_before in side_hp_before.items():
            if _normalize_side_key(side_k) == _normalize_side_key(active_side):
                continue
            enemy_damage += max(0.0, float(hp_before - float(side_hp_after.get(side_k, hp_before))))
            enemy_kills += max(0, int(side_alive_before.get(side_k, 0) - side_alive_after.get(side_k, 0)))
        runtime_damage_actor, runtime_kills_actor = _tm_extract_actor_damage_kills_from_runtime_events(
            runtime_events=runtime_events,
            acting_unit_id=str(acting_unit_id),
        )
        enemy_damage = max(float(enemy_damage), float(runtime_damage_actor))
        enemy_kills = max(int(enemy_kills), int(runtime_kills_actor))
        if isinstance(transition_info, dict):
            info_damage_actor = _tm_metric_from_row(
                transition_info,
                "damage_dealt",
                "damage",
                "enemy_damage",
                default=float(enemy_damage),
            )
            info_kills_actor = _tm_metric_from_row(
                transition_info,
                "kills_dealt",
                "kills",
                "enemy_kills",
                default=float(enemy_kills),
            )
            if float(info_damage_actor) > 0.0 or float(enemy_damage) <= 0.0:
                enemy_damage = float(info_damage_actor)
            if (
                int(round(float(info_kills_actor))) > 0
                or int(enemy_kills) <= 0
            ):
                enemy_kills = int(round(float(info_kills_actor)))
        prefilter_info = dict(transition_info or {}) if isinstance(transition_info, dict) else {}
        raw_unit_prefilter_enabled = prefilter_info.get("unit_prefilter_enabled", None)
        unit_prefilter_selected_unit_id = str(
            prefilter_info.get(
                "unit_prefilter_selected_unit_id",
                "",
            )
            or ""
        )
        if not unit_prefilter_selected_unit_id.strip():
            unit_prefilter_selected_unit_id = "__none__"
        prefilter_metrics = resolve_prefilter_counts(
            unit_prefilter_requested=bool(unit_prefilter_requested),
            active_policy=str(active_policy),
            raw_unit_prefilter_enabled=raw_unit_prefilter_enabled,
            constrained_from_info=_to_int_or_none(prefilter_info.get("unit_prefilter_constrained_count", None)),
            global_from_info=_to_int_or_none(prefilter_info.get("unit_prefilter_global_count", None)),
            runtime_constrained_count=int(len(list(legal_for_step or []))),
            runtime_global_count=int(len(list(legal_actions_list or []))),
        )
        unit_prefilter_enabled = bool(prefilter_metrics.get("unit_prefilter_enabled", False))
        unit_prefilter_enabled_source = str(prefilter_metrics.get("unit_prefilter_enabled_source", "missing"))
        unit_prefilter_constrained_count = prefilter_metrics.get("unit_prefilter_constrained_count", None)
        unit_prefilter_constrained_count_source = str(
            prefilter_metrics.get("unit_prefilter_constrained_count_source", "missing")
        )
        unit_prefilter_global_count = prefilter_metrics.get("unit_prefilter_global_count", None)
        unit_prefilter_global_count_source = str(
            prefilter_metrics.get("unit_prefilter_global_count_source", "missing")
        )
        if collect_this_step and action_kind == "OPPORTUNITY_FIRE":
            phase29["reaction_fire_count"] += 1
            phase29["reaction_fire_damage_sum"] += float(enemy_damage)
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["reaction_fire_count"] += 1
            side_bucket["reaction_fire_damage_sum"] += float(enemy_damage)
            if int(enemy_kills) > 0:
                phase29["reaction_fire_kill_conversions"] += 1
                side_bucket["reaction_fire_kill_conversions"] += 1
        elif collect_this_step and action_kind == "OPPORTUNITY_SKIP":
            phase29["reaction_fire_skipped_count"] += 1
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["reaction_fire_skipped_count"] += 1
        if collect_this_step and ("ASSAULT" in action_kind or action_kind in {"MELEE", "ASSAULT_MELEE"}):
            phase29["melee_attempts"] += 1
            phase29["melee_damage_sum"] += float(enemy_damage)
            phase29["melee_kills_sum"] += float(enemy_kills)
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["melee_attempts"] += 1
            side_bucket["melee_damage_sum"] += float(enemy_damage)
            side_bucket["melee_kills_sum"] += float(enemy_kills)
            if float(enemy_damage) > 0.0 or int(enemy_kills) > 0:
                phase29["melee_success_count"] += 1
                side_bucket["melee_success_count"] += 1
            bucket = _es_assault_advantage_bucket(chosen_prob=float(chosen_prob), margin=float(margin), legal_count=len(legal_for_step))
            phase29[f"assault_{bucket}_count"] += 1
            side_bucket[f"assault_{bucket}_count"] += 1
        if transition.done:
            terminal_reason = str(transition.state.end_reason or "natural_terminal")
            winner = transition.state.winner
            winner_side = str(winner) if winner is not None else ""
            if winner is None:
                total_reward += 0.0
                win = False
            else:
                is_selfplay = (
                    len(set(str(p).strip().lower() for p in policy_by_side.values())) == 1
                    if policy_by_side
                    else False
                )
                if is_selfplay:
                    won = str(winner) == eval_side
                else:
                    won = str(winner) in eval_candidates if eval_candidates else (str(winner) == eval_side)
                total_reward += 1.0 if won else -1.0
                win = won
        target_q = _to_int_or_none(action_parts[-2]) if len(action_parts) >= 4 else None
        target_r = _to_int_or_none(action_parts[-1]) if len(action_parts) >= 4 else None
        acting_q = _to_int_or_none(_field(acting_unit, "q", None)) if acting_unit is not None else None
        acting_r = _to_int_or_none(_field(acting_unit, "r", None)) if acting_unit is not None else None
        attack_distance = -1.0
        if isinstance(acting_q, int) and isinstance(acting_r, int) and isinstance(target_q, int) and isinstance(target_r, int):
            attack_distance = float(max(abs(int(acting_q) - int(target_q)), abs(int(acting_r) - int(target_r))))
        cover_map = dict(obs_terrain_cover_by_hex)
        los_map = dict(obs_terrain_los_block_by_hex)
        key_qr = f"{int(target_q)},{int(target_r)}" if isinstance(target_q, int) and isinstance(target_r, int) else ""
        target_cover = float(cover_map.get(key_qr, -1.0)) if key_qr else -1.0
        target_los = float(los_map.get(key_qr, -1.0)) if key_qr else -1.0

        legal_indexes = build_legal_action_indexes(
            legal_actions_list=list(legal_actions_list or []),
            acting_unit_id=str(acting_unit_id),
            parse_action_target_hex_fn=_parse_action_target_hex,
        )
        legal_actions_decoded_target_qr = list(legal_indexes.get("legal_actions_decoded_target_qr", []) or [])
        acting_unit_action_catalog = list(legal_indexes.get("acting_unit_action_catalog", []) or [])
        signal_values = resolve_step_signals(
            action=str(action),
            mcts_action_candidates=list(mcts_action_candidates or []),
            selected_candidate=dict(selected_candidate or {}),
            transition_info=transition_info,
            objective_had_opportunity=int(objective_had_opportunity),
            objective_min_dist_before=float(objective_min_dist_before),
            objective_progress_delta=objective_progress_delta,
            reward_shaping=dict(reward_shaping or {}),
            action_kind=str(action_kind),
            active_side=str(active_side),
            eval_side=str(eval_side),
            before_vp_owner=dict(before_vp_owner),
            after_vp_owner=dict(after_vp_owner),
            obs_vp_hexes=list(obs_vp_hexes or []),
            obs_units=list(obs_units or []),
            post_obs_units=list(getattr(post_obs, "units", []) or []),
            vp_captures_eval=int(vp_captures_eval),
            enemy_damage=float(enemy_damage),
            sustained_advantage_turns_by_side=dict(sustained_advantage_turns_by_side or {}),
            pending_setup_strength_by_side=dict(pending_setup_strength_by_side or {}),
            legal_actions_list=list(legal_actions_list or []),
            field_fn=_field,
            resolve_vp_horizon_selected_fields_fn=_es_resolve_vp_horizon_selected_fields,
            vp_horizon_soft_components_for_step_fn=_vp_horizon_soft_components_for_step,
            normalize_side_key_fn=_normalize_side_key,
            units_snapshot_fn=_units_snapshot,
            resolve_global_strategy_component_fn=resolve_global_strategy_component,
            reaction_fire_soft_signal_for_step_fn=_reaction_fire_soft_signal_for_step,
            reaction_exposure_component_for_step_fn=_reaction_exposure_component_for_step,
            obs_enemy_reaction_fire_risk_for_step_fn=_obs_enemy_reaction_fire_risk_for_step,
        )
        selected_candidate = dict(signal_values.get("selected_candidate", {}) or {})
        decision_rank = int(selected_candidate.get("decision_rank", decision_rank) or 0)
        selected_components = dict(signal_values.get("selected_components", {}) or {})
        selected_tie_break_term = signal_values.get("selected_tie_break_term", None)
        selected_vp_horizon_steps = signal_values.get("selected_vp_horizon_steps", None)
        selected_vp_horizon_signal = signal_values.get("selected_vp_horizon_signal", None)
        selected_vp_horizon_component = signal_values.get("selected_vp_horizon_component", None)
        vp_horizon_source = str(signal_values.get("vp_horizon_source", "missing") or "missing")
        vp_horizon_available = bool(signal_values.get("vp_horizon_available", False))
        (
            unit_positions_snapshot,
            unit_hp_snapshot,
            unit_alive_snapshot,
            unit_suppressed_snapshot,
        ) = build_post_unit_snapshots(
            post_units=list(post_units or []),
            runtime_events=list(runtime_events or []),
            suppressed_from_events_fn=_tm_extract_unit_suppressed_from_runtime_events,
        )
        mcts_prior_value = signal_values.get("mcts_prior_value", None)
        mcts_q_value = signal_values.get("mcts_q_value", None)
        mcts_u_value = signal_values.get("mcts_u_value", None)
        decision_score_value = signal_values.get("decision_score_value", None)
        selected_success_proxy = signal_values.get("selected_success_proxy", None)
        selected_success_component = signal_values.get("selected_success_component", None)
        objective_soft_component_value = signal_values.get("objective_soft_component_value", None)
        objective_soft_source = str(signal_values.get("objective_soft_source", "missing") or "missing")
        objective_soft_available = bool(signal_values.get("objective_soft_available", False))
        objective_soft_reason = str(signal_values.get("objective_soft_reason", "missing") or "missing")
        global_strategy_soft_component_value = signal_values.get("global_strategy_soft_component_value", None)
        global_strategy_soft_source = str(signal_values.get("global_strategy_soft_source", "missing") or "missing")
        global_strategy_soft_available = bool(signal_values.get("global_strategy_soft_available", False))
        reaction_fire_soft_component_value = signal_values.get("reaction_fire_soft_component_value", None)
        reaction_fire_soft_source = str(signal_values.get("reaction_fire_soft_source", "missing") or "missing")
        reaction_fire_soft_available = bool(signal_values.get("reaction_fire_soft_available", False))
        obs_enemy_reaction_fire_risk_value = signal_values.get("obs_enemy_reaction_fire_risk_value", None)
        reaction_exposure_component_value = signal_values.get("reaction_exposure_component_value", None)
        reaction_exposure_source = str(signal_values.get("reaction_exposure_source", "missing") or "missing")
        reaction_exposure_available = bool(signal_values.get("reaction_exposure_available", False))
        sustained_advantage_turns_by_side = dict(
            signal_values.get("sustained_advantage_turns_by_side", {}) or {}
        )
        pending_setup_strength_by_side = dict(
            signal_values.get("pending_setup_strength_by_side", {}) or {}
        )
        step_prior_boost_applied = float(
            max(
                0.0,
                macro_planner.compute_action_boost(
                    str(action),
                    macro_plan,
                    dict(getattr(obs, "vp_owner_by_hex", {}) or {}),
                    str(getattr(obs, "to_play", "") or ""),
                    modulation_scale=float(macro_modulation_scale),
                )
                - 1.0,
            )
        )
        trace_row = build_trace_row(
            core=StepCoreData(
                step=int(steps),
                game_turn=int(getattr(obs, "turn", 0) or 0),
                turn=int(getattr(transition.state, "turn", 0) or 0),
                active_side=str(active_side),
                action=str(action),
                action_kind=str(action_kind),
                chosen_prob=float(chosen_prob),
                margin=float(margin),
                mcts_entropy=float(mcts_entropy),
                mcts_total_visits=int(mcts_total_visits),
                mcts_active_actions=int(mcts_active_actions),
                root_actions_for_explain=list(root_actions_for_explain),
                legal_actions_list=list(legal_actions_list),
                legal_actions_duplicates_collapsed=int(legal_actions_duplicates_collapsed),
                legal_actions_decoded_target_qr=list(legal_actions_decoded_target_qr),
                acting_unit_action_catalog=list(acting_unit_action_catalog),
                acting_unit_id=str(acting_unit_id),
                acting_unit=acting_unit,
                transition_reward=float(transition.reward),
                transition_done=bool(transition.done),
                enemy_damage=float(enemy_damage),
                enemy_kills=int(enemy_kills),
                action_parts=list(action_parts),
                target_q=(target_q if isinstance(target_q, int) else None),
                target_r=(target_r if isinstance(target_r, int) else None),
                attack_distance=float(attack_distance),
                target_cover=float(target_cover),
                target_los=float(target_los),
                capture_legal_count=int(capture_legal_count),
                capture_like_action_taken=bool(capture_like_action_taken),
            ),
            signals=StepSignalData(
                mcts_prior_value=mcts_prior_value,
                mcts_q_value=mcts_q_value,
                mcts_u_value=mcts_u_value,
                decision_score_value=decision_score_value,
                selected_success_proxy=selected_success_proxy,
                selected_success_component=selected_success_component,
                selected_components=dict(selected_components),
                selected_vp_horizon_steps=selected_vp_horizon_steps,
                selected_vp_horizon_signal=selected_vp_horizon_signal,
                selected_vp_horizon_component=selected_vp_horizon_component,
                vp_horizon_source=str(vp_horizon_source),
                vp_horizon_available=bool(vp_horizon_available),
                objective_soft_component_value=objective_soft_component_value,
                objective_soft_source=str(objective_soft_source),
                objective_soft_available=bool(objective_soft_available),
                objective_soft_reason=str(objective_soft_reason),
                global_strategy_soft_component_value=global_strategy_soft_component_value,
                global_strategy_soft_source=str(global_strategy_soft_source),
                global_strategy_soft_available=bool(global_strategy_soft_available),
                reaction_fire_soft_component_value=reaction_fire_soft_component_value,
                reaction_fire_soft_source=str(reaction_fire_soft_source),
                reaction_fire_soft_available=bool(reaction_fire_soft_available),
                reaction_exposure_component_value=reaction_exposure_component_value,
                reaction_exposure_source=str(reaction_exposure_source),
                reaction_exposure_available=bool(reaction_exposure_available),
                objective_had_opportunity=int(objective_had_opportunity),
                objective_min_dist_before=float(objective_min_dist_before),
                objective_min_dist_after=float(objective_min_dist_after),
                objective_progress_delta=objective_progress_delta,
                selected_tie_break_term=selected_tie_break_term,
                objective_converted=int(objective_converted),
                objective_best_vp_id=str(objective_best_vp_id),
                strategy_label=str(strategy_label),
                vp_distance_vector=dict(vp_distance_vector),
                obs_enemy_reaction_fire_risk_value=obs_enemy_reaction_fire_risk_value,
                macro_posture=str(macro_plan.posture),
                macro_target_vp_id=str(macro_plan.target_vp_id or ""),
                unit_macro_role=str(macro_plan.get_role(acting_unit_id_probe)),
                role_assigned=str(macro_plan.get_role(acting_unit_id_probe)),
                role_is_mutated=bool(macro_plan.is_mutated(acting_unit_id_probe)),
                role_mutation_reason=str(macro_plan.get_mutation_reason(acting_unit_id_probe)),
                prior_boost_applied=step_prior_boost_applied,
                badge_label=f"{macro_plan.get_role(acting_unit_id_probe).replace('ROLE_', '')}",
            ),
            prefilter=StepPrefilterData(
                unit_prefilter_enabled=bool(unit_prefilter_enabled),
                unit_prefilter_enabled_source=str(unit_prefilter_enabled_source),
                unit_prefilter_selected_unit_id=str(unit_prefilter_selected_unit_id),
                replan_evaluated_units=list(replan_evaluated_units),
                unit_prefilter_constrained_count=(
                    int(unit_prefilter_constrained_count)
                    if unit_prefilter_constrained_count is not None
                    else None
                ),
                unit_prefilter_constrained_count_source=str(unit_prefilter_constrained_count_source),
                unit_prefilter_global_count=(
                    int(unit_prefilter_global_count)
                    if unit_prefilter_global_count is not None
                    else None
                ),
                unit_prefilter_global_count_source=str(unit_prefilter_global_count_source),
            ),
            mcts_out=mcts_out,
            latent_top_dims=str(latent_top_dims),
            policy_top_actions=list(policy_top_actions),
            policy_top_probs=list(policy_top_probs),
            mcts_action_candidates=list(mcts_action_candidates),
            selected_candidate=dict(selected_candidate),
            decision_rank=int(decision_rank),
            mcts_candidates_duplicates_collapsed=int(mcts_candidates_duplicates_collapsed),
            why_action_vs_vp=dict(why_action_vs_vp),
            policy_top_action=str(policy_top_action),
            policy_overridden_by_mcts=policy_overridden_by_mcts,
            latent_top_indices=list(latent_top_indices),
            latent_top_values=list(latent_top_values),
            latent_l2_norm=latent_l2_norm,
            predicted_value_root=predicted_value_root,
            dynamics_pred_reward=dynamics_pred_reward,
            dynamics_next_latent_l2=dynamics_next_latent_l2,
            dynamics_delta_l2=dynamics_delta_l2,
            immediate_capture_legal_count=int(immediate_capture_legal_count),
            unit_positions_snapshot=list(unit_positions_snapshot),
            unit_hp_snapshot=dict(unit_hp_snapshot),
            unit_alive_snapshot=dict(unit_alive_snapshot),
            unit_suppressed_snapshot=dict(unit_suppressed_snapshot),
            before_vp_owner=dict(before_vp_owner),
            after_vp_owner=dict(after_vp_owner),
            transition_info=transition_info,
            obs_terrain_type_map=dict(obs_terrain_type_by_hex),
            obs_terrain_cover_map=dict(obs_terrain_cover_by_hex),
            obs_terrain_los_block_map=dict(obs_terrain_los_block_by_hex),
            obs_terrain_move_cost_map=dict(obs_terrain_move_cost_by_hex),
            obs_fortification_type_map=dict(obs_fortification_type_by_hex),
            obs_fortification_edge_map=dict(obs_fortification_edge_by_hex),
            head_states=dict(head_states),
            telemetry_coverage_status=str(telemetry_coverage_status),
            telemetry_coverage_reason=str(telemetry_coverage_reason),
            attack_dice_rolls=list(attack_dice_rolls),
            defense_dice_rolls=list(defense_dice_rolls),
            attack_components_by_die=dict(attack_components_by_die),
            defense_components_by_die=dict(defense_components_by_die),
            runtime_events=list(runtime_events),
            post_units_snapshot=_decorate_units_with_macro_plan(
                _units_snapshot(post_units),
                macro_plan,
                acting_unit_id=acting_unit_id_probe,
                prior_boost=step_prior_boost_applied,
            ),
            field_fn=_field,
            trace_detail_level=str(trace_detail_level or "core"),
        )
        trace_rows.append(trace_row)
        row_side = _normalize_side_key((trace_row or {}).get("unit_side", ""))
        if row_side:
            trace_rows_by_side.setdefault(row_side, []).append(trace_row)
        steps += 1
        obs = post_obs
        if transition.done:
            terminal = True
            break
    if not terminal:
        timeout_transition = adapter.sim.resolve_timeout(
            action_id="TIMEOUT",
            end_reason=timeout_reason,
        )
        winner = timeout_transition.state.winner
        winner_side = str(winner) if winner is not None else ""
        if winner is None:
            total_reward += 0.0
            win = False
        else:
            is_selfplay = (
                len(set(str(p).strip().lower() for p in policy_by_side.values())) == 1
                if policy_by_side
                else False
            )
            if is_selfplay:
                won = str(winner) == eval_side
            else:
                won = str(winner) in eval_candidates if eval_candidates else (str(winner) == eval_side)
            total_reward += 1.0 if won else -1.0
            win = won
        terminal = True
        timeout = True
        terminal_reason = str(timeout_transition.state.end_reason or timeout_reason)
    final_vp_by_side = _vp_control_counts()
    scenario_outcome = _scenario_outcome_from_final_vp(final_vp_by_side)
    phase29_summary = _finalize_phase29(phase29)
    phase29_summary.update(_compute_decision_diagnostics_kpis(trace_rows))
    phase29_summary["by_side"] = {
        str(side): {
            **_finalize_phase29(bucket),
            **_compute_decision_diagnostics_kpis(list(trace_rows_by_side.get(_normalize_side_key(side), []))),
        }
        for side, bucket in phase29_by_side.items()
    }
    return (
        int(seed),
        total_reward,
        steps,
        terminal,
        timeout,
        win,
        terminal_reason,
        initial_vp_by_side,
        final_vp_by_side,
        winner_side,
        scenario_outcome,
        phase29_summary,
        trace_rows,
    )
