from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from agents.efficientzero_v2.core.selfplay import (
    _global_strategy_soft_signal as ezv2_global_strategy_soft_signal,
)
from assault_bench.telemetry_models import UnitSnapshotIndex, VPOwnershipSnapshot


def build_post_unit_snapshots(
    post_units: List[object],
    runtime_events: List[Dict[str, object]],
    suppressed_from_events_fn,
) -> tuple[List[Dict[str, object]], Dict[str, float], Dict[str, bool], Dict[str, bool]]:
    index = UnitSnapshotIndex.from_units(list(post_units or []))
    unit_positions_snapshot = list(index.positions)
    unit_hp_snapshot = dict(index.hp_by_id)
    unit_alive_snapshot = dict(index.alive_by_id)
    unit_suppressed_snapshot = dict(index.suppressed_by_id)
    unit_suppressed_snapshot.update(
        suppressed_from_events_fn(list(runtime_events or []))
    )
    return (
        unit_positions_snapshot,
        unit_hp_snapshot,
        unit_alive_snapshot,
        unit_suppressed_snapshot,
    )


def resolve_global_strategy_component(
    *,
    active_side: str,
    action_kind: str,
    reward_shaping: Dict[str, object],
    before_vp_owner: Dict[str, str],
    after_vp_owner: Dict[str, str],
    obs_vp_hexes: List[object],
    obs_units: List[object],
    post_obs_units: List[object],
    vp_captures_eval: int,
    source_value_from_transition: Optional[float],
    sustained_advantage_turns_by_side: Dict[str, int],
    pending_setup_strength_by_side: Dict[str, float],
    normalize_side_key_fn,
    units_snapshot_fn,
) -> Tuple[Optional[float], str, Dict[str, int], Dict[str, float]]:
    if source_value_from_transition is not None:
        return (
            float(source_value_from_transition),
            "transition_info",
            dict(sustained_advantage_turns_by_side),
            dict(pending_setup_strength_by_side),
        )
    side_norm = normalize_side_key_fn(str(active_side))
    previous_setup_strength = float(pending_setup_strength_by_side.get(side_norm, 0.0))
    before_snapshot = VPOwnershipSnapshot.from_owner_map(dict(before_vp_owner or {}))
    after_snapshot = VPOwnershipSnapshot.from_owner_map(dict(after_vp_owner or {}))
    _, _ = before_snapshot.counts_for_side(side_norm)
    after_counts_friendly, after_counts_enemy = after_snapshot.counts_for_side(side_norm)
    vp_advantage = int(after_counts_friendly - after_counts_enemy)
    prev_sustain = int(sustained_advantage_turns_by_side.get(side_norm, 0))
    sustained_turns = prev_sustain + 1 if side_norm and vp_advantage > 0 else 0
    sustained_advantage_turns_by_side[side_norm] = int(sustained_turns)
    units_before_snapshot = units_snapshot_fn(obs_units)
    units_after_snapshot = units_snapshot_fn(post_obs_units)
    computed_value, meta = ezv2_global_strategy_soft_signal(
        side=str(side_norm),
        action_kind=str(action_kind),
        before_units=list(units_before_snapshot),
        after_units=list(units_after_snapshot),
        before_vp_owner_by_hex=dict(before_vp_owner or {}),
        after_vp_owner_by_hex=dict(after_vp_owner or {}),
        vp_hexes=list(obs_vp_hexes or []),
        reward_shaping=dict(reward_shaping or {}),
        sustained_advantage_turns=int(sustained_turns),
        previous_setup_strength=float(previous_setup_strength),
        vp_captures=int(vp_captures_eval),
    )
    pending_setup_strength_by_side[side_norm] = float(
        meta.get("next_setup_strength", 0.0) or 0.0
    )
    return (
        float(computed_value),
        "computed_ezv2_global_strategy_soft_signal",
        dict(sustained_advantage_turns_by_side),
        dict(pending_setup_strength_by_side),
    )
