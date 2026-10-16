from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _safe_entropy(probs: List[float]) -> float:
    entropy = 0.0
    for p in probs:
        p_float = float(p)
        if p_float <= 0.0:
            continue
        entropy -= p_float * math.log(p_float)
    return float(entropy)


def _safe_kl_divergence(p: List[float], q: List[float], eps: float = 1e-9) -> float:
    kl = 0.0
    for pi, qi in zip(p, q):
        pi_f = max(eps, float(pi))
        qi_f = max(eps, float(qi))
        kl += pi_f * math.log(pi_f / qi_f)
    return float(max(0.0, kl))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        return z / (1.0 + z)


def _softmax(logits: List[float]) -> List[float]:
    if not logits:
        return []
    max_l = max(logits)
    exps = [math.exp(l - max_l) for l in logits]
    total = sum(exps)
    if total <= 0:
        return [1.0 / len(logits)] * len(logits)
    return [e / total for e in exps]


def _clean_val(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        if hasattr(v, "item"):
            return float(v.item())
        return float(v)
    except Exception:
        return default


def _clean_list(v: Any) -> list:
    if v is None:
        return []
    if hasattr(v, "detach"):
        v = v.detach()
    if hasattr(v, "cpu"):
        v = v.cpu()
    if hasattr(v, "tolist"):
        return v.tolist()
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def build_decision_report(
    step: int,
    actions: List[str],
    probs: List[float],
    priors: Optional[List[float]] = None,
    values: Optional[List[float]] = None,
    visits: Optional[List[int]] = None,
    rewards: Optional[List[float]] = None,
    q_values: Optional[List[float]] = None,
    u_values: Optional[List[float]] = None,
    root_value: Optional[float] = None,
    factor_contributions: Optional[Dict[str, float]] = None,
    aux_outputs: Optional[Dict[str, Any]] = None,
    objective_info: Optional[Dict[str, Any]] = None,
    intent_info: Optional[Dict[str, Any]] = None,
    multi_vp_info: Optional[Dict[str, Any] | List[float]] = None,
    consistency_info: Optional[Dict[str, Any] | float] = None,
    entropy_threshold: float = 1.0,
    margin_threshold: float = 0.05,
    top_k: int = 5,
    include_heads_analysis: Optional[bool] = None,
) -> Dict[str, Any]:
    rows = []
    has_custom_action_metrics = rewards is not None or q_values is not None or u_values is not None

    for idx, action_id in enumerate(actions):
        prob = float(probs[idx]) if idx < len(probs) else 0.0
        prior = float(priors[idx]) if priors is not None and idx < len(priors) else prob
        value = float(values[idx]) if values is not None and idx < len(values) else 0.0
        visit_count = int(visits[idx]) if visits is not None and idx < len(visits) else 0

        score_dict: Dict[str, Any] = {
            "policy_prob": prob,
            "prior": prior,
            "value": value,
            "visit_count": visit_count,
        }
        if rewards is not None:
            score_dict["reward"] = float(rewards[idx]) if idx < len(rewards) else 0.0
        if q_values is not None:
            score_dict["q_value"] = float(q_values[idx]) if idx < len(q_values) else 0.0
        if u_values is not None:
            score_dict["u_value"] = float(u_values[idx]) if idx < len(u_values) else 0.0

        row: Dict[str, Any] = {
            "action_id": str(action_id),
            "score": score_dict,
        }
        rows.append(row)

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

    report: Dict[str, Any] = {
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

    # Decide if heads analysis should be attached
    has_explicit_head_data = (
        has_custom_action_metrics
        or root_value is not None
        or aux_outputs is not None
        or objective_info is not None
        or intent_info is not None
        or multi_vp_info is not None
        or consistency_info is not None
    )
    should_include_heads = (
        include_heads_analysis
        if include_heads_analysis is not None
        else has_explicit_head_data
    )

    if should_include_heads:
        # 1. Policy Head analysis
        ranked_by_prior = sorted(rows, key=lambda x: x["score"]["prior"], reverse=True)
        top_prior_row = ranked_by_prior[0] if ranked_by_prior else None
        chosen_mcts_row = ranked[0] if ranked else None

        policy_top_action = top_prior_row["action_id"] if top_prior_row else ""
        policy_top_prior = top_prior_row["score"]["prior"] if top_prior_row else 0.0
        mcts_chosen_action = chosen_mcts_row["action_id"] if chosen_mcts_row else ""
        mcts_chosen_prior = chosen_mcts_row["score"]["prior"] if chosen_mcts_row else 0.0

        all_priors = [r["score"]["prior"] for r in rows]
        prior_entropy = _safe_entropy(all_priors)
        all_probs = [r["score"]["policy_prob"] for r in rows]
        kl_div = _safe_kl_divergence(all_probs, all_priors) if len(all_probs) == len(all_priors) else 0.0
        is_overridden = bool(policy_top_action != mcts_chosen_action)

        policy_head_summary = {
            "top_action_id": policy_top_action,
            "top_prior": float(policy_top_prior),
            "mcts_chosen_action_id": mcts_chosen_action,
            "mcts_chosen_prior": float(mcts_chosen_prior),
            "is_overridden_by_mcts": is_overridden,
            "prior_entropy": float(prior_entropy),
            "kl_divergence_mcts_prior": float(kl_div),
        }

        # 2. Value Head analysis
        all_values = [r["score"]["value"] for r in rows]
        chosen_value = chosen_mcts_row["score"]["value"] if chosen_mcts_row else 0.0
        max_val = max(all_values) if all_values else 0.0
        min_val = min(all_values) if all_values else 0.0
        root_val_clean = _clean_val(root_value) if root_value is not None else None

        value_head_summary = {
            "root_value": root_val_clean,
            "chosen_action_value": float(chosen_value),
            "max_action_value": float(max_val),
            "min_action_value": float(min_val),
            "value_spread": float(max_val - min_val),
        }

        # 3. Reward Head analysis
        reward_head_summary: Dict[str, Any] = {}
        if rewards is not None:
            all_rewards = [r["score"].get("reward", 0.0) for r in rows]
            chosen_rew = chosen_mcts_row["score"].get("reward", 0.0) if chosen_mcts_row else 0.0
            max_rew = max(all_rewards) if all_rewards else 0.0
            reward_head_summary = {
                "chosen_action_reward": float(chosen_rew),
                "max_action_reward": float(max_rew),
                "has_immediate_reward": bool(any(abs(r) > 1e-4 for r in all_rewards)),
            }

        # 4. Auxiliary Heads extraction
        aux_dict = dict(aux_outputs or {})
        auxiliary_summary: Dict[str, Any] = {}

        # Objective head
        obj_payload = dict(objective_info or {})
        if "objective_logit" in aux_dict and "raw_logit" not in obj_payload:
            obj_payload["raw_logit"] = _clean_val(aux_dict["objective_logit"])
        if "raw_logit" in obj_payload and "predicted_prob" not in obj_payload:
            obj_payload["predicted_prob"] = _sigmoid(obj_payload["raw_logit"])
        if "predicted_prob" in obj_payload and "predicted_conversion" not in obj_payload:
            obj_payload["predicted_conversion"] = bool(obj_payload["predicted_prob"] >= 0.5)
        if obj_payload:
            auxiliary_summary["objective"] = obj_payload

        # Intent head
        intent_payload = dict(intent_info or {})
        if "intent_logits" in aux_dict and "probabilities" not in intent_payload:
            raw_logits = [_clean_val(x) for x in _clean_list(aux_dict["intent_logits"])]
            probs_list = _softmax(raw_logits)
            intent_payload["probabilities"] = probs_list
            if probs_list:
                best_idx = int(max(range(len(probs_list)), key=lambda i: probs_list[i]))
                intent_payload["predicted_intent_class"] = best_idx
                intent_payload["confidence"] = float(probs_list[best_idx])
        if intent_payload:
            auxiliary_summary["intent"] = intent_payload

        # Multi-VP head
        multi_vp_payload: Dict[str, Any] = {}
        if isinstance(multi_vp_info, dict):
            multi_vp_payload = dict(multi_vp_info)
        elif isinstance(multi_vp_info, (list, tuple)):
            multi_vp_payload = {"vp_distances": [_clean_val(x) for x in multi_vp_info]}
        elif "multi_vp_pred" in aux_dict:
            multi_vp_payload = {
                "vp_distances": [_clean_val(x) for x in _clean_list(aux_dict["multi_vp_pred"])]
            }
        if "vp_distances" in multi_vp_payload and multi_vp_payload["vp_distances"]:
            dists = multi_vp_payload["vp_distances"]
            if isinstance(dists, list) and dists:
                multi_vp_payload["min_distance"] = float(min(dists))
        if multi_vp_payload:
            auxiliary_summary["multi_vp"] = multi_vp_payload

        # Consistency head
        consistency_payload: Dict[str, Any] = {}
        if isinstance(consistency_info, dict):
            consistency_payload = dict(consistency_info)
        elif consistency_info is not None:
            consistency_payload = {"drift": _clean_val(consistency_info)}
        elif "consistency_drift" in aux_dict:
            consistency_payload = {"drift": _clean_val(aux_dict["consistency_drift"])}
        if "drift" in consistency_payload and "is_stable" not in consistency_payload:
            consistency_payload["is_stable"] = bool(consistency_payload["drift"] < 0.15)
        if consistency_payload:
            auxiliary_summary["consistency"] = consistency_payload

        # 5. Tactical Insights generation
        tactical_insights: List[str] = []
        if is_overridden:
            tactical_insights.append(
                f"MCTS search overrode Policy Head: Policy preferred '{policy_top_action}' "
                f"(prior={policy_top_prior:.2f}), but MCTS chose '{mcts_chosen_action}' "
                f"(prob={top_prob:.2f}, prior={mcts_chosen_prior:.2f})."
            )
        else:
            tactical_insights.append(
                f"Policy Head aligned with MCTS search on '{mcts_chosen_action}' "
                f"(prior={mcts_chosen_prior:.2f}, prob={top_prob:.2f})."
            )

        if value_head_summary["value_spread"] >= 0.5:
            tactical_insights.append(
                f"High action-value spread ({value_head_summary['value_spread']:.2f}) indicates a critical decision fork."
            )

        if "objective" in auxiliary_summary:
            prob_obj = auxiliary_summary["objective"].get("predicted_prob")
            if prob_obj is not None and prob_obj > 0.6:
                tactical_insights.append(
                    f"Objective Head predicts high likelihood of objective capture/progress ({prob_obj:.1%})."
                )

        if "consistency" in auxiliary_summary:
            if not auxiliary_summary["consistency"].get("is_stable", True):
                tactical_insights.append(
                    f"Latent consistency drift detected ({auxiliary_summary['consistency'].get('drift', 0.0):.3f})."
                )

        heads_analysis: Dict[str, Any] = {
            "policy_head": policy_head_summary,
            "value_head": value_head_summary,
            "tactical_insights": tactical_insights,
        }
        if reward_head_summary:
            heads_analysis["reward_head"] = reward_head_summary
        if auxiliary_summary:
            heads_analysis["auxiliary_heads"] = auxiliary_summary

        report["heads_analysis"] = heads_analysis

    return report

