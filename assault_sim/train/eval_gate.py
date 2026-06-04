from __future__ import annotations


def composite_eval_score(eval_stats: dict, damage_weight: float = 0.25) -> float:
    win_rate = float(eval_stats.get("win_rate", 0.0))
    damage_ratio = float(eval_stats.get("damage_ratio", 0.0))
    return win_rate + damage_weight * damage_ratio


def should_promote_best(
    *,
    score: float,
    best_score: float,
    min_improvement: float,
) -> bool:
    return score >= (best_score + min_improvement)

