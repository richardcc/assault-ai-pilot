from __future__ import annotations

import math
from typing import Dict, List, Optional

from assault_bench.transform_ops import to_dict_rows


def resolve_vp_horizon_selected_fields(
    *,
    selected_candidate: Dict[str, object],
    transition_info: Optional[object],
) -> tuple[Optional[float], Optional[float], Optional[float], str, bool]:
    def _get_field(obj: object, name: str, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    info_vp_horizon_steps = _get_field(transition_info, "vp_horizon_steps", None)
    info_vp_horizon_signal = _get_field(transition_info, "vp_horizon_signal", None)
    info_vp_horizon_component = _get_field(transition_info, "vp_horizon_decision_component", None)
    if info_vp_horizon_component is None:
        info_vp_horizon_component = _get_field(transition_info, "vp_horizon_component", None)

    raw_steps = selected_candidate.get("vp_horizon_steps", info_vp_horizon_steps)
    raw_signal = selected_candidate.get("vp_horizon_signal", info_vp_horizon_signal)
    raw_component = selected_candidate.get(
        "vp_horizon_decision_component",
        selected_candidate.get("vp_horizon_component", info_vp_horizon_component),
    )

    def _safe_float_or_none(value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            out = float(value)
        except Exception:
            return None
        return out if math.isfinite(out) else None

    steps = _safe_float_or_none(raw_steps)
    signal = _safe_float_or_none(raw_signal)
    component = _safe_float_or_none(raw_component)
    any_available = bool((steps is not None) or (signal is not None) or (component is not None))

    if any_available and (
        selected_candidate.get("vp_horizon_steps", None) is not None
        or selected_candidate.get("vp_horizon_signal", None) is not None
        or selected_candidate.get("vp_horizon_decision_component", None) is not None
        or selected_candidate.get("vp_horizon_component", None) is not None
    ):
        source = str(selected_candidate.get("vp_horizon_source", "") or "selected_candidate")
    elif any_available:
        source = "transition_info"
    else:
        source = "missing"

    return steps, signal, component, str(source), bool(any_available)


def candidate_unit_id(candidate_row: Dict[str, object]) -> str:
    row = dict(candidate_row or {})
    explicit = str(
        row.get("unit_id", row.get("actor_unit_id", row.get("acting_unit_id", ""))) or ""
    ).strip()
    if explicit:
        return explicit
    aid = str(row.get("action_id", "") or "").strip()
    parts = aid.split(":")
    if len(parts) > 1:
        unit_id = str(parts[1] or "").strip()
        if unit_id:
            return unit_id
    return ""


def dedupe_candidates_action_unit(
    candidate_rows: List[Dict[str, object]],
) -> tuple[List[Dict[str, object]], int]:
    rows = to_dict_rows(candidate_rows)
    if not rows:
        return [], 0
    by_key: Dict[tuple[str, str], Dict[str, object]] = {}
    collapsed = 0
    for row in rows:
        action_id = str(row.get("action_id", "") or "").strip()
        unit_id = candidate_unit_id(row)
        key = (action_id, unit_id)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = row
            continue
        collapsed += 1
        prev_selected = bool(prev.get("selected_action", False))
        row_selected = bool(row.get("selected_action", False))
        prev_visits = int(prev.get("visit_count", 0) or 0)
        row_visits = int(row.get("visit_count", 0) or 0)
        prev_score = float(prev.get("real_decision_score", prev.get("final_score", 0.0)) or 0.0)
        row_score = float(row.get("real_decision_score", row.get("final_score", 0.0)) or 0.0)
        keep_row = False
        if row_selected and not prev_selected:
            keep_row = True
        elif row_selected == prev_selected:
            if row_visits > prev_visits:
                keep_row = True
            elif row_visits == prev_visits and row_score > prev_score:
                keep_row = True
        if keep_row:
            kept = row
            other = prev
        else:
            kept = prev
            other = row
        if not kept.get("selected_action", False) and bool(other.get("selected_action", False)):
            kept["selected_action"] = True
        for k, v in other.items():
            if k in {"action_id", "unit_id", "actor_unit_id", "acting_unit_id"}:
                continue
            if kept.get(k, None) is None and v is not None:
                kept[k] = v
        by_key[key] = kept
    return list(by_key.values()), int(collapsed)


def assault_advantage_bucket(chosen_prob: float, margin: float, legal_count: int) -> str:
    score = 0
    if float(chosen_prob) >= 0.55:
        score += 1
    if float(margin) >= 0.20:
        score += 1
    if int(legal_count) >= 6:
        score += 1
    return "favorable" if score >= 2 else "unfavorable"
