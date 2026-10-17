"""Tactical Quality Metrics Engine for ASSAULT (EfficientZero v2).

Computes robust, side-debiased tactical metrics designed specifically for asymmetric
wargames and curriculum phases:
  1. Mirror Performance (Two-legged / mirror matchups): Cancels out intrinsic scenario side bias.
  2. Combat Exchange Ratio (CER): Attrition & force preservation efficiency.
  3. Objective Dominance (VP Net & Capture Rate).
  4. Operational Maturity (Resolution without stall / timeout rate).
  5. Calibrated Anchor-ELO (Bradley-Terry relative to Random and MCTS baselines).
  6. Composite Tactical Quality Score (TQS: 0-100) and Rank (S/A/B/C/D).
"""

from __future__ import annotations

import math
from typing import Any


ANCHOR_RATINGS = {
    "random": 800.0,
    "heuristic": 1100.0,
    "mcts_baseline": 1400.0,
    "selfplay": 1500.0,
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return default


def compute_side_score(win_rate: float, draw_rate: float) -> float:
    """Computes standard game outcome score: Win=1.0, Draw=0.5, Loss=0.0."""
    return max(0.0, min(1.0, win_rate + 0.5 * draw_rate))


def compute_anchor_elo(
    mirror_score_vs_random: float | None = None,
    mirror_score_vs_mcts: float | None = None,
    default_elo: float = 1200.0,
) -> float:
    """Calculates Bradley-Terry anchor-based ELO calibrated against fixed reference agents.

    Inverts the standard logistic expectation:
      S = 1 / (1 + 10^((R_opp - R_model) / 400))
      => R_model = R_opp + 400 * log10(S / (1 - S))
    """
    estimates: list[tuple[float, float]] = []

    if mirror_score_vs_random is not None and not math.isnan(mirror_score_vs_random):
        s = max(0.02, min(0.98, mirror_score_vs_random))
        r_rand = ANCHOR_RATINGS["random"]
        implied = r_rand + 400.0 * math.log10(s / (1.0 - s))
        estimates.append((implied, 1.0))

    if mirror_score_vs_mcts is not None and not math.isnan(mirror_score_vs_mcts):
        s = max(0.02, min(0.98, mirror_score_vs_mcts))
        r_mcts = ANCHOR_RATINGS["mcts_baseline"]
        implied = r_mcts + 400.0 * math.log10(s / (1.0 - s))
        estimates.append((implied, 2.5))

    if not estimates:
        return default_elo

    total_weight = sum(w for _, w in estimates)
    weighted_elo = sum(e * w for e, w in estimates) / total_weight
    return round(weighted_elo, 1)


def compute_tactical_quality_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregates a list of side-result rows (e.g. from catalog_eval_result_sides)

    and computes the comprehensive Tactical Quality Score (TQS), Mirror Scores,
    CER, VP Dominance, and Anchor ELO.
    """
    if not rows:
        return {
            "status": "empty",
            "tactical_quality_score": 0.0,
            "tactical_grade": "D",
            "anchor_elo": 1200.0,
            "global_mirror_score_vs_random": 0.0,
            "global_mirror_score_vs_self": 0.5,
            "mean_asymmetry_gap": 0.0,
            "combat_exchange_ratio": 1.0,
            "vp_net_avg": 0.0,
            "tracked_captured_avg": 0.0,
            "decisive_rate": 0.0,
            "quality_gate": {"passed": False, "status": "FAIL", "reasons": ["No evaluation data found"]},
            "scenario_breakdown": {},
            "total_episodes": 0,
        }

    # Extract rows where the model was the controller on that side.
    # Note: If controller is 'random', that row reflects the Random agent's side.
    model_rows: list[dict[str, Any]] = []
    for r in rows:
        ctrl = str(r.get("controller") or "").strip().lower()
        if ctrl != "random":
            model_rows.append(r)

    if not model_rows:
        model_rows = rows

    # Group by scenario
    scenarios_set = sorted({str(r.get("scenario_id") or "").strip() for r in model_rows if str(r.get("scenario_id") or "").strip()})

    scenario_breakdown: dict[str, Any] = {}
    mirror_scores_random: list[float] = []
    mirror_scores_self: list[float] = []
    asymmetry_gaps: list[float] = []

    total_episodes = 0
    total_vp_net_weighted = 0.0
    total_captured_weighted = 0.0
    total_vic_weighted = 0.0
    total_def_weighted = 0.0

    for scen in scenarios_set:
        scen_rows = [r for r in model_rows if str(r.get("scenario_id") or "").strip() == scen]
        side_a_rows = [r for r in scen_rows if "side_a" in str(r.get("matchup_profile") or "").lower()]
        side_b_rows = [r for r in scen_rows if "side_b" in str(r.get("matchup_profile") or "").lower()]
        self_rows = [r for r in scen_rows if "self" in str(r.get("matchup_profile") or "").lower()]

        def _calc_score(r_list: list[dict[str, Any]]) -> float | None:
            if not r_list:
                return None
            tot_eps = sum(max(1, int(r.get("episodes") or 1)) for r in r_list)
            if tot_eps <= 0:
                return None
            tot_score = sum(
                (
                    float(r.get("score"))
                    if r.get("score") is not None
                    else compute_side_score(_safe_float(r.get("win_rate")), _safe_float(r.get("draw_rate")))
                )
                * max(1, int(r.get("episodes") or 1))
                for r in r_list
            )
            return tot_score / tot_eps

        score_a = _calc_score(side_a_rows)
        score_b = _calc_score(side_b_rows)
        score_self = _calc_score(self_rows)

        scen_res: dict[str, Any] = {
            "score_as_side_a_vs_random": round(score_a, 3) if score_a is not None else None,
            "score_as_side_b_vs_random": round(score_b, 3) if score_b is not None else None,
            "mirror_score_selfplay": round(score_self, 3) if score_self is not None else None,
        }

        if score_a is not None and score_b is not None:
            mirror_rand = (score_a + score_b) / 2.0
            gap = abs(score_a - score_b)
            mirror_scores_random.append(mirror_rand)
            asymmetry_gaps.append(gap)
            scen_res["mirror_score_vs_random"] = round(mirror_rand, 3)
            scen_res["asymmetry_gap"] = round(gap, 3)
        elif score_a is not None or score_b is not None:
            single = score_a if score_a is not None else score_b
            mirror_scores_random.append(single)
            scen_res["mirror_score_vs_random"] = round(single, 3)
            scen_res["asymmetry_gap"] = None
        else:
            scen_res["mirror_score_vs_random"] = None
            scen_res["asymmetry_gap"] = None

        if score_self is not None:
            mirror_scores_self.append(score_self)

        scenario_breakdown[scen] = scen_res

    # Overall Metrics across all model rows
    for r in model_rows:
        eps = max(1, int(r.get("episodes") or 1))
        vp_net = _safe_float(r.get("vp_net_avg_side"))
        captured = _safe_float(r.get("tracked_captured_avg"))
        tot_vic = _safe_float(r.get("total_victory_rate"))
        vic = _safe_float(r.get("victory_rate"))
        tot_def = _safe_float(r.get("total_defeat_rate"))
        def_rate = _safe_float(r.get("defeat_rate"))

        total_episodes += eps
        total_vp_net_weighted += vp_net * eps
        total_captured_weighted += captured * eps
        total_vic_weighted += (vic + 1.5 * tot_vic) * eps
        total_def_weighted += (def_rate + 1.5 * tot_def) * eps

    global_mirror_vs_random = (
        sum(mirror_scores_random) / len(mirror_scores_random) if mirror_scores_random else 0.5
    )
    global_mirror_vs_self = (
        sum(mirror_scores_self) / len(mirror_scores_self) if mirror_scores_self else 0.5
    )
    mean_asymmetry_gap = (
        sum(asymmetry_gaps) / len(asymmetry_gaps) if asymmetry_gaps else 0.0
    )

    # Combat Exchange Ratio (CER)
    cer = (
        (total_vic_weighted + 0.05) / max(0.1, total_def_weighted + 0.05)
        if (total_vic_weighted > 0 or total_def_weighted > 0)
        else 1.0
    )
    cer = round(min(10.0, max(0.1, cer)), 2)

    avg_vp_net = total_vp_net_weighted / max(1, total_episodes) if total_episodes > 0 else 0.0
    avg_captured = total_captured_weighted / max(1, total_episodes) if total_episodes > 0 else 0.0

    decisive_rate = total_vic_weighted / max(1, total_episodes) if total_episodes > 0 else 0.0
    decisive_rate = max(0.0, min(1.0, decisive_rate))

    # Anchor ELO
    anchor_elo = compute_anchor_elo(
        mirror_score_vs_random=global_mirror_vs_random,
        mirror_score_vs_mcts=global_mirror_vs_self,
    )

    # Composite Tactical Quality Score (TQS: 0 to 100)
    #  35% Mirror Performance vs MCTS/Self (strategic depth)
    #  25% Mirror Performance vs Random (tactical baseline)
    #  20% Combat Exchange Ratio (force preservation)
    #  10% VP Net (objective hold)
    #  10% Decisive resolution
    cer_normalized = max(0.0, min(1.0, math.log2(max(0.25, cer) + 0.75) / 1.7))
    vp_normalized = max(0.0, min(1.0, (avg_vp_net + 0.5) / 1.0))
    tqs_raw = (
        0.35 * global_mirror_vs_self
        + 0.25 * global_mirror_vs_random
        + 0.20 * cer_normalized
        + 0.10 * vp_normalized
        + 0.10 * decisive_rate
    )
    tqs = round(max(0.0, min(100.0, tqs_raw * 100.0)), 1)

    # Tactical Rank Grade
    if tqs >= 85.0:
        grade = "S (Elite Commander)"
    elif tqs >= 70.0:
        grade = "A (Proficient Tactician)"
    elif tqs >= 55.0:
        grade = "B (Competent / Advancing)"
    elif tqs >= 40.0:
        grade = "C (Developing / Fragile)"
    else:
        grade = "D (Sub-tactical / Unstable)"

    # Quality Gate Assessment
    passed_gate = (
        global_mirror_vs_random >= 0.55
        and cer >= 0.90
        and tqs >= 50.0
        and mean_asymmetry_gap <= 0.65
    )

    gate_reasons: list[str] = []
    if global_mirror_vs_random < 0.55:
        gate_reasons.append(f"Mirror vs Random under threshold ({global_mirror_vs_random:.2f} < 0.55)")
    if cer < 0.90:
        gate_reasons.append(f"CER under attrition parity ({cer:.2f} < 0.90)")
    if mean_asymmetry_gap > 0.65:
        gate_reasons.append(f"Excessive side fragility / asymmetry gap ({mean_asymmetry_gap:.2f} > 0.65)")

    return {
        "status": "ok",
        "tactical_quality_score": tqs,
        "tactical_grade": grade,
        "anchor_elo": anchor_elo,
        "global_mirror_score_vs_random": round(global_mirror_vs_random, 3),
        "global_mirror_score_vs_self": round(global_mirror_vs_self, 3),
        "mean_asymmetry_gap": round(mean_asymmetry_gap, 3),
        "combat_exchange_ratio": cer,
        "vp_net_avg": round(avg_vp_net, 3),
        "tracked_captured_avg": round(avg_captured, 2),
        "decisive_rate": round(decisive_rate, 3),
        "quality_gate": {
            "passed": passed_gate,
            "status": "PASS" if passed_gate else ("WARN" if tqs >= 45.0 else "FAIL"),
            "reasons": gate_reasons,
        },
        "scenario_breakdown": scenario_breakdown,
        "total_episodes": total_episodes,
    }
