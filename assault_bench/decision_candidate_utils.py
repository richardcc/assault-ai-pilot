from __future__ import annotations

from typing import Dict, List


def canonicalize_decision_candidates(
    candidate_rows: List[Dict[str, object]],
    chosen_action_id: str,
    *,
    default_policy_prior_zero: bool = True,
) -> List[Dict[str, object]]:
    rows = [dict(c or {}) for c in list(candidate_rows or [])]
    if not rows:
        return []
    chosen_action_id = str(chosen_action_id or "")
    for row in rows:
        action_id = str(row.get("action_id", "") or "")
        final_score = row.get("real_decision_score", row.get("final_score", 0.0))
        try:
            final_score_f = float(final_score if final_score is not None else 0.0)
        except Exception:
            final_score_f = 0.0
        visit_count = row.get("visit_count", 0)
        try:
            visit_count_i = int(visit_count if visit_count is not None else 0)
        except Exception:
            visit_count_i = 0
        row["action_id"] = action_id
        row["final_score"] = float(final_score_f)
        row["real_decision_score"] = float(final_score_f)
        row["visit_count"] = int(max(0, visit_count_i))
        row["mcts_q_value"] = (
            float(row.get("mcts_q_value"))
            if row.get("mcts_q_value", None) is not None
            else None
        )
        row["mcts_u_value"] = (
            float(row.get("mcts_u_value"))
            if row.get("mcts_u_value", None) is not None
            else None
        )
        row["mcts_success_prob_proxy"] = (
            float(row.get("mcts_success_prob_proxy"))
            if row.get("mcts_success_prob_proxy", None) is not None
            else None
        )
        row["mcts_success_component"] = (
            float(row.get("mcts_success_component"))
            if row.get("mcts_success_component", None) is not None
            else None
        )
        row["mcts_puct_score"] = (
            float(row.get("mcts_puct_score"))
            if row.get("mcts_puct_score", None) is not None
            else None
        )
        if default_policy_prior_zero:
            row["policy_prior"] = float(row.get("policy_prior", 0.0) or 0.0)
        else:
            row["policy_prior"] = (
                float(row.get("policy_prior"))
                if row.get("policy_prior", None) is not None
                else None
            )
        row["vp_horizon_steps"] = (
            float(row.get("vp_horizon_steps"))
            if row.get("vp_horizon_steps", None) is not None
            else None
        )
        row["vp_horizon_signal"] = (
            float(row.get("vp_horizon_signal"))
            if row.get("vp_horizon_signal", None) is not None
            else None
        )
        row["vp_horizon_component"] = (
            float(row.get("vp_horizon_component"))
            if row.get("vp_horizon_component", None) is not None
            else None
        )
        h_dec = row.get("vp_horizon_decision_component", row.get("vp_horizon_component", None))
        row["vp_horizon_decision_component"] = float(h_dec) if h_dec is not None else None
        row["selected_action"] = bool(action_id == chosen_action_id)
        row["selected_by"] = str(row.get("selected_by", "") or "mcts_puct")
        row["decision_criterion"] = str(row.get("decision_criterion", "mcts_puct"))
        row["decision_components"] = {
            "visit_count": int(row["visit_count"]),
            "q_value": float(row["mcts_q_value"]) if row.get("mcts_q_value", None) is not None else None,
            "u_value": float(row["mcts_u_value"]) if row.get("mcts_u_value", None) is not None else None,
            "success_prob_proxy": (
                float(row["mcts_success_prob_proxy"])
                if row.get("mcts_success_prob_proxy", None) is not None
                else None
            ),
            "success_component": (
                float(row["mcts_success_component"])
                if row.get("mcts_success_component", None) is not None
                else None
            ),
            "puct_score": float(row["mcts_puct_score"]) if row.get("mcts_puct_score", None) is not None else None,
            "policy_prior": float(row["policy_prior"]) if row.get("policy_prior", None) is not None else None,
            "tie_break_term": (
                float(row.get("vp_progress_delta"))
                if row.get("vp_progress_delta", None) is not None
                else None
            ),
            "tie_break_source": str(row.get("vp_progress_source", "unknown") or "unknown"),
            "vp_horizon_steps": float(row["vp_horizon_steps"]) if row.get("vp_horizon_steps", None) is not None else None,
            "vp_horizon_signal": float(row["vp_horizon_signal"]) if row.get("vp_horizon_signal", None) is not None else None,
            "vp_horizon_component": (
                float(row["vp_horizon_component"])
                if row.get("vp_horizon_component", None) is not None
                else None
            ),
        }
    ranked = sorted(
        rows,
        key=lambda r: (
            -float(r.get("real_decision_score", 0.0) or 0.0),
            -int(r.get("visit_count", 0) or 0),
            str(r.get("action_id", "")),
        ),
    )
    rank_by_action = {str(r.get("action_id", "")): int(i + 1) for i, r in enumerate(ranked)}
    for row in rows:
        row["decision_rank"] = int(rank_by_action.get(str(row.get("action_id", "")), len(rows)))
    return rows
