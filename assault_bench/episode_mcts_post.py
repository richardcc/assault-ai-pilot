from __future__ import annotations

import math
from typing import Dict, List, Tuple


def resolve_action_and_root_metrics(
    *,
    mcts_out,
    sampled_action: str,
    side: str,
    obs_vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
    select_action_with_probability_tie_break_fn,
) -> Dict[str, object]:
    action = str(sampled_action or "")
    action_selection_source = "mcts_prob_sample"
    probs = [float(x) for x in (mcts_out.probs or [])]
    visit_counts = [int(v) for v in (mcts_out.visits or [])]
    mcts_breakdown_by_action = {}
    for b in list(getattr(mcts_out, "root_candidate_breakdown", []) or []):
        if not isinstance(b, dict):
            continue
        aid_b = str(b.get("action_id", "") or "")
        if aid_b:
            mcts_breakdown_by_action[aid_b] = dict(b)
    if probs and list(mcts_out.actions or []):
        action, action_selection_source = select_action_with_probability_tie_break_fn(
            sampled_action=str(action),
            actions=[str(a) for a in list(mcts_out.actions or [])],
            probs=list(probs),
            visits=list(visit_counts),
            breakdown_by_action=dict(mcts_breakdown_by_action),
            side=str(side),
            vp_hexes=list(obs_vp_hexes or []),
            vp_owner_by_hex=dict(vp_owner_by_hex or {}),
        )
    visit_total = int(sum(visit_counts))
    chosen_prob = 0.0
    margin = 0.0
    mcts_entropy = 0.0
    if probs:
        for a_id, p in zip(list(mcts_out.actions or []), probs):
            if str(a_id) == str(action):
                chosen_prob = float(p)
                break
        if chosen_prob <= 0.0:
            chosen_prob = float(max(probs))
        top2 = sorted(probs, reverse=True)[:2]
        margin = float(top2[0] - top2[1]) if len(top2) > 1 else float(top2[0])
        entropy_probs = (
            [float(max(0.0, v)) / float(visit_total) for v in visit_counts]
            if visit_total > 0
            else list(probs)
        )
        for p in entropy_probs:
            pp = float(max(1e-12, p))
            mcts_entropy += -pp * math.log(pp)
    mcts_total_visits = int(visit_total)
    mcts_active_actions = int(sum(1 for v in (mcts_out.visits or []) if int(v) > 0))
    visits_by_action = {
        str(a): int(v)
        for a, v in zip(list(mcts_out.actions or []), list(mcts_out.visits or []))
    }
    root_actions_for_explain = [
        str(a) for a in list(getattr(mcts_out, "actions", []) or []) if str(a or "").strip()
    ]
    return {
        "action": str(action),
        "action_selection_source": str(action_selection_source),
        "probs": list(probs),
        "visit_counts": list(visit_counts),
        "mcts_breakdown_by_action": dict(mcts_breakdown_by_action),
        "chosen_prob": float(chosen_prob),
        "margin": float(margin),
        "mcts_entropy": float(mcts_entropy),
        "mcts_total_visits": int(mcts_total_visits),
        "mcts_active_actions": int(mcts_active_actions),
        "visits_by_action": dict(visits_by_action),
        "root_actions_for_explain": list(root_actions_for_explain),
    }


def enrich_candidates_from_breakdown(
    *,
    mcts_action_candidates: List[Dict[str, object]],
    mcts_breakdown_by_action: Dict[str, Dict[str, object]],
    mcts_out,
    probs: List[float],
    visit_total: int,
    chosen_action_text: str,
    action_selection_source: str,
    dedupe_candidates_fn,
) -> Tuple[List[Dict[str, object]], int]:
    probs_by_action = {
        str(a): float(p)
        for a, p in zip(list(mcts_out.actions or []), list(probs or []))
    }
    total_visits_f = float(max(0, int(visit_total)))
    enriched_candidates: List[Dict[str, object]] = []
    for c in list(mcts_action_candidates or []):
        c_out = dict(c or {})
        aid = str(c_out.get("action_id", "") or "")
        breakdown_row = dict(mcts_breakdown_by_action.get(aid, {}) or {})
        if aid and breakdown_row:
            if breakdown_row.get("q_value", None) is not None:
                c_out["mcts_q_value"] = float(breakdown_row.get("q_value"))
            if breakdown_row.get("u_value", None) is not None:
                c_out["mcts_u_value"] = float(breakdown_row.get("u_value"))
            if breakdown_row.get("puct_score", None) is not None:
                c_out["real_decision_score"] = float(breakdown_row.get("puct_score"))
                c_out["final_score"] = float(breakdown_row.get("puct_score"))
            c_out["mcts_q_unclipped"] = (
                float(breakdown_row.get("q_unclipped"))
                if breakdown_row.get("q_unclipped", None) is not None
                else None
            )
            c_out["mcts_q_clipped"] = (
                float(breakdown_row.get("q_clipped"))
                if breakdown_row.get("q_clipped", None) is not None
                else None
            )
            c_out["mcts_q_norm_applied"] = bool(
                breakdown_row.get(
                    "q_norm_applied",
                    getattr(mcts_out, "q_root_normalization_applied", False),
                )
            )
        vc = int(max(0, int(c_out.get("visit_count", 0) or 0)))
        dc_raw = c_out.get("decision_components", {})
        dc = dict(dc_raw) if isinstance(dc_raw, dict) else {}
        c_out["visit_share"] = (
            float(vc) / total_visits_f if total_visits_f > 0.0 else None
        )
        c_out["chosen_action_prob"] = (
            float(probs_by_action.get(aid, 0.0))
            if aid in probs_by_action
            else 0.0
        )
        c_out["selection_source"] = (
            str(action_selection_source)
            if aid == chosen_action_text
            else "mcts_prob_non_selected"
        )
        c_out["policy_prior_source"] = (
            "producer_policy_head_prior"
            if c_out.get("policy_prior", None) is not None
            else "missing"
        )
        c_out["policy_prior_available"] = bool(c_out.get("policy_prior", None) is not None)
        c_out["mcts_q_value_source"] = (
            "producer_mcts_breakdown"
            if c_out.get("mcts_q_value", None) is not None
            else "missing"
        )
        c_out["mcts_q_value_available"] = bool(c_out.get("mcts_q_value", None) is not None)
        c_out["mcts_u_value_source"] = (
            "producer_mcts_breakdown"
            if c_out.get("mcts_u_value", None) is not None
            else "missing"
        )
        c_out["mcts_u_value_available"] = bool(c_out.get("mcts_u_value", None) is not None)
        c_out["mcts_success_prob_proxy_source"] = (
            "decision_components"
            if dc.get("mcts_success_prob_proxy", dc.get("success_prob_proxy", None)) is not None
            else "missing"
        )
        c_out["mcts_success_prob_proxy_available"] = bool(
            dc.get("mcts_success_prob_proxy", dc.get("success_prob_proxy", None)) is not None
        )
        c_out["mcts_success_component_source"] = (
            "decision_components"
            if dc.get("mcts_success_component", dc.get("success_component", None)) is not None
            else "missing"
        )
        c_out["mcts_success_component_available"] = bool(
            dc.get("mcts_success_component", dc.get("success_component", None)) is not None
        )
        c_out["vp_horizon_steps_available"] = bool(c_out.get("vp_horizon_steps", None) is not None)
        c_out["vp_horizon_signal_available"] = bool(c_out.get("vp_horizon_signal", None) is not None)
        c_out["vp_horizon_decision_component_available"] = bool(
            c_out.get("vp_horizon_decision_component", c_out.get("vp_horizon_component", None)) is not None
        )
        enriched_candidates.append(c_out)
    if not enriched_candidates:
        enriched_candidates.append(
            {
                "action_id": chosen_action_text,
                "selected_action": True,
                "visit_count": 0,
                "visit_share": 0.0,
                "chosen_action_prob": float(max(0.0, max(probs) if probs else 0.0)),
                "selection_source": "fallback_no_candidates",
                "policy_prior": None,
                "mcts_q_value": None,
                "mcts_u_value": None,
                "decision_rank": 1,
                "real_decision_score": float(max(0.0, max(probs) if probs else 0.0)),
                "policy_prior_source": "fallback_missing",
                "policy_prior_available": False,
                "mcts_q_value_source": "fallback_missing",
                "mcts_q_value_available": False,
                "mcts_u_value_source": "fallback_missing",
                "mcts_u_value_available": False,
                "mcts_success_prob_proxy_source": "fallback_missing",
                "mcts_success_prob_proxy_available": False,
                "mcts_success_component_source": "fallback_missing",
                "mcts_success_component_available": False,
                "vp_horizon_steps_available": False,
                "vp_horizon_signal_available": False,
                "vp_horizon_decision_component_available": False,
                "decision_components": {
                    "mcts_success_component": None,
                    "success_component": None,
                    "mcts_success_prob_proxy": None,
                    "success_prob_proxy": None,
                    "vp_horizon_steps": None,
                    "vp_horizon_signal": None,
                    "vp_horizon_component": None,
                    "vp_horizon_decision_component": None,
                    "objective_soft_reward_component": None,
                    "global_strategy_soft_reward_component": None,
                    "reaction_fire_soft_reward_component": None,
                    "tie_break_term": None,
                },
            }
        )
    out, collapsed = dedupe_candidates_fn(enriched_candidates)
    return list(out or []), int(collapsed)

