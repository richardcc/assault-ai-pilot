from __future__ import annotations

import math
from typing import Dict, List, Optional

from assault_bench.action_utils import (
    action_kind_from_id,
    action_unit_id_from_id,
    is_stationary_action_kind,
)
from assault_bench.decision_candidate_utils import canonicalize_decision_candidates
from assault_bench.telemetry_models import normalize_side_key
from assault_bench.vp_action_utils import (
    extract_vp_hexes,
    owner_by_qr,
    parse_action_target_hex,
)
from agents.efficientzero_v2.core.selfplay import (
    _best_enemy_vp_qr_for_side,
    _candidate_vp_progress_delta,
    _candidate_vp_target_after,
    _parse_action_id,
)


def axial_distance(a_q: int, a_r: int, b_q: int, b_r: int) -> int:
    dq = int(a_q) - int(b_q)
    dr = int(a_r) - int(b_r)
    ds = (int(a_q) + int(a_r)) - (int(b_q) + int(b_r))
    return int(max(abs(dq), abs(dr), abs(ds)))


def extract_unit_position(unit: object) -> Optional[tuple[int, int]]:
    def _read(obj: object, key: str, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _to_int(value: object) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    q_direct_keys = ("q", "hex_q", "hexQ", "col", "x")
    r_direct_keys = ("r", "hex_r", "hexR", "row", "y")
    for qk in q_direct_keys:
        q_v = _to_int(_read(unit, qk, None))
        if q_v is None:
            continue
        for rk in r_direct_keys:
            r_v = _to_int(_read(unit, rk, None))
            if r_v is not None:
                return int(q_v), int(r_v)

    nested_fields = ("position", "pos", "hex", "location", "coord", "coords")
    for nested_key in nested_fields:
        nested = _read(unit, nested_key, None)
        if nested is None:
            continue
        for qk in q_direct_keys:
            q_v = _to_int(_read(nested, qk, None))
            if q_v is None:
                continue
            for rk in r_direct_keys:
                r_v = _to_int(_read(nested, rk, None))
                if r_v is not None:
                    return int(q_v), int(r_v)
    return None


def extract_unit_identifier(unit: object) -> str:
    def _read(obj: object, key: str, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for key in ("unit_id", "unitId", "id", "unit_key", "unitKey"):
        value = str(_read(unit, key, "") or "").strip()
        if value:
            return value
    return ""


def lookup_actor_position_from_units(
    *,
    actor_unit_id: str,
    step_units_snapshot: Optional[List[object]],
) -> Optional[tuple[int, int]]:
    actor_key = str(actor_unit_id or "").strip()
    if not actor_key:
        return None
    for unit in list(step_units_snapshot or []):
        if extract_unit_identifier(unit) != actor_key:
            continue
        pos = extract_unit_position(unit)
        if pos is not None:
            return pos
    return None


def build_unit_position_index(step_units_snapshot: Optional[List[object]]) -> Dict[str, tuple[int, int]]:
    out: Dict[str, tuple[int, int]] = {}
    for unit in list(step_units_snapshot or []):
        uid = extract_unit_identifier(unit)
        if not uid:
            continue
        pos = extract_unit_position(unit)
        if pos is not None:
            out[uid] = (int(pos[0]), int(pos[1]))
    return out


def _clip_q_guardrail(value: float, clip_abs: Optional[float]) -> tuple[float, bool]:
    if clip_abs is None:
        return float(value), False
    limit = float(max(0.0, clip_abs))
    if limit <= 0.0:
        return 0.0, float(value) != 0.0
    v = float(value)
    if v > limit:
        return float(limit), True
    if v < -limit:
        return float(-limit), True
    return v, False


def select_vp_best_action(
    *,
    candidates: List[Dict[str, object]],
    chosen_action: str,
    objective_best_vp_id: str = "",
) -> Dict[str, object]:
    chosen_action_id = str(chosen_action or "")
    chosen = next((c for c in candidates if str(c.get("action_id", "")) == chosen_action_id), None)
    chosen_unit_id = action_unit_id_from_id(chosen_action_id)
    chosen_kind = action_kind_from_id(chosen_action_id)
    objective_best_vp_id = str(objective_best_vp_id or "").strip()
    move_candidates = [
        c
        for c in candidates
        if action_kind_from_id(str(c.get("action_id", ""))) == "MOVE"
        and action_unit_id_from_id(str(c.get("action_id", ""))) == chosen_unit_id
    ]
    if not move_candidates:
        return dict(chosen) if chosen is not None else {}

    def _delta_key(candidate: Dict[str, object]) -> tuple[float, float, str]:
        return (
            float(candidate.get("vp_progress_delta", 0.0) or 0.0),
            float(candidate.get("final_score", 0.0) or 0.0),
            str(candidate.get("action_id", "")),
        )

    primary_best = max(move_candidates, key=_delta_key)
    deltas = [float(c.get("vp_progress_delta", 0.0) or 0.0) for c in move_candidates]
    delta_span = (max(deltas) - min(deltas)) if deltas else 0.0
    has_non_unknown_delta = any(
        (
            (src := str(c.get("vp_progress_source", "") or "").strip().lower())
            and src != "unknown"
            and not src.startswith("unavailable_")
        )
        for c in move_candidates
    )
    if has_non_unknown_delta and delta_span > 1e-9:
        return dict(primary_best)
    if objective_best_vp_id:
        target_filtered = [c for c in move_candidates if str(c.get("vp_target_id", "") or "") == objective_best_vp_id]
        if target_filtered:
            move_candidates = target_filtered
    distance_candidates = [c for c in move_candidates if c.get("vp_distance_after", None) is not None]
    if distance_candidates:
        return dict(
            min(
                distance_candidates,
                key=lambda c: (
                    float(c.get("vp_distance_after", float("inf"))),
                    -float(c.get("final_score", 0.0) or 0.0),
                    str(c.get("action_id", "")),
                ),
            )
        )
    if chosen is not None and chosen_kind == "MOVE":
        return dict(chosen)
    return dict(primary_best)


def build_why_action_vs_vp(
    *,
    legal_actions: List[str],
    chosen_action: str,
    priors_by_action: Optional[Dict[str, float]],
    values_by_action: Optional[Dict[str, float]],
    value_sign_by_action: Optional[Dict[str, int]],
    visits_by_action: Dict[str, int],
    c_puct: float,
    dynamics_pred_reward: Optional[float],
    acting_unit_q: Optional[int],
    acting_unit_r: Optional[int],
    step_units_snapshot: Optional[List[object]] = None,
    vp_hexes: List[object],
    active_side: str = "",
    vp_owner_by_hex: Optional[Dict[str, str]] = None,
    top_k: Optional[int] = None,
    objective_best_vp_id: str = "",
    q_clip_abs: Optional[float] = 10.0,
    value_rescale_mode: str = "tanh",
    value_rescale_temperature: float = 10.0,
) -> Dict[str, object]:
    def _rescale_q_for_explain(value: float) -> float:
        mode = str(value_rescale_mode or "tanh").strip().lower()
        if mode in {"", "off", "none"}:
            return float(value)
        temp = max(1e-6, float(value_rescale_temperature))
        if mode == "tanh":
            return float(math.tanh(float(value) / temp))
        if mode in {"signed_log_tanh", "log_tanh"}:
            v = float(value)
            signed_log = math.copysign(math.log1p(abs(v)), v)
            return float(math.tanh(signed_log / temp))
        return float(math.tanh(float(value) / temp))

    def _normalize_vp_candidate(candidate: Dict[str, object]) -> Dict[str, object]:
        out = dict(candidate or {})
        vp_delta = out.get("vp_progress_delta", None)
        try:
            out["vp_progress_delta"] = float(vp_delta) if vp_delta is not None else None
        except Exception:
            out["vp_progress_delta"] = None
        src = str(out.get("vp_progress_source", "") or "").strip() or "unknown"
        out["vp_progress_source"] = src
        # Keep VP target/distance contract explicit for downstream consumers.
        out["vp_target_id"] = str(out.get("vp_target_id", "") or "").strip()
        out["vp_target_source"] = str(out.get("vp_target_source", "") or "").strip() or "missing"
        vp_dist = out.get("vp_distance_after", None)
        try:
            out["vp_distance_after"] = float(vp_dist) if vp_dist is not None else None
        except Exception:
            out["vp_distance_after"] = None
        vp_dist_source = str(out.get("vp_distance_source", "") or "").strip()
        if out["vp_distance_after"] is not None:
            out["vp_distance_source"] = vp_dist_source or "present_missing_source"
        else:
            out["vp_distance_source"] = vp_dist_source or "missing"
        return out

    if not legal_actions:
        return {
            "top_k": int(max(0, int(top_k or 0))),
            "chosen_action_id": str(chosen_action or ""),
            "vp_best_action_id": "",
            "delta_score": None,
            "score_components_priority": [],
            "explanation": "N/A (no legal actions)",
            "candidate_actions": [],
        }
    legal_action_ids = [str(a or "") for a in list(legal_actions or [])]
    total_visits = int(sum(int(max(0, visits_by_action.get(a, 0))) for a in legal_action_ids))
    root_sqrt = math.sqrt(max(1, total_visits))
    vp_cells_all = extract_vp_hexes(vp_hexes=vp_hexes)
    side_norm = normalize_side_key(active_side)
    owners_by_qr = owner_by_qr(dict(vp_owner_by_hex or {}))
    vp_cells = [
        (int(vq), int(vr), str(vp_id or ""))
        for vq, vr, vp_id in vp_cells_all
        if (not side_norm or normalize_side_key(owners_by_qr.get((int(vq), int(vr)), "")) != side_norm)
    ]
    base_actor_q = int(acting_unit_q) if isinstance(acting_unit_q, int) else None
    base_actor_r = int(acting_unit_r) if isinstance(acting_unit_r, int) else None
    chosen_unit_id = action_unit_id_from_id(str(chosen_action or ""))
    unit_pos_index = build_unit_position_index(step_units_snapshot)
    candidates: List[Dict[str, object]] = []
    for action_id in legal_action_ids:
        action_id = str(action_id or "")
        action_kind = action_kind_from_id(action_id)
        candidate_unit_id = action_unit_id_from_id(action_id)
        if candidate_unit_id and candidate_unit_id == chosen_unit_id:
            candidate_actor_q = base_actor_q
            candidate_actor_r = base_actor_r
        else:
            candidate_actor_q = None
            candidate_actor_r = None
        if vp_cells and (candidate_actor_q is None or candidate_actor_r is None):
            candidate_actor = unit_pos_index.get(str(candidate_unit_id or ""), None)
            if candidate_actor is not None:
                candidate_actor_q, candidate_actor_r = candidate_actor
        vp_dist_before = None
        if candidate_actor_q is not None and candidate_actor_r is not None and vp_cells:
            vp_dist_before = min(axial_distance(candidate_actor_q, candidate_actor_r, vp_q, vp_r) for vp_q, vp_r, _ in vp_cells)
        prior = 0.0
        if isinstance(priors_by_action, dict):
            raw_prior = priors_by_action.get(action_id, None)
            if raw_prior is not None:
                try:
                    prior = float(raw_prior)
                except Exception:
                    prior = 0.0
        q_est = 0.0
        if isinstance(values_by_action, dict):
            raw_q = values_by_action.get(action_id, None)
            if raw_q is not None:
                try:
                    q_est = float(raw_q)
                except Exception:
                    q_est = 0.0
        if isinstance(value_sign_by_action, dict):
            sgn = int(value_sign_by_action.get(action_id, 1))
            if sgn < 0:
                q_est *= -1.0
        q_est = _rescale_q_for_explain(float(q_est))
        q_est, _ = _clip_q_guardrail(q_est, q_clip_abs)
        visits = int(max(0, visits_by_action.get(action_id, 0)))
        u = float(c_puct) * float(prior) * (float(root_sqrt) / float(1 + visits))
        final_score = float(q_est) + float(u)
        vp_progress_delta = 0.0
        vp_progress_source = "unknown"
        vp_target_id = ""
        vp_target_source = "missing"
        vp_distance_after = None
        vp_distance_source = "missing"
        best_vp_q, best_vp_r = _best_enemy_vp_qr_for_side(
            side=str(active_side or ""),
            vp_hexes=list(vp_hexes or []),
            vp_owner_by_hex=dict(vp_owner_by_hex or {}),
            best_vp_id=str(objective_best_vp_id or ""),
        )
        legal_capture_options = 0
        for la in legal_action_ids:
            kind_la = str(_parse_action_id(str(la))[0] or "").strip().upper()
            if "CAPTURE" in kind_la:
                legal_capture_options += 1
                continue
            th = parse_action_target_hex(str(la))
            if th is None:
                continue
            owner = normalize_side_key(owners_by_qr.get((int(th[0]), int(th[1])), ""))
            if owner and owner != side_norm:
                legal_capture_options += 1
        fallback_progress = None
        if vp_dist_before is not None:
            fallback_progress = 0.0
        vp_progress_delta, vp_progress_source = _candidate_vp_progress_delta(
            action_id=str(action_id),
            acting_q=candidate_actor_q,
            acting_r=candidate_actor_r,
            best_vp_q=best_vp_q,
            best_vp_r=best_vp_r,
            fallback_progress_delta=fallback_progress,
            legal_capture_options=int(legal_capture_options),
        )
        if not vp_cells_all:
            vp_progress_source = "unavailable_no_vp_context"
        candidate_vp_owner = dict(vp_owner_by_hex or {})
        kind_now = str(_parse_action_id(str(action_id))[0] or "").strip().upper()
        if "CAPTURE" in kind_now:
            tq_cap, tr_cap = parse_action_target_hex(str(action_id)) or (None, None)
            if isinstance(tq_cap, int) and isinstance(tr_cap, int):
                candidate_vp_owner[f"{int(tq_cap)},{int(tr_cap)}"] = str(active_side or "")
        vp_target_id, vp_distance_after, vp_distance_source = _candidate_vp_target_after(
            action_id=str(action_id),
            side=str(active_side or ""),
            vp_hexes=list(vp_hexes or []),
            vp_owner_by_hex=dict(candidate_vp_owner),
            acting_q=candidate_actor_q,
            acting_r=candidate_actor_r,
        )
        vp_target_source = "vp_target_after"
        candidates.append(
            _normalize_vp_candidate(
                {
                    "action_id": action_id,
                    "policy_prior": float(prior),
                    "q_estimate": float(q_est),
                    "reward_estimate": float(dynamics_pred_reward) if dynamics_pred_reward is not None and action_id == str(chosen_action or "") else None,
                    "exploration_bonus_u": float(u),
                    "final_score": float(final_score),
                    "vp_progress_delta": vp_progress_delta,
                    "vp_progress_source": str(vp_progress_source),
                    "vp_target_id": str(vp_target_id),
                    "vp_target_source": str(vp_target_source),
                    "vp_distance_after": vp_distance_after,
                    "vp_distance_source": str(vp_distance_source),
                    "visit_count": int(visits),
                    "real_decision_score": float(final_score),
                    "mcts_q_value": float(q_est),
                    "mcts_u_value": float(u),
                    "mcts_success_prob_proxy": None,
                    "mcts_success_component": None,
                    "mcts_puct_score": float(final_score),
                    "selected_by": "mcts_puct",
                    "decision_criterion": "mcts_puct",
                    "decision_components": {
                        "visit_count": int(visits),
                        "q_value": float(q_est),
                        "u_value": float(u),
                        "success_prob_proxy": None,
                        "success_component": None,
                        "puct_score": float(final_score),
                        "policy_prior": float(prior),
                        "tie_break_term": float(vp_progress_delta),
                        "tie_break_source": str(vp_progress_source),
                    },
                }
            )
        )
    ranked = sorted(candidates, key=lambda c: float(c.get("final_score", float("-inf"))), reverse=True)
    k = int(top_k or 0)
    ranked_top = ranked if k <= 0 else ranked[: max(1, k)]
    chosen = next((c for c in candidates if str(c.get("action_id", "")) == str(chosen_action or "")), None)
    if chosen is not None and not any(str(c.get("action_id", "")) == str(chosen.get("action_id", "")) for c in ranked_top):
        if ranked_top:
            ranked_top[-1] = dict(chosen)
        else:
            ranked_top.append(dict(chosen))
    vp_best = select_vp_best_action(
        candidates=candidates,
        chosen_action=str(chosen_action or ""),
        objective_best_vp_id=str(objective_best_vp_id or ""),
    )
    if not vp_best:
        vp_best = None
    delta_score = None
    if chosen is not None and vp_best is not None:
        delta_score = float(chosen.get("final_score", 0.0)) - float(vp_best.get("final_score", 0.0))
    component_deltas: List[tuple[str, float]] = []
    if chosen is not None and vp_best is not None:
        component_deltas = [
            ("Q", abs(float(chosen.get("q_estimate", 0.0)) - float(vp_best.get("q_estimate", 0.0)))),
            ("U", abs(float(chosen.get("exploration_bonus_u", 0.0)) - float(vp_best.get("exploration_bonus_u", 0.0)))),
            ("prior", abs(float(chosen.get("policy_prior", 0.0)) - float(vp_best.get("policy_prior", 0.0)))),
            ("vp_progress", abs(float(chosen.get("vp_progress_delta", 0.0) or 0.0) - float(vp_best.get("vp_progress_delta", 0.0) or 0.0))),
        ]
    component_priority = [name for name, value in sorted(component_deltas, key=lambda x: x[1], reverse=True) if value > 1e-9]
    explanation = "N/A (missing VP candidate telemetry)"
    if chosen is not None and vp_best is not None:
        chosen_id = str(chosen.get("action_id", ""))
        vp_id = str(vp_best.get("action_id", ""))
        if chosen_id == vp_id:
            explanation = "selected action is also best toward VP"
        else:
            q_gap = float(chosen.get("q_estimate", 0.0)) - float(vp_best.get("q_estimate", 0.0))
            u_gap = float(chosen.get("exploration_bonus_u", 0.0)) - float(vp_best.get("exploration_bonus_u", 0.0))
            vp_gap = float(chosen.get("vp_progress_delta", 0.0) or 0.0) - float(vp_best.get("vp_progress_delta", 0.0) or 0.0)
            if q_gap > 0.0 and vp_gap < 0.0:
                explanation = "won by higher Q despite worse VP progress"
            elif u_gap > 0.0 and vp_gap < 0.0:
                explanation = "won by exploration bonus despite worse VP progress"
            elif vp_gap >= 0.0 and (delta_score or 0.0) >= 0.0:
                explanation = "won while matching or improving VP progress"
            else:
                explanation = "won by combined PUCT score over VP-oriented alternative"
    ranked_top = canonicalize_decision_candidates(
        ranked_top,
        chosen_action_id=str(chosen_action or ""),
        default_policy_prior_zero=True,
    )
    return {
        "top_k": int(max(0, int(top_k or 0))),
        "chosen_action_id": str(chosen_action or ""),
        "vp_best_action_id": str((vp_best or {}).get("action_id", "")),
        "delta_score": delta_score,
        "score_components_priority": component_priority[:3],
        "explanation": str(explanation),
        "candidate_actions": ranked_top,
    }


def backfill_why_action_vs_vp_from_observed_transition(
    *,
    why_action_vs_vp: Dict[str, object],
    chosen_action: str,
    objective_progress_delta: Optional[float],
    objective_best_vp_id: str = "",
    legal_actions: Optional[List[str]] = None,
) -> Dict[str, object]:
    out = dict(why_action_vs_vp or {})
    candidates = [dict(c or {}) for c in list(out.get("candidate_actions", []) or [])]
    chosen_action = str(chosen_action or "")
    chosen_kind = action_kind_from_id(chosen_action)
    chosen_parts = chosen_action.split(":")
    chosen_actor_id = chosen_parts[1] if len(chosen_parts) > 1 else ""
    legal_actions = [str(a or "") for a in list(legal_actions or [])]
    legal_move_actions = [
        a
        for a in legal_actions
        if action_kind_from_id(a) == "MOVE"
        and (a.split(":")[1] if len(a.split(":")) > 1 else "") == chosen_actor_id
    ]
    if not candidates and legal_move_actions:
        candidates = [
            {
                "action_id": str(a),
                "policy_prior": 0.0,
                "q_estimate": 0.0,
                "reward_estimate": None,
                "exploration_bonus_u": 0.0,
                "final_score": 0.0,
                "vp_progress_delta": 0.0,
                "vp_progress_source": "state_fallback",
                "vp_target_id": "",
                "vp_target_source": "missing",
                "vp_distance_after": None,
                "vp_distance_source": "missing",
                "visit_count": 0,
                "real_decision_score": 0.0,
                "mcts_q_value": 0.0,
                "mcts_u_value": 0.0,
                "mcts_success_prob_proxy": None,
                "mcts_success_component": None,
                "mcts_puct_score": 0.0,
                "selected_by": "mcts_puct",
                "decision_criterion": "mcts_puct",
                "decision_components": {
                    "visit_count": 0,
                    "q_value": 0.0,
                    "u_value": 0.0,
                    "success_prob_proxy": None,
                    "success_component": None,
                    "puct_score": 0.0,
                    "policy_prior": 0.0,
                    "tie_break_term": 0.0,
                    "tie_break_source": "state_fallback",
                },
            }
            for a in legal_move_actions
        ]
    if not candidates:
        return out
    observed_delta = None
    if objective_progress_delta is not None:
        try:
            observed_delta = float(objective_progress_delta)
        except Exception:
            observed_delta = None
    for c in candidates:
        aid = str(c.get("action_id", "") or "")
        kind = action_kind_from_id(aid)
        src_text = str(c.get("vp_progress_source", "") or "").strip().lower()
        vp_delta_missing = c.get("vp_progress_delta", None) is None
        vp_delta_unknownish = src_text in {"", "unknown"}
        if c.get("vp_progress_delta", None) is None and is_stationary_action_kind(kind):
            c["vp_progress_delta"] = 0.0
            c["vp_progress_source"] = str(c.get("vp_progress_source", "") or "state_fallback")
        if aid == chosen_action and observed_delta is not None and (vp_delta_missing or vp_delta_unknownish or src_text == "state_fallback"):
            c["vp_progress_delta"] = float(observed_delta)
            c["vp_progress_source"] = str(c.get("vp_progress_source", "") or "state_fallback")
        if c.get("vp_progress_delta", None) is not None:
            try:
                c["vp_progress_delta"] = float(c.get("vp_progress_delta"))
            except Exception:
                c["vp_progress_delta"] = None
        c["vp_progress_source"] = str(c.get("vp_progress_source", "") or "unknown")
    out["candidate_actions"] = canonicalize_decision_candidates(
        candidates,
        chosen_action_id=str(chosen_action),
        default_policy_prior_zero=False,
    )
    chosen = next((c for c in candidates if str(c.get("action_id", "")) == chosen_action), None)
    vp_best = select_vp_best_action(
        candidates=candidates,
        chosen_action=chosen_action,
        objective_best_vp_id=str(objective_best_vp_id or ""),
    )
    if not vp_best and action_kind_from_id(chosen_action) == "MOVE" and legal_move_actions:
        fallback_id = chosen_action if chosen_action in legal_move_actions else sorted(legal_move_actions)[0]
        vp_best = next(
            (c for c in candidates if str(c.get("action_id", "")) == str(fallback_id)),
            {"action_id": str(fallback_id), "final_score": 0.0},
        )
    if not vp_best:
        vp_best = None
    out["vp_best_action_id"] = str((vp_best or {}).get("action_id", ""))
    out["delta_score"] = (
        float(chosen.get("final_score", 0.0)) - float(vp_best.get("final_score", 0.0))
        if chosen is not None and vp_best is not None
        else None
    )
    if chosen is not None and vp_best is not None:
        if str(chosen.get("action_id", "")) == str(vp_best.get("action_id", "")):
            out["explanation"] = "selected action is also best toward VP"
        else:
            out["explanation"] = str(
                out.get("explanation", "") or "won by combined PUCT score over VP-oriented alternative"
            )
    elif chosen is not None and chosen.get("vp_progress_delta", None) is not None:
        out["explanation"] = "selected action telemetry includes observed VP progress"
    elif chosen_kind == "MOVE" and str(out.get("vp_best_action_id", "")).strip():
        out["explanation"] = str(
            out.get("explanation", "") or "selected fallback VP-best MOVE from legal acting-unit actions"
        )
    return out
