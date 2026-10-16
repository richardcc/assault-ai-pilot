from __future__ import annotations

import statistics
from typing import Dict, List

from assault_bench.benchmark_types import BenchmarkResult
from assault_bench.phase29_metrics import build_phase29_eval_kpis_from_seed_rows
from assault_bench.phase29_side_metrics import build_phase29_eval_kpis_by_side_from_seed_rows
from assault_bench.transform_ops import to_dict_rows


def _controller_label_from_policy(policy_name: str) -> str:
    policy = str(policy_name or "").strip().lower()
    if policy == "mcts":
        return "MuZero"
    if policy == "random":
        return "Random"
    return "Unknown"


def build_benchmark_result(
    *,
    agent_name: str,
    profile: str,
    group: str,
    goal: str,
    policy: str,
    policy_by_side: Dict[str, str],
    seeds: List[int],
    returns: List[float],
    steps: List[int],
    terminals: List[bool],
    timeouts: List[bool],
    wins: List[bool],
    terminal_reason_counts: Dict[str, int],
    vp_initial_sum_by_side: Dict[str, float],
    vp_final_sum_by_side: Dict[str, float],
    vp_initial_counts_by_side: Dict[str, Dict[int, int]],
    vp_final_counts_by_side: Dict[str, Dict[int, int]],
    vp_gained_sum_by_side: Dict[str, float],
    vp_lost_sum_by_side: Dict[str, float],
    winner_side_counts: Dict[str, int],
    tracked_side: str,
    tracked_metric: str,
    tracked_captured_values: List[int],
    scenario_outcome_counts: Dict[str, int],
    scenario_outcome_class_counts: Dict[str, int],
    scenario_outcome_class_counts_by_side: Dict[str, Dict[str, int]],
    tracked_outcome_bucket_counts: Dict[str, int],
    opponent_outcome_bucket_counts: Dict[str, int],
    phase29_seed_rows: List[Dict[str, float]],
    phase29_seed_rows_by_side: List[Dict[str, Dict[str, float]]],
    eval_decision_summary: Dict[str, object],
    eval_decisions_top: List[Dict[str, object]],
    eval_decision_steps_top: List[Dict[str, object]],
    seed_games_rows: List[Dict[str, object]],
    episode_wall_s_values: List[float],
    profile_wall_s: float,
) -> BenchmarkResult:
    side_keys = sorted(set(vp_initial_counts_by_side.keys()) | set(vp_final_counts_by_side.keys()))
    tracked_values = [int(x) for x in list(tracked_captured_values or [])]
    seed_games = to_dict_rows(seed_games_rows)
    controller_by_side = {
        str(side): _controller_label_from_policy(str(policy_name_for_side))
        for side, policy_name_for_side in dict(policy_by_side or {}).items()
        if str(side or "").strip()
    }
    timings = sorted(
        [float(v) for v in list(episode_wall_s_values or []) if isinstance(v, (int, float))]
    )
    p50 = float(statistics.median(timings)) if timings else 0.0
    if timings:
        idx95 = int(max(0, min(len(timings) - 1, round(0.95 * (len(timings) - 1)))))
        p95 = float(timings[idx95])
    else:
        p95 = 0.0
    mean_s = (float(sum(timings)) / float(max(1, len(timings)))) if timings else 0.0
    profile_wall_s_val = float(max(0.0, float(profile_wall_s or 0.0)))
    eps = (float(len(seeds)) / profile_wall_s_val) if profile_wall_s_val > 0.0 else 0.0
    total_episodes = max(1, len(seeds))
    timeout_count = sum(1 for x in timeouts if x)
    non_timeout_count = max(0, total_episodes - timeout_count)
    non_timeout_resolution_rate = float(non_timeout_count) / float(total_episodes)
    resolved_non_timeout_win_count = sum(
        1
        for timeout_flag, win_flag in zip(list(timeouts or []), list(wins or []))
        if (not bool(timeout_flag)) and bool(win_flag)
    )
    resolved_non_timeout_win_rate = (
        float(resolved_non_timeout_win_count) / float(non_timeout_count)
        if non_timeout_count > 0
        else 0.0
    )
    return BenchmarkResult(
        agent_name=agent_name,
        matchup_profile=profile,
        matchup_group=group,
        measurement_goal=goal,
        policy_name=policy,
        policy_by_side=dict(policy_by_side),
        controller_by_side=controller_by_side,
        episodes=len(seeds),
        avg_return=sum(returns) / len(returns),
        avg_steps=sum(steps) / len(steps),
        terminal_rate=sum(1 for x in terminals if x) / len(terminals),
        timeout_rate=sum(1 for x in timeouts if x) / len(timeouts),
        non_timeout_resolution_rate=non_timeout_resolution_rate,
        win_rate=sum(1 for x in wins if x) / len(wins),
        resolved_non_timeout_win_rate=resolved_non_timeout_win_rate,
        terminal_reasons={
            reason: count / len(seeds) for reason, count in terminal_reason_counts.items()
        },
        vp_initial_avg_by_side={
            side: (float(v) / float(max(1, len(seeds))))
            for side, v in vp_initial_sum_by_side.items()
        },
        vp_final_avg_by_side={
            side: (float(v) / float(max(1, len(seeds))))
            for side, v in vp_final_sum_by_side.items()
        },
        vp_net_avg_by_side={
            side: (
                float(vp_final_sum_by_side.get(side, 0.0) - vp_initial_sum_by_side.get(side, 0.0))
                / float(max(1, len(seeds)))
            )
            for side in side_keys
        },
        vp_gained_avg_by_side={
            side: (float(vp_gained_sum_by_side.get(side, 0.0)) / float(max(1, len(seeds))))
            for side in side_keys
        },
        vp_lost_avg_by_side={
            side: (float(vp_lost_sum_by_side.get(side, 0.0)) / float(max(1, len(seeds))))
            for side in side_keys
        },
        vp_final_distribution_by_side={
            side: {
                str(vp): (c / float(max(1, len(seeds))))
                for vp, c in sorted(counts.items(), key=lambda kv: kv[0])
            }
            for side, counts in vp_final_counts_by_side.items()
        },
        winner_side_counts={
            side: int(winner_side_counts.get(side, 0))
            for side in sorted(
                set(winner_side_counts.keys())
                | set(vp_initial_counts_by_side.keys())
                | set(vp_final_counts_by_side.keys())
            )
        },
        winner_side_rates={
            side: (float(winner_side_counts.get(side, 0)) / float(max(1, len(seeds))))
            for side in sorted(
                set(winner_side_counts.keys())
                | set(vp_initial_counts_by_side.keys())
                | set(vp_final_counts_by_side.keys())
            )
        },
        tracked_side=tracked_side,
        tracked_metric=tracked_metric,
        tracked_captured_avg=(
            sum(float(x) for x in tracked_values) / float(max(1, len(tracked_values)))
        ),
        tracked_captured_distribution={
            str(v): (
                float(sum(1 for x in tracked_values if int(x) == int(v)))
                / float(max(1, len(tracked_values)))
            )
            for v in sorted(set(tracked_values))
        },
        scenario_outcome_counts={k: int(v) for k, v in sorted(scenario_outcome_counts.items(), key=lambda kv: kv[0])},
        scenario_outcome_rates={
            k: (float(v) / float(max(1, len(seeds))))
            for k, v in sorted(scenario_outcome_counts.items(), key=lambda kv: kv[0])
        },
        scenario_outcome_class_counts={k: int(v) for k, v in sorted(scenario_outcome_class_counts.items(), key=lambda kv: kv[0])},
        scenario_outcome_class_rates={
            k: (float(v) / float(max(1, len(seeds))))
            for k, v in sorted(scenario_outcome_class_counts.items(), key=lambda kv: kv[0])
        },
        scenario_outcome_class_counts_by_side={
            str(side): {str(cls): int(cnt) for cls, cnt in sorted(dict(counts or {}).items(), key=lambda kv: kv[0])}
            for side, counts in sorted(dict(scenario_outcome_class_counts_by_side or {}).items(), key=lambda kv: kv[0])
        },
        scenario_outcome_class_rates_by_side={
            str(side): {
                str(cls): (float(cnt) / float(max(1, len(seeds))))
                for cls, cnt in sorted(dict(counts or {}).items(), key=lambda kv: kv[0])
            }
            for side, counts in sorted(dict(scenario_outcome_class_counts_by_side or {}).items(), key=lambda kv: kv[0])
        },
        tracked_outcome_bucket_counts={k: int(v) for k, v in sorted(tracked_outcome_bucket_counts.items(), key=lambda kv: kv[0])},
        tracked_outcome_bucket_rates={
            k: (float(v) / float(max(1, len(seeds))))
            for k, v in sorted(tracked_outcome_bucket_counts.items(), key=lambda kv: kv[0])
        },
        opponent_outcome_bucket_counts={k: int(v) for k, v in sorted(opponent_outcome_bucket_counts.items(), key=lambda kv: kv[0])},
        opponent_outcome_bucket_rates={
            k: (float(v) / float(max(1, len(seeds))))
            for k, v in sorted(opponent_outcome_bucket_counts.items(), key=lambda kv: kv[0])
        },
        phase_2_9_eval_kpis=build_phase29_eval_kpis_from_seed_rows(
            phase29_seed_rows=phase29_seed_rows
        ),
        phase_2_9_eval_kpis_by_side=build_phase29_eval_kpis_by_side_from_seed_rows(
            phase29_seed_rows_by_side=phase29_seed_rows_by_side
        ),
        eval_decision_summary=eval_decision_summary,
        eval_decisions_top=eval_decisions_top,
        eval_decision_steps_top=eval_decision_steps_top,
        seed_games=list(seed_games),
        profile_wall_s=profile_wall_s_val,
        episode_wall_s_mean=mean_s,
        episode_wall_s_p50=p50,
        episode_wall_s_p95=p95,
        episodes_per_second=eps,
    )
