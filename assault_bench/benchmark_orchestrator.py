from __future__ import annotations

from pathlib import Path
from typing import Dict

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.muzero.adapter_voec import MuZeroVOECAdapter
from agents.muzero.configs.config_loader import load_muzero_config
from agents.muzero.core.network import MuZeroNetwork
from assault_bench.bench_io import (
    mlflow_log_metrics,
    persist_bench_artifacts,
    publish_eval_catalog,
    start_mlflow_run,
)
from assault_bench.benchmark_aggregation import accumulate_seed_episode
from assault_bench.benchmark_bootstrap import bootstrap_checkpoint_runtime
from assault_bench.benchmark_finalize import (
    build_benchmark_payload,
    build_phase29_mlflow_metrics,
    resolve_run_id_from_checkpoint,
)
from assault_bench.benchmark_matchup_setup import prepare_matchup_matrix
from assault_bench.benchmark_matchups import build_profile_defs, select_matchup_specs
from assault_bench.benchmark_matrix_runner import execute_benchmark_matrix
from assault_bench.benchmark_publish_pipeline import (
    ensure_benchmark_results_non_empty,
    publish_benchmark_outputs,
)
from assault_bench.benchmark_runtime_utils import (
    engine_kind_from_checkpoint_path,
    resolve_bench_device_choice,
    resolve_checkpoint_path,
    resolve_enabled_profiles,
    resolve_repo_root_from,
)
from assault_bench.benchmark_seed_payload import build_seed_task_payload
from assault_bench.benchmark_serialization import json_dumps
from assault_bench.configs.config_loader import load_benchmark_config
from assault_bench.decision_metrics import build_eval_decision_summary
from assault_bench.episode_runner import (
    benchmark_seed_task,
    benchmark_seed_task_batch,
    run_episode_with_policy,
)
from assault_bench.model_state_utils import load_state_dict
from assault_bench.outcome_metrics import (
    compute_seed_side_outcome_metrics,
    normalize_outcome_score,
    outcome_bucket_from_class,
    outcome_bucket_from_score,
)
from assault_bench.phase29_contract import (
    build_eval_diagnostics_summary,
    build_head_diagnostics_eval,
    build_phase29_promotion_gate,
    build_phase29_train_eval,
    load_train_summary_from_checkpoint,
)
from assault_bench.phase29_metrics import aggregate_muzero_eval_kpis
from mlops.catalog_publisher_v2 import publish_eval_run
from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator

SCHEMA_VERSION_V2 = "reporting_v2_strict"


def _run_benchmark_impl(
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    checkpoint_path: str = "",
    muzero_config_path: str = "",
    mlflow_experiment: str = "assault_bench",
    mlflow_run_name: str = "",
    device: str = "",
) -> Dict:
    config_path_abs = Path(config_path).resolve()
    repo_root = resolve_repo_root_from(config_path_abs)
    cfg = load_benchmark_config(config_path_abs)
    voec_cfg = load_voec_config(Path(cfg.paths["voec_config"]))
    scenario_id = str(cfg.benchmark["scenario_id"])
    scenario_ids_raw = list(cfg.benchmark.get("scenario_ids", []) or [])
    scenario_ids = [str(x or "").strip() for x in scenario_ids_raw if str(x or "").strip()]
    if not scenario_ids:
        scenario_ids = [str(scenario_id)]
    if str(scenario_id) not in scenario_ids:
        scenario_ids = [str(scenario_id)] + list(scenario_ids)
    scenario_weights_raw = list(cfg.benchmark.get("scenario_weights", []) or [])
    scenario_weights = [1.0 for _ in scenario_ids]
    if len(scenario_weights_raw) == len(scenario_ids):
        parsed = []
        for w in scenario_weights_raw:
            try:
                parsed.append(max(0.0, float(w)))
            except Exception:
                parsed.append(0.0)
        if sum(parsed) > 0.0:
            scenario_weights = parsed
    seeds = list(cfg.benchmark["seeds"])
    max_steps = int(cfg.benchmark["max_steps"])
    max_steps_override = int(cfg.benchmark.get("max_steps_override", 0))
    mcts_simulations = int(cfg.benchmark["mcts_simulations"])
    mcts_c_puct = float(cfg.benchmark["mcts_c_puct"])
    mcts_temperature = float(cfg.benchmark.get("mcts_temperature", 1.0))
    trace_detail_level = str(cfg.benchmark.get("trace_detail_level", "core") or "core").strip().lower()
    if trace_detail_level not in {"core", "full"}:
        trace_detail_level = "core"
    mcts_dirichlet_alpha = float(cfg.benchmark.get("mcts_dirichlet_alpha", 0.3))
    mcts_dirichlet_epsilon = float(cfg.benchmark.get("mcts_dirichlet_epsilon", 0.0))
    mcts_q_clip_abs = float(cfg.benchmark.get("mcts_q_clip_abs", 10.0))
    mcts_q_root_normalization_mode = str(cfg.benchmark.get("mcts_q_root_normalization_mode", "adaptive_minmax"))
    mcts_q_root_normalization_strength = float(cfg.benchmark.get("mcts_q_root_normalization_strength", 0.35))
    mcts_value_rescale_mode = str(cfg.benchmark.get("mcts_value_rescale_mode", "tanh"))
    mcts_value_rescale_temperature = float(cfg.benchmark.get("mcts_value_rescale_temperature", 10.0))
    mcts_success_prob_enabled = bool(cfg.benchmark.get("mcts_success_prob_enabled", False))
    mcts_success_prob_alpha = float(cfg.benchmark.get("mcts_success_prob_alpha", 0.0))
    mcts_success_prob_center = float(cfg.benchmark.get("mcts_success_prob_center", 0.5))
    mcts_success_prob_scale = float(cfg.benchmark.get("mcts_success_prob_scale", 0.5))
    mcts_success_prob_centered_clip_abs = float(cfg.benchmark.get("mcts_success_prob_centered_clip_abs", 1.0))
    mcts_min_root_visits_per_action = int(cfg.benchmark.get("mcts_min_root_visits_per_action", 0) or 0)
    mcts_min_root_visits_top_n = int(cfg.benchmark.get("mcts_min_root_visits_top_n", 0) or 0)
    unit_prefilter_enabled = bool(cfg.benchmark.get("unit_prefilter_enabled", False))
    unit_prefilter_replan_enabled = bool(cfg.benchmark.get("unit_prefilter_replan_enabled", False))
    unit_prefilter_top_k = int(cfg.benchmark.get("unit_prefilter_top_k", 1) or 1)
    unit_prefilter_vp_progress_weight = float(cfg.benchmark.get("unit_prefilter_vp_progress_weight", 1.0))
    unit_prefilter_capture_opportunity_weight = float(cfg.benchmark.get("unit_prefilter_capture_opportunity_weight", 2.0))
    unit_prefilter_threat_weight = float(cfg.benchmark.get("unit_prefilter_threat_weight", 0.25))
    num_workers = int(cfg.benchmark.get("num_workers", 1))
    cuda_parallel_use_threads = bool(cfg.benchmark.get("cuda_parallel_use_threads", True))
    inference_max_batch_size = int(cfg.benchmark.get("inference_max_batch_size", 16) or 16)
    inference_batch_wait_ms = float(cfg.benchmark.get("inference_batch_wait_ms", 2.0) or 2.0)
    seed_batch_size = int(cfg.benchmark.get("seed_batch_size", 1) or 1)
    mcts_sims_by_profile = dict(cfg.benchmark.get("mcts_simulations_by_profile", {}) or {})
    persist_replay_episode_files = bool(cfg.benchmark.get("persist_replay_episode_files", True))
    allow_cuda_parallel = bool(cfg.benchmark.get("allow_cuda_parallel", False))
    cuda_parallel_workers = int(cfg.benchmark.get("cuda_parallel_workers", 1) or 1)
    bench_device_cfg = str(cfg.benchmark.get("device", "cuda"))
    bench_device = resolve_bench_device_choice(bench_device_cfg, device)
    if bench_device == "cuda" and num_workers > 1:
        if allow_cuda_parallel:
            effective_limit = max(1, int(cuda_parallel_workers))
            eff_workers = max(1, min(int(num_workers), int(effective_limit)))
            print(
                "[Bench] CUDA parallel enabled by config "
                f"(requested_workers={num_workers}, limit={effective_limit}, effective_workers={eff_workers}).",
                flush=True,
            )
            num_workers = eff_workers
        else:
            print(
                f"[Bench] CUDA eval with num_workers={num_workers} can oversubscribe GPU. Forcing workers=1. "
                "Set benchmark.allow_cuda_parallel=true to opt in.",
                flush=True,
            )
            num_workers = 1

    run_root_cfg = Path(str(cfg.paths["run_root"]))
    run_root = run_root_cfg if run_root_cfg.is_absolute() else (repo_root / run_root_cfg).resolve()
    checkpoint_path = resolve_checkpoint_path(checkpoint_path=checkpoint_path, run_root=run_root)
    model_kind_hint = engine_kind_from_checkpoint_path(checkpoint_path=checkpoint_path)
    if muzero_config_path:
        cfg_muzero_path = str(muzero_config_path)
    elif model_kind_hint == "efficientzero_v2":
        cfg_muzero_path = "agents/efficientzero_v2/configs/efficientzero_v2_config.yaml"
    else:
        cfg_muzero_path = str(cfg.paths.get("muzero_config", "agents/muzero/configs/muzero_config.yaml"))

    mlflow_mod, _mlflow_ctx = start_mlflow_run(
        experiment_name=str(mlflow_experiment),
        run_name=(str(mlflow_run_name).strip() or f"bench_{scenario_id}"),
    )
    runtime_boot = bootstrap_checkpoint_runtime(
        cfg_benchmark=dict(cfg.benchmark or {}),
        checkpoint_path=str(checkpoint_path or ""),
        cfg_muzero_path=str(cfg_muzero_path),
        model_kind_hint=str(model_kind_hint),
        bench_device=str(bench_device),
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
        mcts_dirichlet_alpha=float(mcts_dirichlet_alpha),
        mcts_dirichlet_epsilon=float(mcts_dirichlet_epsilon),
        mcts_min_root_visits_per_action=int(mcts_min_root_visits_per_action),
        mcts_min_root_visits_top_n=int(mcts_min_root_visits_top_n),
        unit_prefilter_enabled=bool(unit_prefilter_enabled),
        unit_prefilter_replan_enabled=bool(unit_prefilter_replan_enabled),
        unit_prefilter_top_k=int(unit_prefilter_top_k),
        unit_prefilter_vp_progress_weight=float(unit_prefilter_vp_progress_weight),
        unit_prefilter_capture_opportunity_weight=float(unit_prefilter_capture_opportunity_weight),
        unit_prefilter_threat_weight=float(unit_prefilter_threat_weight),
        load_muzero_config_fn=load_muzero_config,
        load_state_dict_fn=load_state_dict,
        muzero_network_cls=MuZeroNetwork,
        efficientzero_v2_network_cls=EfficientZeroV2Network,
    )
    model = runtime_boot["model"]
    model_kind = str(runtime_boot["model_kind"])
    muz_cfg = runtime_boot["muz_cfg"]
    ckpt = runtime_boot["ckpt"]
    action_dim = int(runtime_boot["action_dim"])
    mcts_unroll_steps = int(runtime_boot["mcts_unroll_steps"])
    mcts_discount = float(runtime_boot["mcts_discount"])
    reward_shaping_cfg = dict(runtime_boot["reward_shaping_cfg"] or {})

    sim = VOECSimulator(assets=voec_cfg.assets)
    adapter = MuZeroVOECAdapter(sim)
    matchup_setup = prepare_matchup_matrix(
        adapter=adapter,
        scenario_id=str(scenario_ids[0]),
        seeds=list(seeds or []),
        benchmark_cfg=dict(cfg.benchmark or {}),
        resolve_enabled_profiles_fn=resolve_enabled_profiles,
        build_profile_defs_fn=build_profile_defs,
        select_matchup_specs_fn=select_matchup_specs,
    )
    sides = list(matchup_setup.get("sides", []) or [])
    profile_defs = list(matchup_setup.get("profile_defs", []) or [])
    enabled_profiles = set(matchup_setup.get("enabled_profiles", set()) or set())
    matchup_specs = list(matchup_setup.get("matchup_specs", []) or [])
    for spec in matchup_specs:
        profile_name = str(dict(spec or {}).get("profile", "")).strip().lower()
        if profile_name and profile_name in mcts_sims_by_profile:
            try:
                spec["mcts_simulations_override"] = int(mcts_sims_by_profile[profile_name])
            except Exception:
                pass

    results, bench_replay_episodes = execute_benchmark_matrix(
        matchup_specs=matchup_specs,
        seeds=seeds,
        sides=sides,
        num_workers=num_workers,
        scenario_id=str(scenario_id),
        scenario_ids=list(scenario_ids),
        scenario_weights=list(scenario_weights),
        policy_seed_task_builder_fn=lambda **kwargs: build_seed_task_payload(voec_cfg=voec_cfg, **kwargs),
        benchmark_seed_task_fn=benchmark_seed_task,
        benchmark_seed_task_batch_fn=benchmark_seed_task_batch,
        run_episode_with_policy_fn=lambda **kwargs: run_episode_with_policy(adapter=adapter, **kwargs),
        accumulate_seed_episode_fn=accumulate_seed_episode,
        build_eval_decision_summary_fn=build_eval_decision_summary,
        normalize_outcome_score_fn=normalize_outcome_score,
        compute_seed_side_outcome_metrics_fn=compute_seed_side_outcome_metrics,
        outcome_bucket_from_score_fn=outcome_bucket_from_score,
        outcome_bucket_from_class_fn=outcome_bucket_from_class,
        max_steps=max_steps,
        max_steps_override=max_steps_override,
        mcts_simulations=mcts_simulations,
        mcts_c_puct=mcts_c_puct,
        mcts_temperature=mcts_temperature,
        mcts_dirichlet_alpha=mcts_dirichlet_alpha,
        mcts_dirichlet_epsilon=mcts_dirichlet_epsilon,
        mcts_q_clip_abs=float(runtime_boot["mcts_q_clip_abs"]),
        mcts_q_root_normalization_mode=str(runtime_boot["mcts_q_root_normalization_mode"]),
        mcts_q_root_normalization_strength=float(runtime_boot["mcts_q_root_normalization_strength"]),
        mcts_value_rescale_mode=str(runtime_boot["mcts_value_rescale_mode"]),
        mcts_value_rescale_temperature=float(runtime_boot["mcts_value_rescale_temperature"]),
        mcts_success_prob_enabled=bool(runtime_boot["mcts_success_prob_enabled"]),
        mcts_success_prob_alpha=float(runtime_boot["mcts_success_prob_alpha"]),
        mcts_success_prob_center=float(runtime_boot["mcts_success_prob_center"]),
        mcts_success_prob_scale=float(runtime_boot["mcts_success_prob_scale"]),
        mcts_success_prob_centered_clip_abs=float(runtime_boot["mcts_success_prob_centered_clip_abs"]),
        mcts_min_root_visits_per_action=int(runtime_boot["mcts_min_root_visits_per_action"]),
        mcts_min_root_visits_top_n=int(runtime_boot["mcts_min_root_visits_top_n"]),
        checkpoint_path=str(checkpoint_path or ""),
        ckpt=ckpt,
        action_dim=action_dim,
        mcts_unroll_steps=mcts_unroll_steps,
        mcts_discount=mcts_discount,
        reward_shaping_cfg=dict(reward_shaping_cfg or {}),
        bench_device=str(bench_device),
        model_kind=str(model_kind),
        muz_cfg=muz_cfg,
        model=model,
        trace_detail_level=str(trace_detail_level),
        cuda_parallel_use_threads=bool(cuda_parallel_use_threads),
        inference_max_batch_size=int(inference_max_batch_size),
        inference_batch_wait_ms=float(inference_batch_wait_ms),
        seed_batch_size=int(max(1, seed_batch_size)),
    )
    ensure_benchmark_results_non_empty(
        results=list(results or []),
        profile_defs=list(profile_defs or []),
        matchup_specs=list(matchup_specs or []),
        enabled_profiles=enabled_profiles,
        scenario_id=("multi:" + "|".join(list(scenario_ids))) if len(scenario_ids) > 1 else str(scenario_id),
        seeds=list(seeds or []),
    )
    return publish_benchmark_outputs(
        schema_version=SCHEMA_VERSION_V2,
        scenario_id=("multi:" + "|".join(list(scenario_ids))) if len(scenario_ids) > 1 else str(scenario_id),
        checkpoint_path=str(checkpoint_path or ""),
        results=list(results or []),
        run_root=run_root,
        repo_root=repo_root,
        bench_replay_episodes=list(bench_replay_episodes or []),
        resolve_run_id_from_checkpoint_fn=resolve_run_id_from_checkpoint,
        build_benchmark_payload_fn=build_benchmark_payload,
        persist_bench_artifacts_fn=persist_bench_artifacts,
        publish_eval_catalog_fn=publish_eval_catalog,
        publish_eval_run_fn=publish_eval_run,
        aggregate_muzero_eval_kpis_fn=aggregate_muzero_eval_kpis,
        build_phase29_train_eval_fn=build_phase29_train_eval,
        build_phase29_promotion_gate_fn=build_phase29_promotion_gate,
        build_eval_diagnostics_summary_fn=build_eval_diagnostics_summary,
        build_head_diagnostics_eval_fn=build_head_diagnostics_eval,
        load_train_summary_fn=load_train_summary_from_checkpoint,
        json_dumps_fn=json_dumps,
        mlflow_mod=mlflow_mod,
        mlflow_log_metrics_fn=mlflow_log_metrics,
        build_phase29_mlflow_metrics_fn=build_phase29_mlflow_metrics,
        persist_replay_episode_files=bool(persist_replay_episode_files),
    )


def run_benchmark(
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    checkpoint_path: str = "",
    muzero_config_path: str = "",
    mlflow_experiment: str = "assault_bench",
    mlflow_run_name: str = "",
    device: str = "",
):
    return _run_benchmark_impl(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        muzero_config_path=muzero_config_path,
        mlflow_experiment=mlflow_experiment,
        mlflow_run_name=mlflow_run_name,
        device=device,
    )
