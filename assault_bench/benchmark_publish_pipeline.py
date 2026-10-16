from __future__ import annotations

from typing import Callable, Dict, List


def ensure_benchmark_results_non_empty(
    *,
    results: List[object],
    profile_defs: List[Dict[str, object]],
    matchup_specs: List[Dict[str, object]],
    enabled_profiles,
    scenario_id: str,
    seeds: List[int],
) -> None:
    if results:
        return
    available_profiles = sorted(
        {
            str(p.get("profile", "")).strip().lower()
            for p in list(profile_defs or [])
            if str(p.get("profile", "")).strip()
        }
    )
    selected_profiles = sorted(
        {
            str(p.get("profile", "")).strip().lower()
            for p in list(matchup_specs or [])
            if str(p.get("profile", "")).strip()
        }
    )
    err = (
        "benchmark produced zero result rows; aborting publish. "
        f"enabled_profiles={sorted(enabled_profiles)} "
        f"selected_profiles={selected_profiles} "
        f"available_profiles={available_profiles} "
        f"scenario_id={str(scenario_id)} seeds={int(len(seeds or []))}"
    )
    print(f"[Bench][ERROR] {err}", flush=True)
    raise RuntimeError(err)


def publish_benchmark_outputs(
    *,
    schema_version: str,
    scenario_id: str,
    checkpoint_path: str,
    results: List[object],
    run_root,
    repo_root,
    bench_replay_episodes: List[Dict[str, object]],
    resolve_run_id_from_checkpoint_fn: Callable[[str], str],
    build_benchmark_payload_fn: Callable[..., Dict],
    persist_bench_artifacts_fn: Callable[..., None],
    publish_eval_catalog_fn: Callable[..., None],
    publish_eval_run_fn,
    aggregate_muzero_eval_kpis_fn,
    build_phase29_train_eval_fn,
    build_phase29_promotion_gate_fn,
    build_eval_diagnostics_summary_fn,
    build_head_diagnostics_eval_fn,
    load_train_summary_fn,
    json_dumps_fn,
    mlflow_mod,
    mlflow_log_metrics_fn: Callable[..., None],
    build_phase29_mlflow_metrics_fn: Callable[[Dict], Dict[str, float]],
    persist_replay_episode_files: bool = True,
) -> Dict:
    run_id = resolve_run_id_from_checkpoint_fn(checkpoint_path)
    payload = build_benchmark_payload_fn(
        schema_version=schema_version,
        scenario_id=str(scenario_id),
        run_id=str(run_id or ""),
        results=list(results or []),
        load_train_summary_fn=load_train_summary_fn,
        checkpoint_path=str(checkpoint_path or ""),
        aggregate_muzero_eval_kpis_fn=aggregate_muzero_eval_kpis_fn,
        build_phase29_train_eval_fn=build_phase29_train_eval_fn,
        build_phase29_promotion_gate_fn=build_phase29_promotion_gate_fn,
        build_eval_diagnostics_summary_fn=build_eval_diagnostics_summary_fn,
        build_head_diagnostics_eval_fn=build_head_diagnostics_eval_fn,
    )
    if run_id:
        persist_bench_artifacts_fn(
            run_id=str(run_id),
            scenario_id=str(scenario_id),
            run_root=run_root,
            payload=dict(payload or {}),
            results=list(results or []),
            bench_replay_episodes=list(bench_replay_episodes or []),
            json_dumps_fn=json_dumps_fn,
            persist_replay_episode_files=bool(persist_replay_episode_files),
        )
    publish_eval_catalog_fn(
        repo_root=repo_root,
        run_id=str(run_id or ""),
        publish_eval_run_fn=publish_eval_run_fn,
    )
    if mlflow_mod is not None:
        try:
            mlflow_log_metrics_fn(
                mlflow_mod,
                build_phase29_mlflow_metrics_fn(dict(payload or {})),
            )
            mlflow_mod.end_run()
        except Exception:
            pass
    return payload

