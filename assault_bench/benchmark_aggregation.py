from __future__ import annotations

from typing import Dict, List, Tuple

from assault_bench.transform_ops import to_dict_rows


def accumulate_seed_episode(
    *,
    seed_used: int,
    scenario_id: str,
    ret: float,
    step_count: int,
    terminal: bool,
    timeout: bool,
    win: bool,
    winner_side: str,
    scenario_outcome: Dict[str, object],
    phase29_summary: Dict[str, object],
    trace_rows: List[Dict[str, object]],
    agent_name: str,
    episode_index: int,
    collect_flow_metrics: bool,
    returns: List[float],
    steps: List[int],
    terminals: List[bool],
    timeouts: List[bool],
    wins: List[bool],
    vp_initial_counts_by_side: Dict[str, Dict[int, int]],
    vp_initial_sum_by_side: Dict[str, float],
    vp_final_counts_by_side: Dict[str, Dict[int, int]],
    vp_final_sum_by_side: Dict[str, float],
    vp_gained_sum_by_side: Dict[str, float],
    vp_lost_sum_by_side: Dict[str, float],
    winner_side_counts: Dict[str, int],
    tracked_side: str,
    tracked_metric: str,
    tracked_captured_values: List[int],
    scenario_outcome_counts: Dict[str, int],
    scenario_outcome_class_counts: Dict[str, int],
    scenario_outcome_class_counts_by_side: Dict[str, Dict[str, int]],
    seed_games_rows: List[Dict[str, object]],
    tracked_outcome_bucket_counts: Dict[str, int],
    opponent_outcome_bucket_counts: Dict[str, int],
    phase29_seed_rows: List[Dict[str, object]],
    phase29_seed_rows_by_side: List[Dict[str, object]],
    decision_trace_rows_all: List[Dict[str, object]],
    bench_replay_episodes: List[Dict[str, object]],
    terminal_reason_counts: Dict[str, int],
    terminal_reason: str,
    initial_vp_by_side: Dict[str, int],
    final_vp_by_side: Dict[str, int],
    episode_elapsed_s: float | None,
    episode_timing_meta: Dict[str, object] | None,
    normalize_outcome_score_fn,
    compute_seed_side_outcome_metrics_fn,
    outcome_bucket_from_score_fn,
    outcome_bucket_from_class_fn,
) -> Tuple[str, str]:
    initial_side_rows = to_dict_rows(
        [{"side": k, "vp": v} for k, v in dict(initial_vp_by_side or {}).items()]
    )
    final_side_rows = to_dict_rows(
        [{"side": k, "vp": v} for k, v in dict(final_vp_by_side or {}).items()]
    )
    returns.append(ret)
    steps.append(step_count)
    terminals.append(terminal)
    timeouts.append(timeout)
    wins.append(win)
    for row in initial_side_rows:
        side_s = str(row.get("side", ""))
        vp_i = int(row.get("vp", 0) or 0)
        if side_s not in vp_initial_counts_by_side:
            vp_initial_counts_by_side[side_s] = {}
        vp_initial_counts_by_side[side_s][vp_i] = vp_initial_counts_by_side[side_s].get(vp_i, 0) + 1
        vp_initial_sum_by_side[side_s] = vp_initial_sum_by_side.get(side_s, 0.0) + float(vp_i)
    for row in final_side_rows:
        side_s = str(row.get("side", ""))
        vp_i = int(row.get("vp", 0) or 0)
        if side_s not in vp_final_counts_by_side:
            vp_final_counts_by_side[side_s] = {}
        vp_final_counts_by_side[side_s][vp_i] = vp_final_counts_by_side[side_s].get(vp_i, 0) + 1
        vp_final_sum_by_side[side_s] = vp_final_sum_by_side.get(side_s, 0.0) + float(vp_i)
    all_sides = {str(r.get("side", "")) for r in initial_side_rows} | {str(r.get("side", "")) for r in final_side_rows}
    for side in all_sides:
        side_key = str(side)
        vi = float(dict(initial_vp_by_side or {}).get(side, 0) or 0)
        vf = float(dict(final_vp_by_side or {}).get(side, 0) or 0)
        vp_gained_sum_by_side[side_key] = vp_gained_sum_by_side.get(side_key, 0.0) + max(0.0, vf - vi)
        vp_lost_sum_by_side[side_key] = vp_lost_sum_by_side.get(side_key, 0.0) + max(0.0, vi - vf)
    winner_key = str(winner_side or "").strip()
    if winner_key:
        winner_side_counts[winner_key] = winner_side_counts.get(winner_key, 0) + 1
    tracked_side = tracked_side or str(scenario_outcome.get("tracked_side", "")).strip()
    tracked_metric = tracked_metric or str(scenario_outcome.get("metric", "")).strip()
    tracked_captured_values.append(int(scenario_outcome.get("captured", 0) or 0))
    outcome_label = str(scenario_outcome.get("result", "")).strip() or "unknown"
    scenario_outcome_counts[outcome_label] = scenario_outcome_counts.get(outcome_label, 0) + 1
    outcome_class = str(scenario_outcome.get("outcome_class", "")).strip() or "unknown"
    scenario_outcome_class_counts[outcome_class] = scenario_outcome_class_counts.get(outcome_class, 0) + 1
    outcome_class_by_side = {
        str(side).strip().upper(): str(cls or "").strip().lower() or "unknown"
        for side, cls in dict(scenario_outcome.get("outcome_class_by_side", {}) or {}).items()
        if str(side or "").strip()
    }
    for side_key, side_class in outcome_class_by_side.items():
        side_bucket = scenario_outcome_class_counts_by_side.setdefault(str(side_key), {})
        side_bucket[side_class] = int(side_bucket.get(side_class, 0) + 1)
    outcome_score = normalize_outcome_score_fn(scenario_outcome.get("outcome_score", None))
    seed_side_metrics = compute_seed_side_outcome_metrics_fn(list(trace_rows or []))
    expected_sides = sorted(
        {
            str(k or "").strip().upper()
            for k in (
                list(dict(initial_vp_by_side or {}).keys())
                + list(dict(final_vp_by_side or {}).keys())
                + list(dict(seed_side_metrics or {}).keys())
            )
            if str(k or "").strip()
        }
    )
    missing_sides = [s for s in expected_sides if s not in dict(seed_side_metrics or {})]
    if missing_sides:
        raise RuntimeError(
            "seed side_metrics missing expected side(s): "
            f"seed={int(seed_used)} missing={missing_sides} expected={expected_sides}"
        )
    required_metric_keys = (
        "units_alive_final",
        "units_lost",
        "enemy_units_eliminated",
        "damage_dealt",
    )
    for side_key in expected_sides:
        metric_row = dict(dict(seed_side_metrics or {}).get(side_key, {}) or {})
        missing_metric_keys = [
            k for k in required_metric_keys if metric_row.get(k, None) is None
        ]
        if missing_metric_keys:
            raise RuntimeError(
                "seed side_metrics missing required metric key(s): "
                f"seed={int(seed_used)} side={side_key} missing={missing_metric_keys}"
            )
    seed_games_rows.append(
        {
            "seed": int(seed_used),
            "scenario_id": str(scenario_id or ""),
            "winner_side": str(winner_key or ""),
            "terminal": bool(terminal),
            "timeout": bool(timeout),
            "scenario_outcome_class": str(outcome_class),
            "scenario_outcome_class_by_side": dict(outcome_class_by_side),
            "scenario_outcome_score": outcome_score,
            "episode_wall_s": (
                float(episode_elapsed_s)
                if isinstance(episode_elapsed_s, (int, float))
                else None
            ),
            "episode_startup_s": (
                float(dict(episode_timing_meta or {}).get("startup_s", 0.0))
                if isinstance(dict(episode_timing_meta or {}).get("startup_s", None), (int, float))
                else None
            ),
            "episode_model_load_s": (
                float(dict(episode_timing_meta or {}).get("model_load_s", 0.0))
                if isinstance(dict(episode_timing_meta or {}).get("model_load_s", None), (int, float))
                else None
            ),
            "episode_compute_s": (
                float(dict(episode_timing_meta or {}).get("episode_s", 0.0))
                if isinstance(dict(episode_timing_meta or {}).get("episode_s", None), (int, float))
                else None
            ),
            "side_metrics": dict(seed_side_metrics or {}),
        }
    )
    tracked_bucket = (
        outcome_bucket_from_score_fn(outcome_score)
        if outcome_score is not None
        else outcome_bucket_from_class_fn(outcome_class)
    )
    tracked_outcome_bucket_counts[tracked_bucket] = tracked_outcome_bucket_counts.get(tracked_bucket, 0) + 1
    if tracked_bucket == "win":
        opponent_bucket = "loss"
    elif tracked_bucket == "loss":
        opponent_bucket = "win"
    else:
        opponent_bucket = tracked_bucket
    opponent_outcome_bucket_counts[opponent_bucket] = opponent_outcome_bucket_counts.get(opponent_bucket, 0) + 1
    if collect_flow_metrics:
        phase29_seed_rows.append(dict(phase29_summary or {}))
        phase29_seed_rows_by_side.append(dict((phase29_summary or {}).get("by_side", {}) or {}))
    decision_trace_rows_all.extend(list(trace_rows or []))
    bench_replay_episodes.append(
        {
            "agent_name": str(agent_name),
            "seed": int(seed_used),
            "episode_index": int(episode_index),
            "transitions": list(trace_rows or []),
        }
    )
    key = terminal_reason or "unknown"
    terminal_reason_counts[key] = terminal_reason_counts.get(key, 0) + 1
    return tracked_side, tracked_metric
