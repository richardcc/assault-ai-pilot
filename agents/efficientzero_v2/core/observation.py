from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

from agents.efficientzero_v2.core.objective_signals import objective_min_distance_snapshot

DEFAULT_OBS_CHANNELS = 38
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


DOCTRINE_ROLE_CODES: dict[str, float] = {
    "SPEARHEAD": 1.0,
    "FIRE_SUPPORT": 0.75,
    "RECON": 0.50,
    "SCREEN": 0.25,
    "COMMAND": 0.10,
}


def encode_doctrine_role(role_name: str | None) -> float:
    if not role_name:
        return DOCTRINE_ROLE_CODES["SCREEN"]
    return DOCTRINE_ROLE_CODES.get(str(role_name).strip().upper(), DOCTRINE_ROLE_CODES["SCREEN"])


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
            if isinstance(target_ranges, dict):
                for rk, rv in target_ranges.items():
                    if isinstance(rv, dict) and "dice" in rv:
                        max_direct_range = max(max_direct_range, float(_range_high(rk)))
                        direct_power = max(direct_power, _dice_power(rv.get("dice", [])))
        for rk, rv in indirect.items():
            if isinstance(rv, dict) and "dice" in rv:
                max_indirect_range = max(max_indirect_range, float(_range_high(rk)))
                indirect_power = max(indirect_power, _dice_power(rv.get("dice", [])))
            elif isinstance(rv, dict):
                for sub_rk, sub_rv in rv.items():
                    if isinstance(sub_rv, dict) and "dice" in sub_rv:
                        max_indirect_range = max(max_indirect_range, float(_range_high(sub_rk)))
                        indirect_power = max(indirect_power, _dice_power(sub_rv.get("dice", [])))
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

        doc_prof = dict(payload.get("doctrine_profile", {}) or {})
        default_role = str(doc_prof.get("default_role", "SCREEN")).upper()
        rng = doc_prof.get("optimal_engagement_range", [1, 4])
        opt_min = float(rng[0]) if isinstance(rng, (list, tuple)) and len(rng) >= 1 else 1.0
        opt_max = float(rng[1]) if isinstance(rng, (list, tuple)) and len(rng) >= 2 else 4.0
        cohesion = float(doc_prof.get("cohesion_weight", 1.0))
        fallback_hp = float(doc_prof.get("fallback_threshold_hp", 1))

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
            "default_role": default_role,
            "optimal_range_min": opt_min,
            "optimal_range_max": opt_max,
            "cohesion_weight": cohesion,
            "fallback_threshold_hp": fallback_hp,
        }
        for k, v in f.items():
            if isinstance(v, (int, float)):
                max_vals[k] = max(max_vals.get(k, 1.0), float(v))
        table[str(unit_key)] = f
    return {"table": table, "max": max_vals}


def observation_to_tensor(
    obs,
    channels: int = DEFAULT_OBS_CHANNELS,
    height: int = DEFAULT_OBS_HEIGHT,
    width: int = DEFAULT_OBS_WIDTH,
) -> torch.Tensor:
    grid = np.zeros((channels, height, width), dtype=np.float32)
    half_h = height // 2
    half_w = width // 2
    to_play = str(obs.to_play) if obs.to_play is not None else ""
    
    # 1. Bounds and coordinate mapping
    playable_hexes = getattr(obs, "playable_hexes", []) or []
    vp_list = getattr(obs, "vp_hexes", []) or []
    bounds = getattr(obs, "_coord_bounds", None)
    if bounds is not None:
        min_q, max_q, min_r, max_r = bounds
    else:
        coords_list = []
        for unit in (getattr(obs, "units", []) or []):
            q, r = unit.get("q"), unit.get("r")
            if isinstance(q, int) and isinstance(r, int):
                coords_list.append((q, r))
        for hx in playable_hexes:
            q, r = hx.get("q"), hx.get("r")
            if isinstance(q, int) and isinstance(r, int):
                coords_list.append((q, r))
        for vp in vp_list:
            q, r = vp.get("q"), vp.get("r")
            if isinstance(q, int) and isinstance(r, int):
                coords_list.append((q, r))
                
        if coords_list:
            coords_arr = np.array(coords_list, dtype=np.int32)
            min_q, min_r = coords_arr.min(axis=0)
            max_q, max_r = coords_arr.max(axis=0)
        else:
            min_q, max_q = -half_w, half_w
            min_r, max_r = -half_h, half_h
        
    q_span = max(0, max_q - min_q)
    r_span = max(0, max_r - min_r)
    max_q_norm = float(max(1, max(abs(min_q), abs(max_q))))
    max_r_norm = float(max(1, max(abs(min_r), abs(max_r))))

    def to_xy_single(q: int, r: int) -> tuple[int, int]:
        if q_span <= (width - 1):
            x = int(q - min_q)
        else:
            x = int(round((float(q - min_q) / float(max(1, q_span))) * float(width - 1)))
        if r_span <= (height - 1):
            y = int(r - min_r)
        else:
            y = int(round((float(r - min_r) / float(max(1, r_span))) * float(height - 1)))
        return x, y

    def _hex_dist(aq: int, ar: int, bq: int, br: int) -> int:
        dq = int(aq) - int(bq)
        dr = int(ar) - int(br)
        return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)

    unit_features = _unit_feature_table()
    feature_table = dict(unit_features.get("table", {}) or {})
    feature_max = dict(unit_features.get("max", {}) or {})

    ally_alive_coords: list[tuple[int, int]] = []
    ally_threat_sources: list[tuple[int, int, float, float]] = []
    enemy_threat_sources: list[tuple[int, int, float, float]] = []
    ally_optimal_sources: list[tuple[int, int, float, float, float, float]] = []
    enemy_optimal_sources: list[tuple[int, int, float, float, float, float]] = []

    # 2. Units
    for unit in (getattr(obs, "units", []) or []):
        q = unit.get("q")
        r = unit.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy_single(int(q), int(r))
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

        doc_role = str(unit.get("doctrine_role") or unit.get("role") or feat.get("default_role", "SCREEN")).upper()
        role_code = encode_doctrine_role(doc_role)
        opt_min = float(feat.get("optimal_range_min", 1.0))
        opt_max = float(feat.get("optimal_range_max", max(1.0, raw_direct_range)))
        if "doctrine_profile" in unit and isinstance(unit["doctrine_profile"], dict):
            u_rng = unit["doctrine_profile"].get("optimal_engagement_range")
            if isinstance(u_rng, (list, tuple)) and len(u_rng) >= 2:
                opt_min, opt_max = float(u_rng[0]), float(u_rng[1])

        if side == to_play:
            if alive:
                ally_alive_coords.append((int(q), int(r)))
                ally_threat_sources.append((int(q), int(r), max(1.0, raw_direct_range), max(0.1, attack_power_norm)))
                ally_optimal_sources.append((int(q), int(r), opt_min, opt_max, direct_range_norm, role_code))
            grid[0, y, x] = 1.0
            grid[2, y, x] = hp_norm
            crossfire = sum(
                1 for eq, er, edrange, _ in enemy_threat_sources
                if 1 <= _hex_dist(int(q), int(r), eq, er) <= edrange
            )
            crossfire_score = min(1.0, float(crossfire) / 3.0)
            if alive and suppressed:
                crossfire_score = 1.0
            grid[4, y, x] = crossfire_score
            
            if float(feat.get("is_mg", 0.0)) > 0.0:
                grid[8, y, x] = 1.0
            elif doc_role == "FIRE_SUPPORT" and alive:
                grid[8, y, x] = max(float(grid[8, y, x]), 0.75)
            if float(feat.get("is_mortar", 0.0)) > 0.0:
                grid[10, y, x] = 1.0
            grid[22, y, x] = movement_norm
            grid[24, y, x] = direct_range_norm
            grid[28, y, x] = attack_power_norm
            grid[30, y, x] = defense_power_norm
            if channels > 32:
                grid[32, y, x] = role_code
        else:
            if alive:
                enemy_threat_sources.append((int(q), int(r), max(1.0, raw_direct_range), max(0.1, attack_power_norm)))
                enemy_optimal_sources.append((int(q), int(r), opt_min, opt_max, direct_range_norm, role_code))
            grid[1, y, x] = 1.0
            grid[3, y, x] = hp_norm
            has_ally_target = any(
                1 <= _hex_dist(int(q), int(r), aq, ar) <= raw_direct_range
                for aq, ar in ally_alive_coords
            )
            engagement_score = 1.0 if has_ally_target else (1.0 if (alive and suppressed) else 0.0)
            grid[5, y, x] = engagement_score
            if float(feat.get("is_mg", 0.0)) > 0.0:
                grid[9, y, x] = 1.0
            elif doc_role == "FIRE_SUPPORT" and alive:
                grid[9, y, x] = max(float(grid[9, y, x]), 0.75)
            if float(feat.get("is_mortar", 0.0)) > 0.0:
                grid[23, y, x] = 1.0
            grid[25, y, x] = direct_range_norm
            grid[31, y, x] = defense_power_norm
            if channels > 33:
                grid[33, y, x] = role_code

    # 3. Reinforcements
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
        x, y = to_xy_single(int(q), int(r))
        if not (0 <= x < width and 0 <= y < height):
            continue
        if "arrival_prob" in reinf and reinf["arrival_prob"] is not None:
            countdown_w = max(0.1, min(1.0, float(reinf["arrival_prob"])))
        else:
            arrival_turn = int(reinf.get("turn", reinf.get("arrival_turn", turn_now + 1)) or (turn_now + 1))
            dt = max(0, arrival_turn - turn_now)
            if dt > max_turns_est:
                continue
            countdown_w = max(0.1, min(1.0, float(max_turns_est - dt) / float(max_turns_est)))

        recon_tier = float(reinf.get("recon_tier", 6) or 6)
        recon_w = max(0.25, min(1.0, recon_tier / 6.0))
        effective_w = countdown_w * recon_w

        side = str(reinf.get("side", ""))
        strength_val = 0.5 * effective_w
        if side == to_play:
            if grid[0, y, x] <= 0.0:
                grid[0, y, x] = strength_val
            grid[21, y, x] = max(float(grid[21, y, x]), 0.5 * effective_w)
        elif side:
            if grid[4, y, x] <= 0.0:
                grid[4, y, x] = strength_val
            grid[7, y, x] = max(float(grid[7, y, x]), 0.35 * effective_w)

    # 4. VPs static
    vp_owner_by_hex = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
    for vp in vp_list:
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x, y = to_xy_single(int(q), int(r))
        if not (0 <= x < width and 0 <= y < height):
            continue
        val = float(vp.get("value", vp.get("per_turn", 2.0)) or 2.0)
        v_rel = max(0.25, val / 2.0)
        grid[13, y, x] = v_rel
        owner = str(vp_owner_by_hex.get(f"{q},{r}", ""))
        if owner:
            grid[14, y, x] = v_rel if owner == to_play else -v_rel

    # 5. VECTORIZED PLAYABLE HEX MAPPING (Massive Speedup!)
    if playable_hexes:
        hex_data = []
        for hx in playable_hexes:
            q, r = hx.get("q"), hx.get("r")
            if isinstance(q, int) and isinstance(r, int):
                x, y = to_xy_single(q, r)
                if 0 <= x < width and 0 <= y < height:
                    hex_data.append((q, r, x, y, f"{q},{r}"))

        if hex_data:
            q_arr = np.array([h[0] for h in hex_data], dtype=np.int32)
            r_arr = np.array([h[1] for h in hex_data], dtype=np.int32)
            x_arr = np.array([h[2] for h in hex_data], dtype=np.int32)
            y_arr = np.array([h[3] for h in hex_data], dtype=np.int32)
            keys = [h[4] for h in hex_data]
            N_hex = len(hex_data)

            grid[12, y_arr, x_arr] = 1.0
            grid[19, y_arr, x_arr] = q_arr / max_q_norm
            grid[20, y_arr, x_arr] = r_arr / max_r_norm

            # Terrain lookups
            mc_map = getattr(obs, "terrain_move_cost_by_hex", {}) or {}
            cov_map = getattr(obs, "terrain_cover_by_hex", {}) or {}
            los_map = getattr(obs, "terrain_los_block_by_hex", {}) or {}
            fort_map = getattr(obs, "fortification_type_by_hex", {}) or {}

            cov_arr = np.array([float(cov_map.get(k, 0.0)) for k in keys], dtype=np.float32)
            los_arr = np.array([float(los_map.get(k, 0.0)) for k in keys], dtype=np.float32)
            grid[15, y_arr, x_arr] = [float(mc_map.get(k, 0.0)) for k in keys]
            grid[16, y_arr, x_arr] = cov_arr
            grid[17, y_arr, x_arr] = los_arr

            # Helper for hex distances in vector form: (N_hex, N_src)
            def _calc_dist_mat(sq_list: list[int], sr_list: list[int]) -> np.ndarray:
                sq = np.array(sq_list, dtype=np.int32)[None, :]
                sr = np.array(sr_list, dtype=np.int32)[None, :]
                dq = q_arr[:, None] - sq
                dr = r_arr[:, None] - sr
                return (np.abs(dq) + np.abs(dr) + np.abs(dq + dr)) // 2

            # Channel 18: vp_distance_field
            if vp_list:
                vp_q_list = [int(vp.get("q", 0) or 0) for vp in vp_list]
                vp_r_list = [int(vp.get("r", 0) or 0) for vp in vp_list]
                vp_vals = [max(0.25, float(vp.get("value", vp.get("per_turn", 2.0)) or 2.0) / 2.0) for vp in vp_list]
                d_vp_mat = _calc_dist_mat(vp_q_list, vp_r_list) # (N_hex, N_vp)
                v_rel_arr = np.array(vp_vals, dtype=np.float32)[None, :]
                grads_mat = v_rel_arr / (1.0 + np.maximum(0, d_vp_mat).astype(np.float32))
                best_grad = grads_mat.max(axis=1)

                urgency_ratio = min(1.0, max(0.0, float(turn_now) / float(max_turns_est)))
                not_owned_mask = np.array([str(vp_owner_by_hex.get(k, "")) != to_play for k in keys], dtype=bool)
                best_grad[not_owned_mask] *= (1.0 + 0.5 * urgency_ratio)
                grid[18, y_arr, x_arr] = best_grad

            # Ally / Enemy coordinates
            has_ally = bool(ally_alive_coords)
            has_enemy = bool(enemy_threat_sources)

            if has_ally:
                d_ally_mat = _calc_dist_mat([a[0] for a in ally_alive_coords], [a[1] for a in ally_alive_coords])
                d_ally_min = d_ally_mat.min(axis=1)
            else:
                d_ally_min = np.full(N_hex, 99, dtype=np.int32)

            if has_enemy:
                d_enemy_mat = _calc_dist_mat([e[0] for e in enemy_threat_sources], [e[1] for e in enemy_threat_sources])
                d_enemy_min = d_enemy_mat.min(axis=1)
            else:
                d_enemy_min = np.full(N_hex, 99, dtype=np.int32)

            # Channel 6: vp_contest_race
            if channels > 6:
                if has_ally and has_enemy:
                    denom = np.maximum(1.0, (d_ally_min + d_enemy_min).astype(np.float32))
                    race_val = (d_enemy_min.astype(np.float32) - d_ally_min.astype(np.float32)) / denom
                    grid[6, y_arr, x_arr] = np.clip(race_val, -1.0, 1.0)
                elif has_ally:
                    grid[6, y_arr, x_arr] = 1.0
                elif has_enemy:
                    grid[6, y_arr, x_arr] = -1.0

            # Channel 7: reaction_fire_threat
            if channels > 7 and has_enemy:
                e_drange = np.array([e[2] for e in enemy_threat_sources], dtype=np.float32)[None, :]
                e_atk = np.array([e[3] for e in enemy_threat_sources], dtype=np.float32)[None, :]
                in_range = (d_enemy_mat >= 1) & (d_enemy_mat <= e_drange)
                t_term = e_atk * (1.0 - 0.4 * cov_arr[:, None]) * (1.0 - (d_enemy_mat - 1) / np.maximum(1.0, e_drange))
                threat_mat = np.where(in_range, t_term, 0.0)
                max_threat = threat_mat.max(axis=1)
                valid_los = los_arr < 1.0
                for i in np.where(valid_los)[0]:
                    grid[7, y_arr[i], x_arr[i]] = min(1.0, max(0.0, float(max_threat[i])))

            # Channel 26: ally_fire_coverage
            if channels > 26 and has_ally:
                a_drange = np.array([a[2] for a in ally_threat_sources], dtype=np.float32)[None, :]
                a_atk = np.array([a[3] for a in ally_threat_sources], dtype=np.float32)[None, :]
                in_range_a = (d_ally_mat >= 1) & (d_ally_mat <= a_drange)
                t_term_a = a_atk * (1.0 - 0.4 * cov_arr[:, None]) * (1.0 - (d_ally_mat - 1) / np.maximum(1.0, a_drange))
                threat_mat_a = np.where(in_range_a, t_term_a, 0.0)
                max_threat_ally = threat_mat_a.max(axis=1)
                valid_los_a = los_arr < 1.0
                for i in np.where(valid_los_a)[0]:
                    grid[26, y_arr[i], x_arr[i]] = min(1.0, max(0.0, float(max_threat_ally[i])))

            # Channel 11: local_firepower_balance
            if channels > 11:
                ally_cov = grid[26, y_arr, x_arr] if channels > 26 else 0.0
                enemy_cov = grid[7, y_arr, x_arr] if channels > 7 else 0.0
                grid[11, y_arr, x_arr] = np.clip(ally_cov - enemy_cov, -1.0, 1.0)

            # Channel 21: frontline_control
            if channels > 21:
                both_valid = (d_ally_min < 99) & (d_enemy_min < 99)
                ctrl_val = np.zeros(N_hex, dtype=np.float32)
                ctrl_val[both_valid] = (d_enemy_min[both_valid] - d_ally_min[both_valid]) / np.maximum(1.0, (d_enemy_min[both_valid] + d_ally_min[both_valid])).astype(np.float32)
                ctrl_val[(d_ally_min < 99) & (~both_valid)] = 1.0
                ctrl_val[(d_enemy_min < 99) & (~both_valid)] = -1.0
                grid[21, y_arr, x_arr] = np.clip(ctrl_val, -1.0, 1.0)

            # Channel 27 & 29: Fortifications & Hazards
            if channels > 27 or channels > 29:
                for idx, k in enumerate(keys):
                    y, x = y_arr[idx], x_arr[idx]
                    cov, los = cov_arr[idx], los_arr[idx]
                    f_type = str(fort_map.get(k, "")).lower()
                    if channels > 27:
                        f_val = 0.0
                        if "bunker" in f_type or "casemate" in f_type: f_val = 1.0
                        elif "gun_emplacement" in f_type or "trench" in f_type: f_val = 0.70
                        elif cov >= 0.35 and los >= 0.50: f_val = 0.40
                        grid[27, y, x] = f_val
                    if channels > 29:
                        h_val = 0.0
                        if "mine" in f_type: h_val = 1.0
                        elif "wire" in f_type: h_val = 0.60
                        grid[29, y, x] = h_val

            # Channel 24 & 25: Optimal ranges
            if channels > 24 and ally_optimal_sources:
                opt_min_a = np.array([a[2] for a in ally_optimal_sources], dtype=np.float32)[None, :]
                opt_max_a = np.array([a[3] for a in ally_optimal_sources], dtype=np.float32)[None, :]
                d_norm_a = np.array([a[4] for a in ally_optimal_sources], dtype=np.float32)[None, :]
                in_opt_a = (d_ally_mat > 0) & (d_ally_mat >= opt_min_a) & (d_ally_mat <= opt_max_a)
                fp_a = np.where(in_opt_a, 0.5 * d_norm_a * (1.0 - 0.3 * los_arr[:, None]), 0.0)
                max_fp_a = fp_a.max(axis=1)
                for i in range(N_hex):
                    if max_fp_a[i] > grid[24, y_arr[i], x_arr[i]]:
                        grid[24, y_arr[i], x_arr[i]] = float(max_fp_a[i])

            if channels > 25 and enemy_optimal_sources:
                opt_min_e = np.array([e[2] for e in enemy_optimal_sources], dtype=np.float32)[None, :]
                opt_max_e = np.array([e[3] for e in enemy_optimal_sources], dtype=np.float32)[None, :]
                d_norm_e = np.array([e[4] for e in enemy_optimal_sources], dtype=np.float32)[None, :]
                in_opt_e = (d_enemy_mat > 0) & (d_enemy_mat >= opt_min_e) & (d_enemy_mat <= opt_max_e)
                fp_e = np.where(in_opt_e, 0.5 * d_norm_e * (1.0 - 0.3 * los_arr[:, None]), 0.0)
                max_fp_e = fp_e.max(axis=1)
                for i in range(N_hex):
                    if max_fp_e[i] > grid[25, y_arr[i], x_arr[i]]:
                        grid[25, y_arr[i], x_arr[i]] = float(max_fp_e[i])

            if channels > 34 and ally_optimal_sources:
                grid[34, y_arr, x_arr] = grid[24, y_arr, x_arr]
            if channels > 35 and enemy_optimal_sources:
                grid[35, y_arr, x_arr] = grid[25, y_arr, x_arr]

            # Channel 36: turn_urgency_pressure
            if channels > 36:
                urgency_ratio = min(1.0, max(0.0, float(turn_now) / float(max_turns_est)))
                if vp_list:
                    d_min_vp = d_vp_mat.min(axis=1)
                    vp_prox = 1.0 / (1.0 + np.maximum(0, d_min_vp).astype(np.float32))
                    base_urgency = np.minimum(1.0, urgency_ratio * (1.0 + 0.5 * vp_prox))
                else:
                    base_urgency = np.full(N_hex, urgency_ratio, dtype=np.float32)
                grid[36, y_arr, x_arr] = base_urgency

            # Channel 37: paralysis_exposure_risk
            if channels > 37:
                is_ally_here = (d_ally_min == 0) if has_ally else np.zeros(N_hex, dtype=bool)
                cov_low = cov_arr < 0.35
                p_risk = np.zeros(N_hex, dtype=np.float32)
                qualify = is_ally_here & cov_low
                if np.any(qualify) and vp_list:
                    d_min_vp_q = d_vp_mat[qualify].min(axis=1) if vp_list else np.full(qualify.sum(), 99, dtype=np.int32)
                    p_risk[qualify] = np.minimum(1.0, 0.5 + 0.5 * (1.0 - cov_arr[qualify]) * (np.minimum(d_min_vp_q, 6).astype(np.float32) / 6.0))
                grid[37, y_arr, x_arr] = p_risk

    return torch.from_numpy(grid)
