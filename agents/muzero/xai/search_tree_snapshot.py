from __future__ import annotations

import math
from typing import Dict, List, Optional


def build_search_snapshot(
    actions: List[str],
    visits: List[int],
    probs: List[float],
    priors: Optional[List[float]] = None,
    values: Optional[List[float]] = None,
    max_nodes: int = 12,
) -> Dict:
    nodes = []
    for idx, action_id in enumerate(actions):
        visit_count = int(visits[idx]) if idx < len(visits) else 0
        policy_prob = float(probs[idx]) if idx < len(probs) else 0.0
        prior = float(priors[idx]) if priors is not None and idx < len(priors) else policy_prob
        value = float(values[idx]) if values is not None and idx < len(values) else 0.0
        nodes.append(
            {
                "action_id": str(action_id),
                "score": {
                    "visit_count": visit_count,
                    "policy_prob": policy_prob,
                    "prior": prior,
                    "value": value,
                },
            }
        )
    ranked = sorted(nodes, key=lambda x: x["score"]["visit_count"], reverse=True)
    limited_nodes = ranked[: max(1, int(max_nodes))]
    total_visits = sum(max(0, n["score"]["visit_count"]) for n in limited_nodes)
    entropy = 0.0
    for n in limited_nodes:
        p = float(n["score"]["policy_prob"])
        if p > 0.0:
            entropy -= p * math.log(p)
    return {
        "root": {
            "expanded_children": len(nodes),
            "snapshot_children": len(limited_nodes),
            "total_visits": int(total_visits),
            "policy_entropy": float(entropy),
        },
        "nodes": limited_nodes,
    }
