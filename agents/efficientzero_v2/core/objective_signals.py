from __future__ import annotations

from dataclasses import dataclass


def normalize_side_label(side: str) -> str:
    return str(side or "").strip().upper()


def hex_distance_axial(aq: int, ar: int, bq: int, br: int) -> int:
    dq = int(aq) - int(bq)
    dr = int(ar) - int(br)
    return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)


@dataclass(frozen=True)
class ObjectiveSignal:
    vp_distance_vector: dict[str, float]
    objective_min_dist: float
    objective_best_vp_id: str
    objective_had_opportunity: int
    objective_converted: int
    objective_progress_delta: float
    objective_min_dist_before: float
    objective_min_dist_after: float


def objective_min_distance_snapshot(
    *,
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> tuple[float, str, dict[str, float]]:
    side_norm = normalize_side_label(side)
    if not side_norm:
        return -1.0, "", {}
    alive_units = [
        u
        for u in list(units or [])
        if isinstance(u, dict)
        and normalize_side_label(u.get("side", "")) == side_norm
        and bool(u.get("alive", True))
        and isinstance(u.get("q"), int)
        and isinstance(u.get("r"), int)
    ]
    if not alive_units:
        return -1.0, "", {}
    owners = dict(vp_owner_by_hex or {})
    best = -1.0
    best_id = ""
    by_vp: dict[str, float] = {}
    for idx, vp in enumerate(list(vp_hexes or [])):
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        key = f"{int(q)},{int(r)}"
        if normalize_side_label(owners.get(key, "")) == side_norm:
            continue
        dmin = min(hex_distance_axial(int(u["q"]), int(u["r"]), int(q), int(r)) for u in alive_units)
        vp_id = str(vp.get("vp_id", "")).strip() or f"VP_{idx}_{key}"
        by_vp[vp_id] = float(dmin)
        if best < 0.0 or dmin < best:
            best = float(dmin)
            best_id = vp_id
    return float(best), str(best_id), by_vp


def objective_step_signal(
    *,
    side: str,
    vp_hexes: list[dict],
    legal_actions: list[str],
    before_units: list[dict],
    before_vp_owner_by_hex: dict[str, str],
    after_units: list[dict],
    after_vp_owner_by_hex: dict[str, str],
    legal_capture_options: int,
    capture_taken: bool,
    vp_captures: int,
    vp_gain_for_side: int,
    opportunity_near_vp_max_dist: float = 2.0,
) -> ObjectiveSignal:
    before_min, best_vp_id, before_vec = objective_min_distance_snapshot(
        units=before_units,
        side=side,
        vp_hexes=vp_hexes,
        vp_owner_by_hex=before_vp_owner_by_hex,
    )
    after_min, _, _ = objective_min_distance_snapshot(
        units=after_units,
        side=side,
        vp_hexes=vp_hexes,
        vp_owner_by_hex=after_vp_owner_by_hex,
    )
    progress_delta = float(before_min - after_min) if before_min >= 0.0 and after_min >= 0.0 else 0.0
    near = float(max(0.0, opportunity_near_vp_max_dist))
    had_opportunity = int(
        int(legal_capture_options) > 0
        or bool(capture_taken)
        or int(vp_gain_for_side) > 0
        or (before_min >= 0.0 and before_min <= near)
        or (after_min >= 0.0 and after_min <= near)
    )
    converted = int(bool(capture_taken) or int(vp_captures) > 0 or int(vp_gain_for_side) > 0)
    return ObjectiveSignal(
        vp_distance_vector=dict(before_vec),
        objective_min_dist=float(before_min),
        objective_best_vp_id=str(best_vp_id),
        objective_had_opportunity=int(had_opportunity),
        objective_converted=int(converted),
        objective_progress_delta=float(progress_delta),
        objective_min_dist_before=float(before_min),
        objective_min_dist_after=float(after_min),
    )

