from __future__ import annotations

from dataclasses import dataclass


def normalize_side_label(side: str) -> str:
    return str(side or "").strip().upper()


def hex_distance_axial(aq: int, ar: int, bq: int, br: int) -> int:
    dq = int(aq) - int(bq)
    dr = int(ar) - int(br)
    return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)


def parse_hex_key_to_qr(key: str) -> tuple[int | None, int | None]:
    try:
        s = str(key or "").strip()
        if not s:
            return None, None
        if "," in s:
            q_s, r_s = s.split(",", 1)
            return int(q_s), int(r_s)
        if ":" in s:
            q_s, r_s = s.split(":", 1)
            return int(q_s), int(r_s)
    except Exception:
        return None, None
    return None, None


def extract_vp_qr(vp: dict) -> tuple[int | None, int | None]:
    if not isinstance(vp, dict):
        return None, None
    q = vp.get("q")
    r = vp.get("r")
    if isinstance(q, int) and isinstance(r, int):
        return int(q), int(r)
    q2, r2 = parse_hex_key_to_qr(vp.get("hex_key", ""))
    if q2 is not None and r2 is not None:
        return q2, r2
    return None, None


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


def _enemy_vp_candidates(
    side_norm: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> list[tuple[str, int, int]]:
    owners = dict(vp_owner_by_hex or {})
    candidates: list[tuple[str, int, int]] = []
    by_owner_map = []
    for key in owners.keys():
        q, r = parse_hex_key_to_qr(key)
        if q is None or r is None:
            continue
        by_owner_map.append({"q": int(q), "r": int(r), "hex_key": str(key)})
    if by_owner_map:
        src = by_owner_map
    else:
        src = list(vp_hexes or [])
    for idx, vp in enumerate(src):
        q, r = extract_vp_qr(vp)
        if q is None or r is None:
            continue
        key = f"{int(q)},{int(r)}"
        owner = normalize_side_label(owners.get(key, ""))
        if owner == side_norm:
            continue
        vp_id = str((vp or {}).get("vp_id", "")).strip() or f"VP_{idx}_{key}"
        candidates.append((vp_id, int(q), int(r)))
    return candidates


def _alive_units_for_side(units: list[dict], side_norm: str) -> list[dict]:
    out: list[dict] = []
    for u in list(units or []):
        if not isinstance(u, dict):
            continue
        if normalize_side_label(u.get("side", "")) != side_norm:
            continue
        if not bool(u.get("alive", True)):
            continue
        q = u.get("q")
        r = u.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        out.append(u)
    return out


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
    vp_candidates = _enemy_vp_candidates(side_norm, vp_hexes, vp_owner_by_hex)
    if not vp_candidates:
        return -1.0, "", {}
    alive_units = _alive_units_for_side(units, side_norm)
    if not alive_units:
        return -1.0, "", {}
    best_by_vp: dict[str, float] = {}
    global_best = -1.0
    best_vp_id = ""
    for vp_id, vq, vr in vp_candidates:
        dmin = None
        for u in alive_units:
            d = float(hex_distance_axial(int(u.get("q")), int(u.get("r")), int(vq), int(vr)))
            if dmin is None or d < dmin:
                dmin = d
        if dmin is None:
            continue
        best_by_vp[str(vp_id)] = float(dmin)
        if global_best < 0.0 or dmin < global_best:
            global_best = float(dmin)
            best_vp_id = str(vp_id)
    return float(global_best), str(best_vp_id), dict(best_by_vp)


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
    progress_delta = 0.0
    if before_min >= 0.0 and after_min >= 0.0:
        progress_delta = float(before_min - after_min)
    near_vp_window = float(max(0.0, float(opportunity_near_vp_max_dist)))
    had_opportunity = int(
        int(legal_capture_options) > 0
        or bool(capture_taken)
        or (before_min >= 0.0 and progress_delta > 0.0)
        or (before_min >= 0.0 and before_min <= near_vp_window)
        or (after_min >= 0.0 and after_min <= near_vp_window)
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
