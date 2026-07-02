from __future__ import annotations

import math
from typing import Dict, List, Optional


def _safe_entropy(probs: List[float]) -> float:
    entropy = 0.0
    for p in probs:
        p_float = float(p)
        if p_float <= 0.0:
            continue
        entropy -= p_float * math.log(p_float)
    return float(entropy)


def build_decision_report(
    step: int,
    actions: List[str],
    probs: List[float],
    priors: Optional[List[float]] = None,
    values: Optional[List[float]] = None,
    visits: Optional[List[int]] = None,
    factor_contributions: Optional[Dict[str, float]] = None,
    entropy_threshold: float = 1.0,
    margin_threshold: float = 0.05,
    top_k: int = 5,
) -> Dict:
    rows = []
    for idx, action_id in enumerate(actions):
        prob = float(probs[idx]) if idx < len(probs) else 0.0
        prior = float(priors[idx]) if priors is not None and idx < len(priors) else prob
        value = float(values[idx]) if values is not None and idx < len(values) else 0.0
        visit_count = int(visits[idx]) if visits is not None and idx < len(visits) else 0
        rows.append(
            {
                "action_id": str(action_id),
                "score": {
                    "policy_prob": prob,
                    "prior": prior,
                    "value": value,
                    "visit_count": visit_count,
                },
            }
        )
    ranked = sorted(rows, key=lambda x: x["score"]["policy_prob"], reverse=True)
    top_prob = ranked[0]["score"]["policy_prob"] if ranked else 0.0
    second_prob = ranked[1]["score"]["policy_prob"] if len(ranked) > 1 else 0.0
    margin = float(top_prob - second_prob)
    entropy = _safe_entropy([r["score"]["policy_prob"] for r in rows])
    dominant = sorted(
        (factor_contributions or {}).items(),
        key=lambda kv: abs(float(kv[1])),
        reverse=True,
    )[:3]
    return {
        "step": step,
        "top_k": ranked[: max(1, int(top_k))],
        "margin": margin,
        "entropy": entropy,
        "dominant_factors": [
            {"factor": str(name), "contribution": float(weight)} for name, weight in dominant
        ],
        "instability": {
            "unstable": bool(entropy >= float(entropy_threshold) or margin <= float(margin_threshold)),
            "reasons": {
                "high_entropy": bool(entropy >= float(entropy_threshold)),
                "low_margin": bool(margin <= float(margin_threshold)),
            },
            "thresholds": {
                "entropy_threshold": float(entropy_threshold),
                "margin_threshold": float(margin_threshold),
            },
        },
    }
