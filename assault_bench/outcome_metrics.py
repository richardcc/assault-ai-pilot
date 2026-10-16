from __future__ import annotations

from typing import Dict, List

from assault_bench.transform_ops import to_dict_rows


def outcome_bucket_from_class(outcome_class: str) -> str:
    cls = str(outcome_class or "").strip().lower()
    if cls in {"total_victory", "victory"}:
        return "win"
    if cls == "draw":
        return "draw"
    if cls in {"defeat", "total_defeat"}:
        return "loss"
    return "unknown"


def normalize_outcome_score(raw: object) -> int | None:
    try:
        score = int(raw)
    except Exception:
        return None
    if score > 0:
        return 1
    if score < 0:
        return -1
    return 0


def outcome_bucket_from_score(score: int | None) -> str:
    if score is None:
        return "unknown"
    if int(score) > 0:
        return "win"
    if int(score) < 0:
        return "loss"
    return "draw"


def compute_seed_side_outcome_metrics(
    trace_rows: List[Dict[str, object]],
) -> Dict[str, Dict[str, float]]:
    rows = to_dict_rows(trace_rows)
    if not rows:
        return {}
    damage_dealt_by_side: Dict[str, float] = {}
    enemy_units_eliminated_by_side: Dict[str, float] = {}
    alive_peak_by_side: Dict[str, float] = {}
    alive_final_by_side: Dict[str, float] = {}
    for row in rows:
        side = str(row.get("unit_side", "") or "").strip().upper()
        if side:
            try:
                dmg = float(row.get("damage_dealt", 0.0) or 0.0)
            except Exception:
                dmg = 0.0
            try:
                kills = float(row.get("kills_dealt", 0.0) or 0.0)
            except Exception:
                kills = 0.0
            damage_dealt_by_side[side] = damage_dealt_by_side.get(side, 0.0) + max(0.0, dmg)
            enemy_units_eliminated_by_side[side] = enemy_units_eliminated_by_side.get(side, 0.0) + max(0.0, kills)
        alive_map = dict(row.get("unit_alive_map", {}) or {})
        alive_counts: Dict[str, int] = {}
        sides_seen_this_row: set[str] = set()
        for unit_id, alive_val in alive_map.items():
            side_key = str(unit_id or "").split("_", 1)[0].strip().upper()
            if not side_key:
                continue
            sides_seen_this_row.add(side_key)
            if bool(alive_val):
                alive_counts[side_key] = alive_counts.get(side_key, 0) + 1
        for side_key in sides_seen_this_row:
            # Final alive must be updated even when a side has zero alive at this step.
            c = int(alive_counts.get(side_key, 0) or 0)
            s = str(side_key)
            alive_peak_by_side[s] = max(float(alive_peak_by_side.get(s, 0.0)), float(c))
            alive_final_by_side[s] = float(c)
    out: Dict[str, Dict[str, float]] = {}
    all_sides = (
        set(alive_peak_by_side.keys())
        | set(alive_final_by_side.keys())
        | set(damage_dealt_by_side.keys())
        | set(enemy_units_eliminated_by_side.keys())
    )
    for side in sorted(all_sides):
        peak = float(alive_peak_by_side.get(side, 0.0))
        fin = float(alive_final_by_side.get(side, 0.0))
        lost = max(0.0, peak - fin)
        out[side] = {
            "units_alive_final": fin,
            "units_lost": lost,
            "enemy_units_eliminated": float(enemy_units_eliminated_by_side.get(side, 0.0)),
            "damage_dealt": float(damage_dealt_by_side.get(side, 0.0)),
        }
    return out
