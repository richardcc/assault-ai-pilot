from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import torch

from agents.efficientzero_v2.core.objective_signals import objective_min_distance_snapshot

DEFAULT_OBS_CHANNELS = 32
DEFAULT_OBS_HEIGHT = 16
DEFAULT_OBS_WIDTH = 16

_DICE_WEIGHT = {
    "RED": 3.0,
    "YELLOW": 2.0,
    "GREEN": 1.0,
    "BLUE": 0.5,
}


def _range_high(range_key: str) -> int:
    txt = str(range_key or "").strip()
    if not txt:
        return 0
    if "-" in txt:
        try:
            return int(txt.split("-", 1)[1])
        except Exception:
            return 0
    try:
        return int(txt)
    except Exception:
        return 0


def _dice_power(dice_values: list) -> float:
    total = 0.0
    for d in list(dice_values or []):
        total += float(_DICE_WEIGHT.get(str(d).upper(), 0.0))
    return total


@lru_cache(maxsize=1)
def _unit_feature_table() -> dict:
    from assault_model.paths import UNIT_CATALOG_PATH
    raw = json.loads(UNIT_CATALOG_PATH.read_text(encoding="utf-8"))
    units = dict(raw.get("units", {}) or {})
    table: Dict[str, Dict[str, float]] = {}
    max_vals = {
        "movement": 1.0,
        "direct_range": 1.0,
        "indirect_range": 1.0,
        "attack_power": 1.0,
        "defense_power": 1.0,
        "max_strength": 4.0,
        "is_mortar": 1.0,
        "is_mg": 1.0,
        "is_assault": 1.0,
    }
    for unit_key, payload in units.items():
        movement = float(payload.get("movement", 0) or 0)
        attack = dict(payload.get("attack", {}) or {})
        direct = dict(attack.get("DIRECT_FIRE", {}) or {})
        indirect = dict(attack.get("INDIRECT_FIRE", {}) or {})
        max_direct_range = 0.0
        max_indirect_range = 0.0
        direct_power = 0.0
        indirect_power = 0.0
        for target_ranges in direct.values():
            for rk, rv in dict(target_ranges or {}).items():
                max_direct_range = max(max_direct_range, float(_range_high(rk)))
                direct_power = max(direct_power, _dice_power(dict(rv or {}).get("dice", [])))
        for target_ranges in indirect.values():
            for rk, rv in dict(target_ranges or {}).items():
                max_indirect_range = max(max_indirect_range, float(_range_high(rk)))
                indirect_power = max(indirect_power, _dice_power(dict(rv or {}).get("dice", [])))
        defense = dict(payload.get("base_defense", {}) or {})
        defense_power = 0.0
        sides = 0
        for dice in defense.values():
            sides += 1
            defense_power += _dice_power(dice)
        if sides > 0:
            defense_power /= float(sides)
        max_strength = float(payload.get("max_strength", 4) or 4)
        subtype = str(payload.get("subtype", "")).upper()
        classification = str(payload.get("classification", "")).upper()
        is_mortar = "MORTAR" in subtype or "INDIRECT_FIRE" in classification
        is_mg = "MG" in subtype or "MMG" in str(unit_key).upper() or "HMG" in str(unit_key).upper()
        is_assault = "FJ" in str(unit_key).upper() or "SNIPER" in str(unit_key).upper() or ("RIFLES" in str(unit_key).upper() and not is_mg and not is_mortar)
        attack_power = max(direct_power, indirect_power)
        f = {
            "movement": movement,
            "direct_range": max_direct_range,
            "indirect_range": max_indirect_range,
            "attack_power": attack_power,
            "defense_power": defense_power,
            "max_strength": max_strength,
            "is_mortar": 1.0 if is_mortar else 0.0,
            "is_mg": 1.0 if is_mg else 0.0,
            "is_assault": 1.0 if is_assault else 0.0,
        }
        for k, v in f.items():
            max_vals[k] = max(max_vals[k], float(v))
        table[str(unit_key)] = f
    return {"table": table, "max": max_vals}


def observation_to_tensor(
    obs,
    channels: int = DEFAULT_OBS_CHANNELS,
    height: int = DEFAULT_OBS_HEIGHT,
    width: int = DEFAULT_OBS_WIDTH,
) -> torch.Tensor:
    grid = torch.zeros(channels, height, width, dtype=torch.float32)
    half_h = height // 2
    half_w = width // 2
    to_play = str(obs.to_play) if obs.to_play is not None else ""
    all_coords: list[tuple[int, int]] = []
    for unit in (getattr(obs, "units", []) or []):
        q = unit.get("q")
        r = unit.get("r")
        if isinstance(q, int) and isinstance(r, int):
            all_coords.append((int(q), int(r)))
    for hx in (getattr(obs, "playable_hexes", []) or []):
        q = hx.get("q")
        r = hx.get("r")
        if isinstance(q, int) and isinstance(r, int):
            all_coords.append((int(q), int(r)))
    for vp in (getattr(obs, "vp_hexes", []) or []):
        q = vp.get("q")
        r = vp.get("r")
        if isinstance(q, int) and isinstance(r, int):
            all_coords.append((int(q), int(r)))
    if all_coords:
        min_q = min(q for q, _ in all_coords)
        max_q = max(q for q, _ in all_coords)
        min_r = min(r for _, r in all_coords)
        max_r = max(r for _, r in all_coords)
    else:
        min_q = -half_w
        max_q = half_w
        min_r = -half_h
        max_r = half_h
    q_span = max(0, max_q - min_q)
    r_span = max(0, max_r - min_r)
    max_q_norm = float(max(1, max(abs(min_q), abs(max_q))))
    max_r_norm = float(max(1, max(abs(min_r), abs(max_r))))

    def to_xy(q: int, r: int) -> tuple[int, int]:
        if q_span <= (width - 1):
            x = int(q - min_q)
        else:
            x = int(round((float(q - min_q) / float(max(1, q_span))) * float(width - 1)))
        if r_span <= (height - 1):
            y = int(r - min_r)
        else:
            y = int(round((float(r - min_r) / float(max(1, r_span))) * float(height - 1)))
        return x, y

    def _hex_distance(aq: int, ar: int, bq: int, br: int) -> int:
        dq = int(aq) - int(bq)
        dr = int(ar) - int(br)
        return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)

    def put(ch: int, y: int, x: int, val: float):
        if 0 <= ch < channels:
            grid[ch, y, x] = float(val)

    def _is_infantry(unit_key: str) -> bool:
        key = str(unit_key or "").upper()
        return any(k in key for k in ["RIFLES", "LMG", "SNIPER"])

    def _is_support(unit_key: str) -> bool:
        key = str(unit_key or "").upper()
        return any(k in key for k in ["MORTAR", "MMG", "BAZOOKA", "BRIXIA", "HMG"])

    unit_features = _unit_feature_table()
    feature_table = dict(unit_features.get("table", {}) or {})
    feature_max = dict(unit_features.get("max", {}) or {})

    ally_alive_coords: list[tuple[int, int]] = []
    ally_threat_sources: list[tuple[int, int, float, float]] = []
    enemy_threat_sources: list[tuple[int, int, float, float]] = []

    for unit in obs.units:
        q = unit.get("q")
        r = unit.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy(int(q), int(r))
        if not (0 <= x < width and 0 <= y < height):
            continue
        side = str(unit.get("side", ""))
        unit_key = str(unit.get("unit_key", ""))
        feat = dict(feature_table.get(unit_key, {}) or {})
        raw_direct_range = float(feat.get("direct_range", 1.0))
        raw_attack_power = float(feat.get("attack_power", 0.0))
        movement_norm = float(feat.get("movement", 0.0)) / float(max(1e-9, feature_max.get("movement", 1.0)))
        direct_range_norm = raw_direct_range / float(max(1e-9, feature_max.get("direct_range", 1.0)))
        attack_power_norm = raw_attack_power / float(max(1e-9, feature_max.get("attack_power", 1.0)))
        defense_power_norm = float(feat.get("defense_power", 0.0)) / float(max(1e-9, feature_max.get("defense_power", 1.0)))
        alive = bool(unit.get("alive", True))
        suppressed = bool(unit.get("suppressed", False) or unit.get("is_suppressed", False))
        max_str = float(feat.get("max_strength", 4.0) or 4.0)
        hp = unit.get("hp", max_str)
        hp_norm = 0.0
        if isinstance(hp, (int, float)):
            hp_norm = max(0.0, min(1.0, float(hp) / max(1.0, max_str)))
        if side == to_play:
            if alive:
                ally_alive_coords.append((int(q), int(r)))
                ally_threat_sources.append((int(q), int(r), max(1.0, raw_direct_range), max(0.1, attack_power_norm)))
            put(0, y, x, 1.0)  # ally_presence
            put(2, y, x, hp_norm)  # ally_hp_norm (normalized by actual max_strength)
            # Channel 4: ally_crossfire_risk / suppression (replaces dead ally_suppressed)
            crossfire = sum(
                1 for eq, er, edrange, _ in enemy_threat_sources
                if 1 <= _hex_distance(int(q), int(r), eq, er) <= edrange
            )
            crossfire_score = min(1.0, float(crossfire) / 3.0)
            if alive and suppressed:
                crossfire_score = 1.0
            put(4, y, x, crossfire_score)
            
            # Channel 8: ally_heavy_mg_support (HMG, MMG, MG42)
            if float(feat.get("is_mg", 0.0)) > 0.0:
                put(8, y, x, 1.0)
            # Channel 10: ally_indirect_mortar (Mortars, Indirect fire)
            if float(feat.get("is_mortar", 0.0)) > 0.0:
                put(10, y, x, 1.0)
            put(22, y, x, movement_norm)  # ally_mobility_norm
            put(24, y, x, direct_range_norm)  # ally_direct_range_norm
            put(28, y, x, attack_power_norm)  # ally_attack_power_norm
            put(30, y, x, defense_power_norm)  # ally_defense_power_norm
        else:
            if alive:
                enemy_threat_sources.append((int(q), int(r), max(1.0, raw_direct_range), max(0.1, attack_power_norm)))
            put(1, y, x, 1.0)  # enemy_presence
            put(3, y, x, hp_norm)  # enemy_hp_norm (normalized by actual max_strength)
            # Channel 5: enemy_target_engagement / suppression
            has_ally_target = any(
                1 <= _hex_distance(int(q), int(r), aq, ar) <= raw_direct_range
                for aq, ar in ally_alive_coords
            )
            engagement_score = 1.0 if has_ally_target else (1.0 if (alive and suppressed) else 0.0)
            put(5, y, x, engagement_score)
            
            # Channel 9: enemy_heavy_mg_support (HMG, MMG, MG42)
            if float(feat.get("is_mg", 0.0)) > 0.0:
                put(9, y, x, 1.0)
            # Channel 23: enemy_indirect_mortar (Mortars, Indirect fire)
            if float(feat.get("is_mortar", 0.0)) > 0.0:
                put(23, y, x, 1.0)
            put(25, y, x, direct_range_norm)  # enemy_direct_range_norm
            put(31, y, x, defense_power_norm)  # enemy_defense_power_norm

    # Palma et al. (2025, Sec. 3.2.3): Project scheduled incoming reinforcements
    # onto their entry hexes weighted by arrival countdown (T_max - dt) / T_max
    # without changing the 32-channel tensor layout.
    turn_now = int(getattr(obs, "turn", 1) or 1)
    max_turns_est = max(1, int(getattr(obs, "max_turns", 8) or 8))
    reinf_list = list(
        getattr(obs, "reinforcements", None)
        or getattr(obs, "reinforcement_schedule", None)
        or []
    )
    for reinf in reinf_list:
        if not isinstance(reinf, dict):
            continue
        pos = reinf.get("position") or reinf.get("entry_hex") or {}
        q = pos.get("q", reinf.get("q"))
        r = pos.get("r", reinf.get("r"))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy(int(q), int(r))
        if not (0 <= x < width and 0 <= y < height):
            continue
        arrival_turn = int(reinf.get("turn", reinf.get("arrival_turn", turn_now + 1)) or (turn_now + 1))
        dt = max(0, arrival_turn - turn_now)
        if dt > max_turns_est:
            continue
        countdown_w = max(0.1, min(1.0, float(max_turns_est - dt) / float(max_turns_est)))
        side = str(reinf.get("side", ""))
        strength_val = 0.5 * countdown_w
        if side == to_play:
            if grid[0, y, x] <= 0.0:
                put(0, y, x, strength_val)
            put(21, y, x, max(float(grid[21, y, x]), 0.5 * countdown_w))
        elif side:
            if grid[4, y, x] <= 0.0:
                put(4, y, x, strength_val)
            put(7, y, x, max(float(grid[7, y, x]), 0.35 * countdown_w))

    vp_owner_by_hex = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
    vp_list = list(getattr(obs, "vp_hexes", []) or [])
    for hx in getattr(obs, "playable_hexes", []) or []:
        q = hx.get("q")
        r = hx.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy(int(q), int(r))
        if 0 <= x < width and 0 <= y < height:
            put(12, y, x, 1.0)  # map_playable
    for vp in getattr(obs, "vp_hexes", []) or []:
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy(int(q), int(r))
        if not (0 <= x < width and 0 <= y < height):
            continue
        put(13, y, x, 1.0)  # vp_mask
        owner = str((getattr(obs, "vp_owner_by_hex", {}) or {}).get(f"{q},{r}", ""))
        if owner:
            put(14, y, x, 1.0 if owner == to_play else -1.0)  # vp_owner_relative
    for hx in getattr(obs, "playable_hexes", []) or []:
        q = hx.get("q")
        r = hx.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy(int(q), int(r))
        if not (0 <= x < width and 0 <= y < height):
            continue
        key = f"{q},{r}"
        put(15, y, x, float((getattr(obs, "terrain_move_cost_by_hex", {}) or {}).get(key, 0.0)))
        put(16, y, x, float((getattr(obs, "terrain_cover_by_hex", {}) or {}).get(key, 0.0)))
        put(17, y, x, float((getattr(obs, "terrain_los_block_by_hex", {}) or {}).get(key, 0.0)))
        # Channel 18: vp_distance_field (continuous radial Euclidean guidance toward nearest VP)
        if vp_list:
            d_min_vp = min((_hex_distance(int(q), int(r), int(vp.get("q", 0)), int(vp.get("r", 0))) for vp in vp_list), default=99)
            grad_val = 1.0 / float(1 + max(0, d_min_vp))
            put(18, y, x, grad_val)
        put(19, y, x, float(q) / max_q_norm)  # q_coord_norm
        put(20, y, x, float(r) / max_r_norm)  # r_coord_norm

        # Channel 6: vp_contest_race
        if channels > 6:
            if ally_alive_coords and enemy_threat_sources:
                d_ally_min = min((_hex_distance(aq, ar, int(q), int(r)) for aq, ar in ally_alive_coords), default=99)
                d_enemy_min = min((_hex_distance(eq, er, int(q), int(r)) for eq, er, _, _ in enemy_threat_sources), default=99)
                denom = max(1.0, float(d_ally_min + d_enemy_min))
                race_val = float(d_enemy_min - d_ally_min) / denom
                put(6, y, x, max(-1.0, min(1.0, race_val)))
            elif ally_alive_coords:
                put(6, y, x, 1.0)
            elif enemy_threat_sources:
                put(6, y, x, -1.0)
            else:
                put(6, y, x, 0.0)

        cov = float((getattr(obs, "terrain_cover_by_hex", {}) or {}).get(key, 0.0))
        los_blk = float((getattr(obs, "terrain_los_block_by_hex", {}) or {}).get(key, 0.0))

        # Channel 7: reaction_fire_threat
        if channels > 7 and enemy_threat_sources:
            if los_blk < 1.0:
                max_threat = 0.0
                for eq, er, edrange, eatk in enemy_threat_sources:
                    dist = _hex_distance(int(q), int(r), eq, er)
                    if 1 <= dist <= edrange:
                        t_val = eatk * (1.0 - 0.4 * cov) * (1.0 - float(dist - 1) / max(1.0, float(edrange)))
                        if t_val > max_threat:
                            max_threat = t_val
                put(7, y, x, min(1.0, max(0.0, max_threat)))

        # Channel 26: ally_fire_coverage
        if channels > 26 and ally_threat_sources:
            if los_blk < 1.0:
                max_threat_ally = 0.0
                for aq, ar, adrange, aatk in ally_threat_sources:
                    dist = _hex_distance(int(q), int(r), aq, ar)
                    if 1 <= dist <= adrange:
                        t_val = aatk * (1.0 - 0.4 * cov) * (1.0 - float(dist - 1) / max(1.0, float(adrange)))
                        if t_val > max_threat_ally:
                            max_threat_ally = t_val
                put(26, y, x, min(1.0, max(0.0, max_threat_ally)))

        # Channel 11: local_firepower_balance
        if channels > 11:
            ally_cov = grid[26, y, x] if channels > 26 else 0.0
            enemy_cov = grid[7, y, x] if channels > 7 else 0.0
            put(11, y, x, max(-1.0, min(1.0, ally_cov - enemy_cov)))

        # Channel 21: frontline_control
        if channels > 21:
            d_ally = min((_hex_distance(int(q), int(r), aq, ar) for aq, ar in ally_alive_coords), default=99)
            d_enemy = min((_hex_distance(int(q), int(r), eq, er) for eq, er, _, _ in enemy_threat_sources), default=99)
            if d_ally < 99 and d_enemy < 99:
                ctrl = float(d_enemy - d_ally) / float(max(1, d_enemy + d_ally))
            elif d_ally < 99:
                ctrl = 1.0
            elif d_enemy < 99:
                ctrl = -1.0
            else:
                ctrl = 0.0
            put(21, y, x, max(-1.0, min(1.0, ctrl)))

        # Channel 27: heavy_fortifications (Bunkers, Casemates, Trenches, Gun Emplacements)
        fort_type = str((getattr(obs, "fortification_type_by_hex", {}) or {}).get(key, "")).lower()
        if channels > 27:
            fort_val = 0.0
            if "bunker" in fort_type or "casemate" in fort_type:
                fort_val = 1.0
            elif "gun_emplacement" in fort_type or "trench" in fort_type:
                fort_val = 0.70
            elif cov >= 0.35 and los_blk >= 0.50:
                fort_val = 0.40  # defensible urban stone building
            put(27, y, x, fort_val)

        # Channel 29: hazard_mines_and_wire (Minefields = 1.0, Barbed Wire = 0.6)
        if channels > 29:
            hazard_val = 0.0
            if "mine" in fort_type:
                hazard_val = 1.0
            elif "wire" in fort_type:
                hazard_val = 0.60
            put(29, y, x, hazard_val)
    return grid
