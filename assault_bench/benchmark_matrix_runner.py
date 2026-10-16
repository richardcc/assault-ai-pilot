from __future__ import annotations

import random
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.efficientzero_v2.core.inference_service import InferenceService
from assault_bench.benchmark_result_builder import build_benchmark_result
from assault_bench.benchmark_types import BenchmarkResult
from assault_bench.trace_metrics_utils import (
    build_eval_decision_steps_top as _tm_build_eval_decision_steps_top,
)


def execute_benchmark_matrix(
    *,
    matchup_specs: List[Dict[str, object]],
    seeds: List[int],
    sides: List[str],
    num_workers: int,
    scenario_id: str,
    scenario_ids: List[str] | None = None,
    scenario_weights: List[float] | None = None,
    policy_seed_task_builder_fn: Callable[..., Dict[str, object]],
    benchmark_seed_task_fn: Callable[[dict], Tuple],
    benchmark_seed_task_batch_fn: Callable[[list[dict]], list[Tuple]] | None,
    run_episode_with_policy_fn: Callable[..., Tuple],
    accumulate_seed_episode_fn: Callable[..., Tuple[str, str]],
    build_eval_decision_summary_fn: Callable[[List[Dict[str, object]]], Tuple[Dict[str, object], List[Dict[str, object]]]],
    normalize_outcome_score_fn: Callable[[object], Optional[int]],
    compute_seed_side_outcome_metrics_fn: Callable[[List[Dict[str, object]]], Dict[str, Dict[str, float]]],
    outcome_bucket_from_score_fn: Callable[[Optional[int]], str],
    outcome_bucket_from_class_fn: Callable[[str], str],
    max_steps: int,
    max_steps_override: int,
    mcts_simulations: int,
    mcts_c_puct: float,
    mcts_temperature: float,
    mcts_dirichlet_alpha: float,
    mcts_dirichlet_epsilon: float,
    mcts_q_clip_abs: float,
    mcts_q_root_normalization_mode: str,
    mcts_q_root_normalization_strength: float,
    mcts_value_rescale_mode: str,
    mcts_value_rescale_temperature: float,
    mcts_success_prob_enabled: bool,
    mcts_success_prob_alpha: float,
    mcts_success_prob_center: float,
    mcts_success_prob_scale: float,
    mcts_success_prob_centered_clip_abs: float,
    mcts_min_root_visits_per_action: int,
    mcts_min_root_visits_top_n: int,
    checkpoint_path: str,
    ckpt,
    action_dim: int,
    mcts_unroll_steps: int,
    mcts_discount: float,
    reward_shaping_cfg: Dict[str, object],
    bench_device: str,
    model_kind: str,
    muz_cfg,
    model,
    trace_detail_level: str = "core",
    cuda_parallel_use_threads: bool = True,
    inference_max_batch_size: int = 16,
    inference_batch_wait_ms: float = 2.0,
    seed_batch_size: int = 1,
) -> tuple[List[BenchmarkResult], List[Dict[str, object]]]:
    def _as_dict(x):
        return x if isinstance(x, dict) else dict(x or {})

    def _as_list(x):
        return x if isinstance(x, list) else list(x or [])

    results: List[BenchmarkResult] = []
    bench_replay_episodes: List[Dict[str, object]] = []
    mix_ids = [str(x or "").strip() for x in list(scenario_ids or [scenario_id]) if str(x or "").strip()]
    if not mix_ids:
        mix_ids = [str(scenario_id)]
    mix_weights = [1.0 for _ in mix_ids]
    if len(list(scenario_weights or [])) == len(mix_ids):
        parsed_weights: list[float] = []
        for w in list(scenario_weights or []):
            try:
                parsed_weights.append(max(0.0, float(w)))
            except Exception:
                parsed_weights.append(0.0)
        if sum(parsed_weights) > 0.0:
            mix_weights = parsed_weights
    mix_cumulative: list[float] = []
    mix_total_w = 0.0
    for w in mix_weights:
        mix_total_w += float(max(0.0, float(w)))
        mix_cumulative.append(mix_total_w)

    def _scenario_for_seed(seed_value: int) -> str:
        if len(mix_ids) <= 1:
            return str(mix_ids[0])
        if mix_total_w <= 0.0:
            return str(mix_ids[0])
        # Deterministic weighted sampling per seed without bias from seed range.
        rng = random.Random(int(seed_value))
        ticket = float(rng.random()) * float(mix_total_w)
        for sid, acc in zip(mix_ids, mix_cumulative):
            if ticket < acc:
                return str(sid)
        return str(mix_ids[-1])

    def _build_result_from_episode_records(
        *,
        records: List[Dict[str, Any]],
        profile: str,
        agent_name: str,
        group: str,
        goal: str,
        policy: str,
        policy_by_side: Dict[str, str],
        collect_flow_metrics: bool,
    ) -> BenchmarkResult:
        returns: List[float] = []
        steps: List[int] = []
        terminals: List[bool] = []
        timeouts: List[bool] = []
        wins: List[bool] = []
        terminal_reason_counts: Dict[str, int] = {}
        vp_initial_counts_by_side: Dict[str, Dict[int, int]] = {}
        vp_final_counts_by_side: Dict[str, Dict[int, int]] = {}
        vp_initial_sum_by_side: Dict[str, float] = {}
        vp_final_sum_by_side: Dict[str, float] = {}
        vp_gained_sum_by_side: Dict[str, float] = {}
        vp_lost_sum_by_side: Dict[str, float] = {}
        winner_side_counts: Dict[str, int] = {}
        tracked_side = ""
        tracked_metric = ""
        tracked_captured_values: List[int] = []
        scenario_outcome_counts: Dict[str, int] = {}
        scenario_outcome_class_counts: Dict[str, int] = {}
        scenario_outcome_class_counts_by_side: Dict[str, Dict[str, int]] = {}
        tracked_outcome_bucket_counts: Dict[str, int] = {}
        opponent_outcome_bucket_counts: Dict[str, int] = {}
        phase29_seed_rows: List[Dict[str, float]] = []
        phase29_seed_rows_by_side: List[Dict[str, Dict[str, float]]] = []
        decision_trace_rows_all: List[Dict[str, object]] = []
        seed_games_rows: List[Dict[str, object]] = []
        episode_wall_s_values: List[float] = []
        replay_rows_local: List[Dict[str, object]] = []
        seeds_local: List[int] = []
        for idx, rec in enumerate(list(records or [])):
            episode_elapsed_s = rec.get("episode_elapsed_s", None)
            if isinstance(episode_elapsed_s, (int, float)):
                episode_wall_s_values.append(float(episode_elapsed_s))
            tracked_side, tracked_metric = accumulate_seed_episode_fn(
                seed_used=int(rec.get("seed_used", 0) or 0),
                scenario_id=str(rec.get("scenario_id", "") or ""),
                ret=float(rec.get("ret", 0.0) or 0.0),
                step_count=int(rec.get("step_count", 0) or 0),
                terminal=bool(rec.get("terminal", False)),
                timeout=bool(rec.get("timeout", False)),
                win=bool(rec.get("win", False)),
                winner_side=str(rec.get("winner_side", "") or ""),
                scenario_outcome=_as_dict(rec.get("scenario_outcome", {})),
                phase29_summary=_as_dict(rec.get("phase29_summary", {})),
                trace_rows=_as_list(rec.get("trace_rows", [])),
                agent_name=str(agent_name),
                episode_index=int(idx),
                collect_flow_metrics=bool(collect_flow_metrics),
                returns=returns,
                steps=steps,
                terminals=terminals,
                timeouts=timeouts,
                wins=wins,
                vp_initial_counts_by_side=vp_initial_counts_by_side,
                vp_initial_sum_by_side=vp_initial_sum_by_side,
                vp_final_counts_by_side=vp_final_counts_by_side,
                vp_final_sum_by_side=vp_final_sum_by_side,
                vp_gained_sum_by_side=vp_gained_sum_by_side,
                vp_lost_sum_by_side=vp_lost_sum_by_side,
                winner_side_counts=winner_side_counts,
                tracked_side=str(tracked_side or ""),
                tracked_metric=str(tracked_metric or ""),
                tracked_captured_values=tracked_captured_values,
                scenario_outcome_counts=scenario_outcome_counts,
                scenario_outcome_class_counts=scenario_outcome_class_counts,
                scenario_outcome_class_counts_by_side=scenario_outcome_class_counts_by_side,
                seed_games_rows=seed_games_rows,
                tracked_outcome_bucket_counts=tracked_outcome_bucket_counts,
                opponent_outcome_bucket_counts=opponent_outcome_bucket_counts,
                phase29_seed_rows=phase29_seed_rows,
                phase29_seed_rows_by_side=phase29_seed_rows_by_side,
                decision_trace_rows_all=decision_trace_rows_all,
                bench_replay_episodes=replay_rows_local,
                terminal_reason_counts=terminal_reason_counts,
                terminal_reason=str(rec.get("terminal_reason", "") or ""),
                initial_vp_by_side=_as_dict(rec.get("initial_vp_by_side", {})),
                final_vp_by_side=_as_dict(rec.get("final_vp_by_side", {})),
                episode_elapsed_s=(
                    float(episode_elapsed_s) if isinstance(episode_elapsed_s, (int, float)) else None
                ),
                episode_timing_meta=_as_dict(rec.get("episode_timing_meta", {})),
                normalize_outcome_score_fn=normalize_outcome_score_fn,
                compute_seed_side_outcome_metrics_fn=compute_seed_side_outcome_metrics_fn,
                outcome_bucket_from_score_fn=outcome_bucket_from_score_fn,
                outcome_bucket_from_class_fn=outcome_bucket_from_class_fn,
            )
            seeds_local.append(int(rec.get("seed_used", 0) or 0))
        eval_decision_summary, eval_decisions_top = build_eval_decision_summary_fn(
            trace_rows=decision_trace_rows_all
        )
        eval_decision_steps_top = _tm_build_eval_decision_steps_top(
            trace_rows=decision_trace_rows_all,
            limit=40,
        )
        profile_wall_s = float(sum(episode_wall_s_values)) if episode_wall_s_values else 0.0
        return build_benchmark_result(
            agent_name=agent_name,
            profile=profile,
            group=group,
            goal=goal,
            policy=policy,
            policy_by_side=policy_by_side,
            seeds=seeds_local,
            returns=returns,
            steps=steps,
            terminals=terminals,
            timeouts=timeouts,
            wins=wins,
            terminal_reason_counts=terminal_reason_counts,
            vp_initial_sum_by_side=vp_initial_sum_by_side,
            vp_final_sum_by_side=vp_final_sum_by_side,
            vp_initial_counts_by_side=vp_initial_counts_by_side,
            vp_final_counts_by_side=vp_final_counts_by_side,
            vp_gained_sum_by_side=vp_gained_sum_by_side,
            vp_lost_sum_by_side=vp_lost_sum_by_side,
            winner_side_counts=winner_side_counts,
            tracked_side=tracked_side,
            tracked_metric=tracked_metric,
            tracked_captured_values=tracked_captured_values,
            scenario_outcome_counts=scenario_outcome_counts,
            scenario_outcome_class_counts=scenario_outcome_class_counts,
            scenario_outcome_class_counts_by_side=scenario_outcome_class_counts_by_side,
            tracked_outcome_bucket_counts=tracked_outcome_bucket_counts,
            opponent_outcome_bucket_counts=opponent_outcome_bucket_counts,
            phase29_seed_rows=phase29_seed_rows,
            phase29_seed_rows_by_side=phase29_seed_rows_by_side,
            eval_decision_summary=eval_decision_summary,
            eval_decisions_top=eval_decisions_top,
            eval_decision_steps_top=eval_decision_steps_top,
            seed_games_rows=seed_games_rows,
            episode_wall_s_values=episode_wall_s_values,
            profile_wall_s=profile_wall_s,
        )

    for spec in matchup_specs:
        profile = str(spec["profile"])
        agent_name = str(spec["agent_name"])
        policy = str(spec["policy"])
        policy_by_side = dict(spec.get("policy_by_side", {}) or {})
        if not policy_by_side and sides:
            policy_by_side = {str(side): str(policy) for side in sides}
        group = str(spec.get("group", ""))
        goal = str(spec.get("goal", ""))
        collect_flow_metrics = bool("muzero" in agent_name.lower())
        mcts_simulations_eff = int(spec.get("mcts_simulations_override", mcts_simulations) or mcts_simulations)
        print(
            f"[Bench] profile={profile} agent={agent_name} policy={policy} "
            f"policy_by_side={policy_by_side if policy_by_side else '{}'} start",
            flush=True,
        )
        returns = []
        steps = []
        terminals = []
        timeouts = []
        wins = []
        terminal_reason_counts: Dict[str, int] = {}
        vp_initial_counts_by_side: Dict[str, Dict[int, int]] = {}
        vp_final_counts_by_side: Dict[str, Dict[int, int]] = {}
        vp_initial_sum_by_side: Dict[str, float] = {}
        vp_final_sum_by_side: Dict[str, float] = {}
        vp_gained_sum_by_side: Dict[str, float] = {}
        vp_lost_sum_by_side: Dict[str, float] = {}
        winner_side_counts: Dict[str, int] = {}
        tracked_side = ""
        tracked_metric = ""
        tracked_captured_values: List[int] = []
        scenario_outcome_counts: Dict[str, int] = {}
        scenario_outcome_class_counts: Dict[str, int] = {}
        scenario_outcome_class_counts_by_side: Dict[str, Dict[str, int]] = {}
        tracked_outcome_bucket_counts: Dict[str, int] = {}
        opponent_outcome_bucket_counts: Dict[str, int] = {}
        phase29_seed_rows: List[Dict[str, float]] = []
        phase29_seed_rows_by_side: List[Dict[str, Dict[str, float]]] = []
        decision_trace_rows_all: List[Dict[str, object]] = []
        seed_games_rows: List[Dict[str, object]] = []
        episode_wall_s_values: List[float] = []
        episode_records: List[Dict[str, Any]] = []
        profile_started = time.perf_counter()

        use_cuda_thread_parallel = bool(
            int(num_workers) > 1
            and str(bench_device) == "cuda"
            and bool(cuda_parallel_use_threads)
            and model is not None
        )
        if num_workers > 1:
            payloads = [
                policy_seed_task_builder_fn(
                    scenario_id=_scenario_for_seed(int(s)),
                    seed=s,
                    policy=policy,
                    policy_by_side=dict(policy_by_side),
                    max_steps=max_steps,
                    max_steps_override=max_steps_override,
                    mcts_simulations=mcts_simulations_eff,
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
                    checkpoint_path=checkpoint_path,
                    ckpt=ckpt,
                    action_dim=action_dim,
                    mcts_unroll_steps=mcts_unroll_steps,
                    mcts_discount=mcts_discount,
                    reward_shaping_cfg=dict(reward_shaping_cfg or {}),
                    collect_flow_metrics=collect_flow_metrics,
                    bench_device=bench_device,
                    model_kind=model_kind,
                    muz_cfg=muz_cfg,
                    trace_detail_level=str(trace_detail_level or "core"),
                )
                for s in seeds
            ]
            if use_cuda_thread_parallel:
                inference_service = None
                try:
                    shared_proxy = None
                    if str(policy).strip().lower() != "random":
                        inference_service = InferenceService(
                            model=model,
                            device="cuda",
                            max_batch_size=int(max(1, inference_max_batch_size)),
                            batch_wait_ms=float(max(0.0, inference_batch_wait_ms)),
                        )
                        inference_service.start()
                        shared_proxy = inference_service.create_proxy()
                    for p in payloads:
                        if shared_proxy is not None:
                            p["shared_model_proxy"] = shared_proxy
                            p["checkpoint_path"] = ""
                    print(
                        "[Bench] CUDA thread-parallel enabled "
                        f"(workers={num_workers}, inference_batch={int(max(1, inference_max_batch_size))}, "
                        f"wait_ms={float(max(0.0, inference_batch_wait_ms)):.2f})",
                        flush=True,
                    )
                    with ThreadPoolExecutor(max_workers=num_workers) as ex:
                        futures = [ex.submit(benchmark_seed_task_fn, p) for p in payloads]
                        for fut in as_completed(futures):
                            result_payload = fut.result()
                            episode_elapsed_s = None
                            episode_timing_meta = None
                            if isinstance(result_payload, tuple):
                                values = list(result_payload)
                            elif isinstance(result_payload, list):
                                values = list(result_payload)
                            else:
                                values = []
                            if len(values) >= 13:
                                (
                                    seed_used,
                                    ret,
                                    step_count,
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
                                ) = values[:13]
                                if len(values) >= 14 and isinstance(values[13], (int, float)):
                                    episode_elapsed_s = float(values[13])
                                if len(values) >= 15 and isinstance(values[14], dict):
                                    episode_timing_meta = dict(values[14] or {})
                            else:
                                raise RuntimeError("benchmark_seed_task returned malformed payload")
                            if isinstance(episode_elapsed_s, (int, float)):
                                episode_wall_s_values.append(float(episode_elapsed_s))
                            episode_records.append(
                                {
                                    "seed_used": int(seed_used),
                                    "scenario_id": str(_scenario_for_seed(int(seed_used))),
                                    "ret": float(ret),
                                    "step_count": int(step_count),
                                    "terminal": bool(terminal),
                                    "timeout": bool(timeout),
                                    "win": bool(win),
                                    "terminal_reason": str(terminal_reason or ""),
                                    "initial_vp_by_side": _as_dict(initial_vp_by_side),
                                    "final_vp_by_side": _as_dict(final_vp_by_side),
                                    "winner_side": str(winner_side or ""),
                                    "scenario_outcome": _as_dict(scenario_outcome),
                                    "phase29_summary": _as_dict(phase29_summary),
                                    "trace_rows": _as_list(trace_rows),
                                    "episode_elapsed_s": episode_elapsed_s,
                                    "episode_timing_meta": episode_timing_meta,
                                }
                            )
                            tracked_side, tracked_metric = accumulate_seed_episode_fn(
                                seed_used=int(seed_used),
                                scenario_id=str(_scenario_for_seed(int(seed_used))),
                                ret=float(ret),
                                step_count=int(step_count),
                                terminal=bool(terminal),
                                timeout=bool(timeout),
                                win=bool(win),
                                winner_side=str(winner_side or ""),
                                scenario_outcome=_as_dict(scenario_outcome),
                                phase29_summary=_as_dict(phase29_summary),
                                trace_rows=_as_list(trace_rows),
                                agent_name=str(agent_name),
                                episode_index=int(len(phase29_seed_rows)),
                                collect_flow_metrics=bool(collect_flow_metrics),
                                returns=returns,
                                steps=steps,
                                terminals=terminals,
                                timeouts=timeouts,
                                wins=wins,
                                vp_initial_counts_by_side=vp_initial_counts_by_side,
                                vp_initial_sum_by_side=vp_initial_sum_by_side,
                                vp_final_counts_by_side=vp_final_counts_by_side,
                                vp_final_sum_by_side=vp_final_sum_by_side,
                                vp_gained_sum_by_side=vp_gained_sum_by_side,
                                vp_lost_sum_by_side=vp_lost_sum_by_side,
                                winner_side_counts=winner_side_counts,
                                tracked_side=str(tracked_side or ""),
                                tracked_metric=str(tracked_metric or ""),
                                tracked_captured_values=tracked_captured_values,
                                scenario_outcome_counts=scenario_outcome_counts,
                                scenario_outcome_class_counts=scenario_outcome_class_counts,
                                scenario_outcome_class_counts_by_side=scenario_outcome_class_counts_by_side,
                                seed_games_rows=seed_games_rows,
                                tracked_outcome_bucket_counts=tracked_outcome_bucket_counts,
                                opponent_outcome_bucket_counts=opponent_outcome_bucket_counts,
                                phase29_seed_rows=phase29_seed_rows,
                                phase29_seed_rows_by_side=phase29_seed_rows_by_side,
                                decision_trace_rows_all=decision_trace_rows_all,
                                bench_replay_episodes=bench_replay_episodes,
                                terminal_reason_counts=terminal_reason_counts,
                                terminal_reason=str(terminal_reason),
                                initial_vp_by_side=_as_dict(initial_vp_by_side),
                                final_vp_by_side=_as_dict(final_vp_by_side),
                                episode_elapsed_s=episode_elapsed_s,
                                episode_timing_meta=episode_timing_meta,
                                normalize_outcome_score_fn=normalize_outcome_score_fn,
                                compute_seed_side_outcome_metrics_fn=compute_seed_side_outcome_metrics_fn,
                                outcome_bucket_from_score_fn=outcome_bucket_from_score_fn,
                                outcome_bucket_from_class_fn=outcome_bucket_from_class_fn,
                            )
                            key = terminal_reason or "unknown"
                            print(
                                f"[Bench]   seed_done scenario={_scenario_for_seed(int(seed_used))} return={ret:.3f} "
                                f"steps={step_count} terminal={terminal} timeout={timeout} "
                                f"reason={key} "
                                f"elapsed_s={float(episode_elapsed_s or 0.0):.2f}",
                                flush=True,
                            )
                finally:
                    if inference_service is not None:
                        try:
                            metrics = dict(inference_service.metrics_snapshot() or {})
                            print(
                                "[Bench] inference_service "
                                f"req={int(metrics.get('inference_requests_total', 0.0))} "
                                f"batches={int(metrics.get('inference_batches_total', 0.0))} "
                                f"batch_mean={float(metrics.get('inference_batch_size_mean', 0.0)):.2f} "
                                f"queue_p95_ms={float(metrics.get('inference_queue_wait_p95_ms', 0.0)):.2f} "
                                f"lat_p95_ms={float(metrics.get('inference_latency_p95_ms', 0.0)):.2f}",
                                flush=True,
                            )
                        except Exception:
                            pass
                        inference_service.stop()
            else:
                with ProcessPoolExecutor(max_workers=num_workers) as ex:
                    sb = max(1, int(seed_batch_size or 1))
                    if sb > 1 and benchmark_seed_task_batch_fn is not None:
                        chunks: list[list[dict]] = [
                            payloads[i:i + sb] for i in range(0, len(payloads), sb)
                        ]
                        futures = [ex.submit(benchmark_seed_task_batch_fn, c) for c in chunks]
                    else:
                        futures = [ex.submit(benchmark_seed_task_fn, p) for p in payloads]
                    for fut in as_completed(futures):
                        raw = fut.result()
                        result_rows = raw if isinstance(raw, list) and raw and isinstance(raw[0], (tuple, list)) else [raw]
                        for result_payload in result_rows:
                            episode_elapsed_s = None
                            episode_timing_meta = None
                            if isinstance(result_payload, tuple):
                                values = list(result_payload)
                            elif isinstance(result_payload, list):
                                values = list(result_payload)
                            else:
                                values = []
                            if len(values) >= 13:
                                (
                                    seed_used,
                                    ret,
                                    step_count,
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
                                ) = values[:13]
                                if len(values) >= 14 and isinstance(values[13], (int, float)):
                                    episode_elapsed_s = float(values[13])
                                if len(values) >= 15 and isinstance(values[14], dict):
                                    episode_timing_meta = dict(values[14] or {})
                            else:
                                raise RuntimeError("benchmark_seed_task returned malformed payload")
                            if isinstance(episode_elapsed_s, (int, float)):
                                episode_wall_s_values.append(float(episode_elapsed_s))
                            episode_records.append(
                                {
                                    "seed_used": int(seed_used),
                                    "scenario_id": str(_scenario_for_seed(int(seed_used))),
                                    "ret": float(ret),
                                    "step_count": int(step_count),
                                    "terminal": bool(terminal),
                                    "timeout": bool(timeout),
                                    "win": bool(win),
                                    "terminal_reason": str(terminal_reason or ""),
                                    "initial_vp_by_side": _as_dict(initial_vp_by_side),
                                    "final_vp_by_side": _as_dict(final_vp_by_side),
                                    "winner_side": str(winner_side or ""),
                                    "scenario_outcome": _as_dict(scenario_outcome),
                                    "phase29_summary": _as_dict(phase29_summary),
                                    "trace_rows": _as_list(trace_rows),
                                    "episode_elapsed_s": episode_elapsed_s,
                                    "episode_timing_meta": episode_timing_meta,
                                }
                            )
                            tracked_side, tracked_metric = accumulate_seed_episode_fn(
                                seed_used=int(seed_used),
                                scenario_id=str(_scenario_for_seed(int(seed_used))),
                                ret=float(ret),
                                step_count=int(step_count),
                                terminal=bool(terminal),
                                timeout=bool(timeout),
                                win=bool(win),
                                winner_side=str(winner_side or ""),
                                scenario_outcome=_as_dict(scenario_outcome),
                                phase29_summary=_as_dict(phase29_summary),
                                trace_rows=_as_list(trace_rows),
                                agent_name=str(agent_name),
                                episode_index=int(len(phase29_seed_rows)),
                                collect_flow_metrics=bool(collect_flow_metrics),
                                returns=returns,
                                steps=steps,
                                terminals=terminals,
                                timeouts=timeouts,
                                wins=wins,
                                vp_initial_counts_by_side=vp_initial_counts_by_side,
                                vp_initial_sum_by_side=vp_initial_sum_by_side,
                                vp_final_counts_by_side=vp_final_counts_by_side,
                                vp_final_sum_by_side=vp_final_sum_by_side,
                                vp_gained_sum_by_side=vp_gained_sum_by_side,
                                vp_lost_sum_by_side=vp_lost_sum_by_side,
                                winner_side_counts=winner_side_counts,
                                tracked_side=str(tracked_side or ""),
                                tracked_metric=str(tracked_metric or ""),
                                tracked_captured_values=tracked_captured_values,
                                scenario_outcome_counts=scenario_outcome_counts,
                                scenario_outcome_class_counts=scenario_outcome_class_counts,
                                scenario_outcome_class_counts_by_side=scenario_outcome_class_counts_by_side,
                                seed_games_rows=seed_games_rows,
                                tracked_outcome_bucket_counts=tracked_outcome_bucket_counts,
                                opponent_outcome_bucket_counts=opponent_outcome_bucket_counts,
                                phase29_seed_rows=phase29_seed_rows,
                                phase29_seed_rows_by_side=phase29_seed_rows_by_side,
                                decision_trace_rows_all=decision_trace_rows_all,
                                bench_replay_episodes=bench_replay_episodes,
                                terminal_reason_counts=terminal_reason_counts,
                                terminal_reason=str(terminal_reason),
                                initial_vp_by_side=_as_dict(initial_vp_by_side),
                                final_vp_by_side=_as_dict(final_vp_by_side),
                                episode_elapsed_s=episode_elapsed_s,
                                episode_timing_meta=episode_timing_meta,
                                normalize_outcome_score_fn=normalize_outcome_score_fn,
                                compute_seed_side_outcome_metrics_fn=compute_seed_side_outcome_metrics_fn,
                                outcome_bucket_from_score_fn=outcome_bucket_from_score_fn,
                                outcome_bucket_from_class_fn=outcome_bucket_from_class_fn,
                            )
                            key = terminal_reason or "unknown"
                            print(
                                f"[Bench]   seed_done scenario={_scenario_for_seed(int(seed_used))} return={ret:.3f} "
                                f"steps={step_count} terminal={terminal} timeout={timeout} "
                                f"reason={key} "
                                f"elapsed_s={float(episode_elapsed_s or 0.0):.2f}",
                                flush=True,
                            )
        else:
            for idx, s in enumerate(seeds, start=1):
                seed_scenario_id = _scenario_for_seed(int(s))
                print(
                    f"[Bench]   seed {idx}/{len(seeds)}={s} scenario={seed_scenario_id} start",
                    flush=True,
                )
                seed_started = time.perf_counter()
                (
                    seed_used,
                    ret,
                    step_count,
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
                ) = run_episode_with_policy_fn(
                    scenario_id=seed_scenario_id,
                    seed=s,
                    policy_name=policy,
                    policy_by_side=dict(policy_by_side),
                    max_steps=max_steps,
                    max_steps_override=max_steps_override,
                    mcts_simulations=mcts_simulations_eff,
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
                    model=model if policy != "random" else None,
                    action_dim=action_dim,
                    mcts_unroll_steps=mcts_unroll_steps,
                    mcts_discount=mcts_discount,
                    reward_shaping=dict(reward_shaping_cfg or {}),
                    collect_flow_metrics=collect_flow_metrics,
                    decision_top_k=None,
                    trace_detail_level=str(trace_detail_level or "core"),
                )
                episode_elapsed_s = float(max(0.0, time.perf_counter() - seed_started))
                episode_timing_meta = {
                    "startup_s": 0.0,
                    "model_load_s": 0.0,
                    "episode_s": float(episode_elapsed_s),
                    "total_s": float(episode_elapsed_s),
                }
                episode_wall_s_values.append(float(episode_elapsed_s))
                episode_records.append(
                    {
                        "seed_used": int(seed_used),
                        "scenario_id": str(seed_scenario_id),
                        "ret": float(ret),
                        "step_count": int(step_count),
                        "terminal": bool(terminal),
                        "timeout": bool(timeout),
                        "win": bool(win),
                        "terminal_reason": str(terminal_reason or ""),
                        "initial_vp_by_side": _as_dict(initial_vp_by_side),
                        "final_vp_by_side": _as_dict(final_vp_by_side),
                        "winner_side": str(winner_side or ""),
                        "scenario_outcome": _as_dict(scenario_outcome),
                        "phase29_summary": _as_dict(phase29_summary),
                        "trace_rows": _as_list(trace_rows),
                        "episode_elapsed_s": episode_elapsed_s,
                        "episode_timing_meta": episode_timing_meta,
                    }
                )
                tracked_side, tracked_metric = accumulate_seed_episode_fn(
                    seed_used=int(seed_used),
                    scenario_id=str(seed_scenario_id),
                    ret=float(ret),
                    step_count=int(step_count),
                    terminal=bool(terminal),
                    timeout=bool(timeout),
                    win=bool(win),
                    winner_side=str(winner_side or ""),
                    scenario_outcome=_as_dict(scenario_outcome),
                    phase29_summary=_as_dict(phase29_summary),
                    trace_rows=_as_list(trace_rows),
                    agent_name=str(agent_name),
                    episode_index=int(idx - 1),
                    collect_flow_metrics=bool(collect_flow_metrics),
                    returns=returns,
                    steps=steps,
                    terminals=terminals,
                    timeouts=timeouts,
                    wins=wins,
                    vp_initial_counts_by_side=vp_initial_counts_by_side,
                    vp_initial_sum_by_side=vp_initial_sum_by_side,
                    vp_final_counts_by_side=vp_final_counts_by_side,
                    vp_final_sum_by_side=vp_final_sum_by_side,
                    vp_gained_sum_by_side=vp_gained_sum_by_side,
                    vp_lost_sum_by_side=vp_lost_sum_by_side,
                    winner_side_counts=winner_side_counts,
                    tracked_side=str(tracked_side or ""),
                    tracked_metric=str(tracked_metric or ""),
                    tracked_captured_values=tracked_captured_values,
                    scenario_outcome_counts=scenario_outcome_counts,
                    scenario_outcome_class_counts=scenario_outcome_class_counts,
                    scenario_outcome_class_counts_by_side=scenario_outcome_class_counts_by_side,
                    seed_games_rows=seed_games_rows,
                    tracked_outcome_bucket_counts=tracked_outcome_bucket_counts,
                    opponent_outcome_bucket_counts=opponent_outcome_bucket_counts,
                    phase29_seed_rows=phase29_seed_rows,
                    phase29_seed_rows_by_side=phase29_seed_rows_by_side,
                    decision_trace_rows_all=decision_trace_rows_all,
                    bench_replay_episodes=bench_replay_episodes,
                    terminal_reason_counts=terminal_reason_counts,
                    terminal_reason=str(terminal_reason),
                    initial_vp_by_side=_as_dict(initial_vp_by_side),
                    final_vp_by_side=_as_dict(final_vp_by_side),
                    episode_elapsed_s=episode_elapsed_s,
                    episode_timing_meta=episode_timing_meta,
                    normalize_outcome_score_fn=normalize_outcome_score_fn,
                    compute_seed_side_outcome_metrics_fn=compute_seed_side_outcome_metrics_fn,
                    outcome_bucket_from_score_fn=outcome_bucket_from_score_fn,
                    outcome_bucket_from_class_fn=outcome_bucket_from_class_fn,
                )
                key = terminal_reason or "unknown"
                print(
                    f"[Bench]   seed {idx}/{len(seeds)}={s} "
                    f"scenario={seed_scenario_id} "
                    f"return={ret:.3f} steps={step_count} "
                    f"terminal={terminal} timeout={timeout} reason={key} "
                    f"elapsed_s={float(episode_elapsed_s or 0.0):.2f}",
                    flush=True,
                )
        eval_decision_summary, eval_decisions_top = build_eval_decision_summary_fn(
            trace_rows=decision_trace_rows_all
        )
        eval_decision_steps_top = _tm_build_eval_decision_steps_top(
            trace_rows=decision_trace_rows_all,
            limit=40,
        )
        scenario_keys = sorted(
            {str(r.get("scenario_id", "") or "").strip() for r in list(episode_records or []) if str(r.get("scenario_id", "") or "").strip()}
        )
        if len(scenario_keys) > 1:
            for sid in scenario_keys:
                scenario_records = [
                    r for r in list(episode_records or [])
                    if str(r.get("scenario_id", "") or "").strip() == sid
                ]
                if not scenario_records:
                    continue
                results.append(
                    _build_result_from_episode_records(
                        records=scenario_records,
                        profile=profile,
                        agent_name=agent_name,
                        group=group,
                        goal=goal,
                        policy=policy,
                        policy_by_side=policy_by_side,
                        collect_flow_metrics=collect_flow_metrics,
                    )
                )
        else:
            results.append(
                build_benchmark_result(
                    agent_name=agent_name,
                    profile=profile,
                    group=group,
                    goal=goal,
                    policy=policy,
                    policy_by_side=policy_by_side,
                    seeds=seeds,
                    returns=returns,
                    steps=steps,
                    terminals=terminals,
                    timeouts=timeouts,
                    wins=wins,
                    terminal_reason_counts=terminal_reason_counts,
                    vp_initial_sum_by_side=vp_initial_sum_by_side,
                    vp_final_sum_by_side=vp_final_sum_by_side,
                    vp_initial_counts_by_side=vp_initial_counts_by_side,
                    vp_final_counts_by_side=vp_final_counts_by_side,
                    vp_gained_sum_by_side=vp_gained_sum_by_side,
                    vp_lost_sum_by_side=vp_lost_sum_by_side,
                    winner_side_counts=winner_side_counts,
                    tracked_side=tracked_side,
                    tracked_metric=tracked_metric,
                    tracked_captured_values=tracked_captured_values,
                    scenario_outcome_counts=scenario_outcome_counts,
                    scenario_outcome_class_counts=scenario_outcome_class_counts,
                    scenario_outcome_class_counts_by_side=scenario_outcome_class_counts_by_side,
                    tracked_outcome_bucket_counts=tracked_outcome_bucket_counts,
                    opponent_outcome_bucket_counts=opponent_outcome_bucket_counts,
                    phase29_seed_rows=phase29_seed_rows,
                    phase29_seed_rows_by_side=phase29_seed_rows_by_side,
                    eval_decision_summary=eval_decision_summary,
                    eval_decisions_top=eval_decisions_top,
                    eval_decision_steps_top=eval_decision_steps_top,
                    seed_games_rows=seed_games_rows,
                    episode_wall_s_values=episode_wall_s_values,
                    profile_wall_s=float(max(0.0, time.perf_counter() - profile_started)),
                )
            )
        last = results[-1]
        print(
            f"[Bench] agent={agent_name} done "
            f"avg_return={last.avg_return:.3f} avg_steps={last.avg_steps:.1f} "
            f"terminal_rate={last.terminal_rate:.3f} timeout_rate={last.timeout_rate:.3f} "
            f"win_rate={last.win_rate:.3f} "
            f"profile_wall_s={last.profile_wall_s:.2f} "
            f"episode_p50_s={last.episode_wall_s_p50:.2f} "
            f"episode_p95_s={last.episode_wall_s_p95:.2f} "
            f"eps={last.episodes_per_second:.3f}",
            flush=True,
        )

    return results, bench_replay_episodes

