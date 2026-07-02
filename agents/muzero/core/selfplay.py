from __future__ import annotations

import json
import math
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import torch

from agents.muzero.adapter_voec import MuZeroVOECAdapter
from agents.muzero.core.mcts import run_mcts_puct
from agents.muzero.core.replay import ReplaySample
from agents.muzero.core.targets import build_sample

DEFAULT_ACTION_DIM = 32
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
    catalog_path = (
        Path(__file__).resolve().parents[3]
        / "assault_sim"
        / "assets"
        / "catalogs"
        / "unit_catalog.json"
    )
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    units = dict(raw.get("units", {}) or {})
    table: Dict[str, Dict[str, float]] = {}
    max_vals = {
        "movement": 1.0,
        "direct_range": 1.0,
        "indirect_range": 1.0,
        "attack_power": 1.0,
        "defense_power": 1.0,
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
        attack_power = max(direct_power, indirect_power)
        f = {
            "movement": movement,
            "direct_range": max_direct_range,
            "indirect_range": max_indirect_range,
            "attack_power": attack_power,
            "defense_power": defense_power,
        }
        for k, v in f.items():
            max_vals[k] = max(max_vals[k], float(v))
        table[str(unit_key)] = f
    return {"table": table, "max": max_vals}


def observation_to_vector(obs) -> List[float]:
    # Compact deterministic feature vector for MVP.
    alive = sum(1 for u in obs.units if u["alive"])
    mean_hp = 0.0
    hp_values = [u["hp"] for u in obs.units if isinstance(u["hp"], (int, float))]
    if hp_values:
        mean_hp = sum(hp_values) / len(hp_values)
    return [float(obs.turn), float(alive), float(mean_hp), float(obs.done)]


def observation_to_tensor(
    obs,
    channels: int = DEFAULT_OBS_CHANNELS,
    height: int = DEFAULT_OBS_HEIGHT,
    width: int = DEFAULT_OBS_WIDTH,
):
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
        movement_norm = float(feat.get("movement", 0.0)) / float(max(1e-9, feature_max.get("movement", 1.0)))
        direct_range_norm = float(feat.get("direct_range", 0.0)) / float(max(1e-9, feature_max.get("direct_range", 1.0)))
        indirect_range_norm = float(feat.get("indirect_range", 0.0)) / float(max(1e-9, feature_max.get("indirect_range", 1.0)))
        attack_power_norm = float(feat.get("attack_power", 0.0)) / float(max(1e-9, feature_max.get("attack_power", 1.0)))
        defense_power_norm = float(feat.get("defense_power", 0.0)) / float(max(1e-9, feature_max.get("defense_power", 1.0)))
        alive = bool(unit.get("alive", True))
        hp = unit.get("hp")
        hp_norm = 0.0
        if isinstance(hp, (int, float)):
            hp_norm = max(0.0, min(1.0, float(hp) / 10.0))
        if side == to_play:
            put(0, y, x, 1.0)  # ally_presence
            put(2, y, x, hp_norm)  # ally_hp_norm
            put(4, y, x, 1.0 if alive else 0.0)  # ally_alive
            if _is_infantry(unit_key):
                put(8, y, x, 1.0)  # ally_infantry
            if _is_support(unit_key):
                put(10, y, x, 1.0)  # ally_support
            put(22, y, x, movement_norm)  # ally_mobility_norm
            put(24, y, x, direct_range_norm)  # ally_direct_range_norm
            put(26, y, x, indirect_range_norm)  # ally_indirect_range_norm
            put(28, y, x, attack_power_norm)  # ally_attack_power_norm
            put(30, y, x, defense_power_norm)  # ally_defense_power_norm
        else:
            put(1, y, x, 1.0)  # enemy_presence
            put(3, y, x, hp_norm)  # enemy_hp_norm
            put(5, y, x, 1.0 if alive else 0.0)  # enemy_alive
            if _is_infantry(unit_key):
                put(9, y, x, 1.0)  # enemy_infantry
            if _is_support(unit_key):
                put(11, y, x, 1.0)  # enemy_support
            put(23, y, x, movement_norm)  # enemy_mobility_norm
            put(25, y, x, direct_range_norm)  # enemy_direct_range_norm
            put(27, y, x, indirect_range_norm)  # enemy_indirect_range_norm
            put(29, y, x, attack_power_norm)  # enemy_attack_power_norm
            put(31, y, x, defense_power_norm)  # enemy_defense_power_norm
    if channels > 6:
        grid[6, :, :] = float(obs.turn) / 50.0  # turn_norm
    if channels > 7:
        grid[7, :, :] = 1.0 if bool(obs.done) else 0.0  # done_flag
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
        vp_list = list(getattr(obs, "vp_hexes", []) or [])
        if vp_list:
            dmin = min(
                _hex_distance(q, r, int(vp.get("q")), int(vp.get("r")))
                for vp in vp_list
                if isinstance(vp.get("q"), int) and isinstance(vp.get("r"), int)
            )
            put(18, y, x, 1.0 / float(1 + max(0, int(dmin))))  # vp_distance_inv
        put(19, y, x, float(q) / max_q_norm)  # q_coord_norm
        put(20, y, x, float(r) / max_r_norm)  # r_coord_norm
        put(21, y, x, 1.0 if (getattr(obs, "vp_owner_by_hex", {}) or {}).get(key, "") else 0.0)  # has_vp_owner
    return grid


def action_id_to_index(action_id: str, action_dim: int) -> int:
    # Stable hash-like mapping across runs/processes (no Python hash randomization).
    return sum(action_id.encode("utf-8")) % action_dim


def parse_action_id(action_id: str) -> tuple[str, str]:
    parts = str(action_id).split(":")
    kind = parts[0] if parts else ""
    unit_id = parts[1] if len(parts) > 1 else ""
    return kind, unit_id


def _infer_indirect_target_unit_id(
    action_id: str,
    before_by_unit: dict[str, dict],
    acting_side: str,
) -> str:
    s = str(action_id or "")
    marker = "RANGED_INDIRECT:"
    idx = s.find(marker)
    if idx < 0:
        return ""
    tail = s[idx + len(marker):]
    parts = tail.split(":")
    if len(parts) < 3:
        return ""
    try:
        tq = int(parts[1])
        tr = int(parts[2])
    except Exception:
        return ""
    matches = []
    for unit_id, u in (before_by_unit or {}).items():
        if not isinstance(u, dict):
            continue
        if str(u.get("side", "")) == str(acting_side):
            continue
        uq = u.get("q")
        ur = u.get("r")
        if isinstance(uq, int) and isinstance(ur, int) and int(uq) == tq and int(ur) == tr:
            matches.append(str(unit_id))
    return matches[0] if len(matches) == 1 else ""


def _is_attack_like_action_kind(kind: str) -> bool:
    k = str(kind or "").strip().upper()
    return k not in {"", "MOVE", "WAIT", "TIMEOUT", "OPPORTUNITY_SKIP"}


def _extract_action_destination_qr(action_id: str) -> tuple[int, int] | None:
    parts = str(action_id or "").split(":")
    if len(parts) < 4:
        return None
    try:
        q = int(parts[-2])
        r = int(parts[-1])
    except Exception:
        return None
    return (q, r)


def _hex_distance_axial(aq: int, ar: int, bq: int, br: int) -> int:
    dq = int(aq) - int(bq)
    dr = int(ar) - int(br)
    return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)


def _normalize_side_label(side: str) -> str:
    s = str(side or "").strip().upper()
    if "." in s:
        s = s.split(".")[-1]
    return s


def _coerce_int_or_none(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _parse_hex_key_to_qr(key) -> tuple[int | None, int | None]:
    s = str(key or "").strip()
    if not s:
        return None, None
    # Supports "q,r", "(q,r)", "[q, r]", "q r", etc.
    nums = re.findall(r"-?\d+", s)
    if len(nums) < 2:
        return None, None
    q = _coerce_int_or_none(nums[0])
    r = _coerce_int_or_none(nums[1])
    return q, r


def _extract_vp_qr(vp) -> tuple[int | None, int | None]:
    # Object with direct attrs (e.g. hex coord class)
    q = _coerce_int_or_none(getattr(vp, "q", None))
    r = _coerce_int_or_none(getattr(vp, "r", None))
    if q is not None and r is not None:
        return q, r
    if isinstance(vp, dict):
        # Most common shape: {"q": int, "r": int}
        q = _coerce_int_or_none(vp.get("q"))
        r = _coerce_int_or_none(vp.get("r"))
        if q is not None and r is not None:
            return q, r
        # Alternate shape: {"hex_coords": {...}} or {"hex_coords": [q,r]}
        hc = vp.get("hex_coords")
        if isinstance(hc, dict):
            q = _coerce_int_or_none(hc.get("q"))
            r = _coerce_int_or_none(hc.get("r"))
            if q is not None and r is not None:
                return q, r
        if isinstance(hc, (list, tuple)) and len(hc) >= 2:
            q = _coerce_int_or_none(hc[0])
            r = _coerce_int_or_none(hc[1])
            if q is not None and r is not None:
                return q, r
    # Object with nested hex_coords attr
    hc = getattr(vp, "hex_coords", None)
    if hc is not None:
        q = _coerce_int_or_none(getattr(hc, "q", None))
        r = _coerce_int_or_none(getattr(hc, "r", None))
        if q is not None and r is not None:
            return q, r
        if isinstance(hc, (list, tuple)) and len(hc) >= 2:
            q = _coerce_int_or_none(hc[0])
            r = _coerce_int_or_none(hc[1])
            if q is not None and r is not None:
                return q, r
    # Last resort: parse from string representation.
    return _parse_hex_key_to_qr(vp)


def _canonical_vp_hexes_from_sim(sim) -> list[dict]:
    state = getattr(sim, "_state", None)
    victory = getattr(state, "victory", None) if state is not None else None
    points = list(getattr(victory, "points", []) or []) if victory is not None else []
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for vp in points:
        q, r = _extract_vp_qr(vp)
        if q is None or r is None:
            continue
        key = (int(q), int(r))
        if key in seen:
            continue
        seen.add(key)
        out.append({"q": int(q), "r": int(r)})
    return out


def _count_vp_capture_options(
    legal_actions: list[str],
    to_play_side: str,
    vp_owner_by_hex: dict[str, str],
) -> int:
    side_norm = _normalize_side_label(to_play_side)
    owners = dict(vp_owner_by_hex or {})
    count = 0
    for action_id in list(legal_actions or []):
        kind, _ = parse_action_id(action_id)
        kind_u = str(kind or "").strip().upper()
        if "CAPTURE" in kind_u:
            count += 1
            continue
        dst = _extract_action_destination_qr(action_id)
        if dst is None:
            continue
        q, r = dst
        key = f"{int(q)},{int(r)}"
        if key not in owners:
            continue
        owner = _normalize_side_label(owners.get(key, ""))
        if owner != side_norm:
            count += 1
    return count


def _nearest_uncaptured_vp_distance_for_side(
    q: int | None,
    r: int | None,
    to_play_side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> float:
    if not isinstance(q, int) or not isinstance(r, int):
        return -1.0
    side_norm = _normalize_side_label(to_play_side)
    owners = dict(vp_owner_by_hex or {})
    dists: list[int] = []
    # Source of truth: owner map keys from runtime state.
    parsed_candidates: list[dict] = []
    if owners:
        for key in owners.keys():
            qk, rk = _parse_hex_key_to_qr(key)
            if qk is None or rk is None:
                continue
            parsed_candidates.append({"q": int(qk), "r": int(rk)})
    # Secondary source (for safety if owner map is unexpectedly empty).
    if not parsed_candidates:
        for vp in list(vp_hexes or []):
            vq, vr = _extract_vp_qr(vp)
            if vq is None or vr is None:
                continue
            parsed_candidates.append({"q": int(vq), "r": int(vr)})
    for vp in parsed_candidates:
        vq = int(vp.get("q"))
        vr = int(vp.get("r"))
        key = f"{int(vq)},{int(vr)}"
        owner = _normalize_side_label(owners.get(key, ""))
        if owner == side_norm:
            continue
        dists.append(int(_hex_distance_axial(int(q), int(r), int(vq), int(vr))))
    if not dists:
        return -1.0
    return float(min(dists))


def _side_min_uncaptured_vp_distance(
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> float:
    side_norm = _normalize_side_label(side)
    if not side_norm:
        return -1.0
    best = -1.0
    for u in list(units or []):
        if not isinstance(u, dict):
            continue
        if _normalize_side_label(u.get("side", "")) != side_norm:
            continue
        if not bool(u.get("alive", True)):
            continue
        q = _coerce_int_or_none(u.get("q"))
        r = _coerce_int_or_none(u.get("r"))
        d = _nearest_uncaptured_vp_distance_for_side(
            q=q,
            r=r,
            to_play_side=side_norm,
            vp_hexes=vp_hexes,
            vp_owner_by_hex=vp_owner_by_hex,
        )
        if d < 0.0:
            continue
        if best < 0.0 or d < best:
            best = float(d)
    return float(best)


def _unit_side_by_id(obs) -> dict:
    return {u["unit_id"]: str(u.get("side")) for u in obs.units if u.get("unit_id")}


def value_signs_from_to_play(obs, legal_actions: List[str]) -> dict:
    """
    Sign convention for backup from root player perspective:
    +1 when action belongs to root side, -1 otherwise.
    """
    root_side = str(obs.to_play) if obs.to_play is not None else ""
    side_by_unit = _unit_side_by_id(obs)
    signs = {}
    for action_id in legal_actions:
        parts = str(action_id).split(":")
        unit_id = parts[1] if len(parts) > 1 else ""
        action_side = side_by_unit.get(unit_id, root_side)
        signs[action_id] = 1 if action_side == root_side else -1
    return signs


def _inference_cache_key(obs, legal_actions: List[str], encoder_type: str) -> tuple:
    units_sig = tuple(
        sorted(
            (
                str(u.get("unit_id", "")),
                str(u.get("side", "")),
                int(u.get("q")) if isinstance(u.get("q"), int) else None,
                int(u.get("r")) if isinstance(u.get("r"), int) else None,
                float(u.get("hp")) if isinstance(u.get("hp"), (int, float)) else None,
                bool(u.get("alive", True)),
            )
            for u in (getattr(obs, "units", []) or [])
            if str(u.get("unit_id", ""))
        )
    )
    return (
        str(encoder_type),
        int(getattr(obs, "turn", 0)),
        str(getattr(obs, "to_play", "")),
        bool(getattr(obs, "done", False)),
        tuple(legal_actions),
        units_sig,
    )


def training_reward_from_transition(root_to_play: str | None, transition) -> float:
    if not transition.done:
        return 0.0
    winner = str(transition.state.winner) if transition.state.winner is not None else None
    if winner is None:
        return 0.0
    root = str(root_to_play) if root_to_play is not None else ""
    return 1.0 if winner == root else -1.0


def shaped_training_reward(
    root_to_play: str | None,
    transition,
    action_kind: str,
    damage_dealt: float,
    kills_dealt: int,
    vp_captures: int = 0,
    vp_net_delta: int = 0,
    objective_had_opportunity: bool = False,
    objective_progress_delta: float = 0.0,
    has_attack_option: bool = False,
    has_capture_option: bool = False,
    reward_shaping: dict | None = None,
) -> tuple[float, dict[str, float]]:
    cfg = reward_shaping or {}
    terminal_scale = float(cfg.get("terminal_scale", 1.0))
    damage_weight = float(cfg.get("damage_weight", 0.0))
    kill_weight = float(cfg.get("kill_weight", 0.0))
    vp_action_bonus = float(cfg.get("vp_action_bonus", 0.0))
    capture_bonus = float(cfg.get("capture_bonus", 0.0))
    vp_capture_bonus_per_hex = float(cfg.get("vp_capture_bonus_per_hex", capture_bonus))
    vp_net_gain_bonus = float(cfg.get("vp_net_gain_bonus", vp_action_bonus))
    vp_net_loss_penalty = float(cfg.get("vp_net_loss_penalty", 0.0))
    objective_progress_bonus_per_hex = float(cfg.get("objective_progress_bonus_per_hex", 0.0))
    objective_no_progress_penalty = float(cfg.get("objective_no_progress_penalty", 0.0))
    objective_no_progress_attack_penalty = float(cfg.get("objective_no_progress_attack_penalty", 0.0))
    reaction_fire_miss_penalty = float(cfg.get("reaction_fire_miss_penalty", 0.0))
    idle_penalty = float(cfg.get("idle_penalty", 0.0))
    idle_with_options_multiplier = float(cfg.get("idle_with_options_multiplier", 1.0))

    base_terminal = training_reward_from_transition(root_to_play, transition) * terminal_scale
    kind_upper = str(action_kind or "").upper()
    damage_component = damage_weight * float(damage_dealt)
    kill_component = kill_weight * float(kills_dealt)
    vp_action_component = 0.0
    if "VP" in str(getattr(transition, "action_id", "")).upper() or "CAPTURE" in kind_upper:
        vp_action_component = float(vp_action_bonus)
    capture_component = float(capture_bonus) if "CAPTURE" in kind_upper else 0.0
    vp_capture_event_component = float(max(0, int(vp_captures))) * float(vp_capture_bonus_per_hex)
    vp_net_gain_component = float(max(0, int(vp_net_delta))) * float(vp_net_gain_bonus)
    vp_net_loss_component = float(max(0, -int(vp_net_delta))) * float(vp_net_loss_penalty)
    objective_progress_component = 0.0
    objective_no_progress_component = 0.0
    objective_no_progress_attack_component = 0.0
    if bool(objective_had_opportunity):
        prog_delta = float(max(0.0, float(objective_progress_delta)))
        objective_progress_component = prog_delta * float(objective_progress_bonus_per_hex)
        if prog_delta <= 0.0:
            objective_no_progress_component = -float(max(0.0, objective_no_progress_penalty))
            if kind_upper not in {"", "MOVE", "WAIT", "TIMEOUT"}:
                objective_no_progress_attack_component = -float(max(0.0, objective_no_progress_attack_penalty))
    reaction_fire_miss_component = 0.0
    if (
        kind_upper == "OPPORTUNITY_FIRE"
        and float(damage_dealt) <= 0.0
        and int(kills_dealt) <= 0
    ):
        reaction_fire_miss_component = -float(max(0.0, reaction_fire_miss_penalty))
    dense = (
        damage_component
        + kill_component
        + vp_action_component
        + capture_component
        + vp_capture_event_component
        + vp_net_gain_component
        - vp_net_loss_component
        + objective_progress_component
        + objective_no_progress_component
        + objective_no_progress_attack_component
        + reaction_fire_miss_component
    )
    idle_component = 0.0
    if not transition.done and kind_upper in {"MOVE", "WAIT"} and dense <= 0.0:
        idle_component = float(idle_penalty)
        if has_attack_option or has_capture_option:
            idle_component *= float(max(1.0, idle_with_options_multiplier))
    total = float(base_terminal + dense + idle_component)
    return total, {
        "terminal": float(base_terminal),
        "damage": float(damage_component),
        "kill": float(kill_component),
        "vp_action": float(vp_action_component),
        "capture": float(capture_component),
        "vp_capture_event": float(vp_capture_event_component),
        "vp_net_gain": float(vp_net_gain_component),
        "vp_net_loss": float(vp_net_loss_component),
        "objective_progress": float(objective_progress_component),
        "objective_no_progress": float(objective_no_progress_component),
        "objective_no_progress_attack": float(objective_no_progress_attack_component),
        "reaction_fire_miss": float(reaction_fire_miss_component),
        "idle": float(idle_component),
        "timeout": 0.0,
        "total": float(total),
    }


def priors_and_values_from_model(
    model,
    observation,
    legal_actions: List[str],
    action_dim: int,
    unroll_steps: int = 1,
    discount: float = 0.997,
):
    model_device = next(model.parameters()).device

    def rollout_value_from_action(hidden_state, action_idx: int, depth: int) -> float:
        action_onehot = torch.zeros(1, action_dim, dtype=torch.float32, device=model_device)
        action_onehot[0, action_idx] = 1.0
        next_hidden, next_policy_logits, next_value, next_reward = model.recurrent_inference(
            hidden_state, action_onehot
        )
        reward_scalar = float(next_reward[0, 0].item())
        value_scalar = float(next_value[0, 0].item())
        if depth <= 1:
            return reward_scalar + (discount * value_scalar)
        next_idx = int(torch.argmax(next_policy_logits[0]).item())
        # Alternate perspective by ply in latent rollout.
        return reward_scalar - (discount * rollout_value_from_action(next_hidden, next_idx, depth - 1))

    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = observation.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([observation], dtype=torch.float32, device=model_device)
        hidden, policy_logits, _, _ = model.initial_inference(obs_tensor)
        logits = policy_logits[0]

        legal_indices = [action_id_to_index(a, action_dim) for a in legal_actions]
        legal_logits = torch.tensor(
            [float(logits[i].item()) for i in legal_indices],
            dtype=torch.float32,
            device=model_device,
        )
        legal_probs = torch.softmax(legal_logits, dim=0).tolist()
        priors = {a: p for a, p in zip(legal_actions, legal_probs)}

        values = {}
        for action_id, action_idx in zip(legal_actions, legal_indices):
            values[action_id] = rollout_value_from_action(
                hidden_state=hidden,
                action_idx=action_idx,
                depth=max(1, int(unroll_steps)),
            )
    return priors, values


def xai_root_signals_from_model(
    model,
    observation,
    legal_actions: List[str],
    action_dim: int,
    topk: int = 5,
):
    model_device = next(model.parameters()).device
    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = observation.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([observation], dtype=torch.float32, device=model_device)
        hidden, policy_logits, value_root, _ = model.initial_inference(obs_tensor)
        hidden_vec = hidden[0].detach()
        logits = policy_logits[0].detach()

        legal_pairs = []
        for action_id in legal_actions:
            idx = action_id_to_index(action_id, action_dim)
            legal_pairs.append((action_id, float(logits[idx].item())))
        if legal_pairs:
            legal_logits = torch.tensor(
                [p[1] for p in legal_pairs], dtype=torch.float32, device=model_device
            )
            legal_probs = torch.softmax(legal_logits, dim=0).detach().cpu().tolist()
            ranked = sorted(
                zip([p[0] for p in legal_pairs], legal_probs),
                key=lambda kv: float(kv[1]),
                reverse=True,
            )[: max(1, int(topk))]
            policy_top_actions = [str(a) for a, _ in ranked]
            policy_top_probs = [float(p) for _, p in ranked]
        else:
            policy_top_actions = []
            policy_top_probs = []

        k = min(max(1, int(topk)), int(hidden_vec.numel()))
        top_vals, top_idx = torch.topk(hidden_vec.abs(), k=k)
        latent_top_indices = [int(i) for i in top_idx.detach().cpu().tolist()]
        latent_top_values = [float(v) for v in top_vals.detach().cpu().tolist()]
        latent_l2_norm = float(torch.linalg.vector_norm(hidden_vec, ord=2).item())
        predicted_value_root = float(value_root[0, 0].item())
    return {
        "policy_top_actions": policy_top_actions,
        "policy_top_probs": policy_top_probs,
        "latent_top_indices": latent_top_indices,
        "latent_top_values": latent_top_values,
        "latent_l2_norm": latent_l2_norm,
        "predicted_value_root": predicted_value_root,
    }


def xai_dynamics_signals_for_action(
    model,
    observation,
    chosen_action_id: str,
    action_dim: int,
):
    model_device = next(model.parameters()).device
    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = observation.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([observation], dtype=torch.float32, device=model_device)
        hidden, _, _, _ = model.initial_inference(obs_tensor)
        hidden_vec = hidden[0].detach()
        action_idx = int(action_id_to_index(chosen_action_id, action_dim))
        action_onehot = torch.zeros(1, action_dim, dtype=torch.float32, device=model_device)
        action_onehot[0, action_idx] = 1.0
        next_hidden, _, _, pred_reward = model.recurrent_inference(hidden, action_onehot)
        next_hidden_vec = next_hidden[0].detach()
        dynamics_pred_reward = float(pred_reward[0, 0].item())
        dynamics_next_latent_l2 = float(torch.linalg.vector_norm(next_hidden_vec, ord=2).item())
        dynamics_delta_l2 = float(torch.linalg.vector_norm(next_hidden_vec - hidden_vec, ord=2).item())
    return {
        "dynamics_pred_reward": dynamics_pred_reward,
        "dynamics_next_latent_l2": dynamics_next_latent_l2,
        "dynamics_delta_l2": dynamics_delta_l2,
    }


def play_episode(
    adapter: MuZeroVOECAdapter,
    scenario_id: str,
    seed: int,
    max_steps: int = 100,
    max_steps_override: int = 0,
    action_dim: int = DEFAULT_ACTION_DIM,
    model=None,
    mcts_simulations: int = 32,
    mcts_c_puct: float = 1.5,
    mcts_unroll_steps: int = 1,
    mcts_discount: float = 0.997,
    mcts_temperature: float = 1.0,
    mcts_dirichlet_alpha: float = 0.3,
    mcts_dirichlet_epsilon: float = 0.0,
    progress_log_every: int = 0,
    timeout_penalty: float = -0.1,
    reward_shaping: dict | None = None,
) -> List[ReplaySample]:
    def _vp_control_counts(observation) -> dict[str, int]:
        sides = sorted(
            {
                str(u.get("side", "")).strip()
                for u in (getattr(observation, "units", []) or [])
                if str(u.get("side", "")).strip()
            }
        )
        counts: dict[str, int] = {s: 0 for s in sides}
        owner_by_hex = dict(getattr(observation, "vp_owner_by_hex", {}) or {})
        for owner in owner_by_hex.values():
            side = str(owner).strip()
            if not side:
                continue
            if side not in counts:
                counts[side] = 0
            counts[side] += 1
        return counts

    samples: List[ReplaySample] = []
    obs = adapter.initial_state(scenario_id=scenario_id, seed=seed)
    sim = getattr(adapter, "sim", None)
    scenario_turn_limit = None
    if sim is not None and hasattr(sim, "scenario_max_turns"):
        try:
            scenario_turn_limit = sim.scenario_max_turns()
        except Exception:
            scenario_turn_limit = None
    unit_count = len(getattr(obs, "units", []) or [])
    effective_max_steps = int(max_steps)
    if int(max_steps_override) > 0:
        effective_max_steps = int(max_steps_override)
    elif scenario_turn_limit is not None and int(scenario_turn_limit) > 0 and unit_count > 0:
        effective_max_steps = int(scenario_turn_limit) * int(unit_count)
    t0 = time.perf_counter()
    # Episode-local cache: repeated states can reuse model priors/values.
    inference_cache: dict[tuple, tuple[dict, dict, dict]] = {}
    inference_cache_limit = 2048
    for step_idx in range(effective_max_steps):
        legal = adapter.legal_actions()
        if not legal:
            break
        legal_kinds = [parse_action_id(a)[0] for a in legal]
        legal_attack_options = sum(1 for k in legal_kinds if _is_attack_like_action_kind(k))
        legal_reaction_options = sum(1 for k in legal_kinds if k.startswith("OPPORTUNITY_"))
        legal_capture_options = _count_vp_capture_options(
            legal_actions=legal,
            to_play_side=str(obs.to_play) if obs.to_play is not None else "",
            vp_owner_by_hex=dict(getattr(obs, "vp_owner_by_hex", {}) or {}),
        )
        eligible_unit_ids: list[str] = []
        sim = getattr(adapter, "sim", None)
        runtime = getattr(sim, "_runtime", None) if sim is not None else None
        active_side = str(obs.to_play) if obs.to_play is not None else ""
        if runtime is not None and active_side:
            try:
                eligible_unit_ids = [
                    str(getattr(u, "unit_id", ""))
                    for u in runtime.get_available_units(active_side)
                    if str(getattr(u, "unit_id", ""))
                ]
            except Exception:
                eligible_unit_ids = []
        if not eligible_unit_ids:
            eligible_unit_ids = [
                str(u.get("unit_id"))
                for u in obs.units
                if str(u.get("side", "")) == active_side
                and bool(u.get("alive", True))
                and str(u.get("unit_id", ""))
            ]
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_encoded = observation_to_tensor(
                obs,
                channels=int(getattr(model, "observation_channels", DEFAULT_OBS_CHANNELS)),
                height=int(getattr(model, "observation_height", DEFAULT_OBS_HEIGHT)),
                width=int(getattr(model, "observation_width", DEFAULT_OBS_WIDTH)),
            )
        else:
            obs_encoded = observation_to_vector(obs)
        priors = None
        values = None
        xai_signals = {
            "policy_top_actions": [],
            "policy_top_probs": [],
            "latent_top_indices": [],
            "latent_top_values": [],
            "latent_l2_norm": 0.0,
            "predicted_value_root": 0.0,
            "dynamics_pred_reward": 0.0,
            "dynamics_next_latent_l2": 0.0,
            "dynamics_delta_l2": 0.0,
        }
        if model is not None:
            cache_key = _inference_cache_key(
                obs=obs,
                legal_actions=legal,
                encoder_type=str(getattr(model, "encoder_type", "mlp")),
            )
            cached = inference_cache.get(cache_key)
            if cached is not None:
                priors, values, xai_signals = cached
            else:
                priors, values = priors_and_values_from_model(
                    model=model,
                    observation=obs_encoded,
                    legal_actions=legal,
                    action_dim=action_dim,
                    unroll_steps=mcts_unroll_steps,
                    discount=mcts_discount,
                )
                xai_signals = xai_root_signals_from_model(
                    model=model,
                    observation=obs_encoded,
                    legal_actions=legal,
                    action_dim=action_dim,
                    topk=5,
                )
                if len(inference_cache) >= inference_cache_limit:
                    inference_cache.clear()
                inference_cache[cache_key] = (priors, values, xai_signals)
        value_signs = value_signs_from_to_play(obs, legal)
        phase_ratio = float(step_idx) / float(max(1, effective_max_steps - 1))
        effective_temperature = float(mcts_temperature)
        effective_dirichlet_epsilon = float(mcts_dirichlet_epsilon)
        if phase_ratio > 0.66:
            effective_temperature = float(max(0.05, mcts_temperature * 0.4))
            effective_dirichlet_epsilon = 0.0
        elif phase_ratio > 0.33:
            effective_temperature = float(max(0.1, mcts_temperature * 0.75))
            effective_dirichlet_epsilon = float(max(0.0, mcts_dirichlet_epsilon * 0.5))
        mcts = run_mcts_puct(
            legal_actions=legal,
            num_simulations=mcts_simulations,
            c_puct=mcts_c_puct,
            priors_by_action=priors,
            values_by_action=values,
            value_sign_by_action=value_signs,
            temperature=effective_temperature,
            dirichlet_alpha=mcts_dirichlet_alpha,
            dirichlet_epsilon=effective_dirichlet_epsilon,
        )
        mcts_total_visits = int(sum(mcts.visits or []))
        mcts_active_actions = int(sum(1 for v in (mcts.visits or []) if int(v) > 0))
        chosen_prob = 0.0
        if mcts.actions and mcts.probs:
            for a, p in zip(mcts.actions, mcts.probs):
                if a == mcts.chosen_action:
                    chosen_prob = float(p)
                    break
        probs_sorted = sorted([float(p) for p in (mcts.probs or [])], reverse=True)
        top_p = probs_sorted[0] if probs_sorted else 0.0
        second_p = probs_sorted[1] if len(probs_sorted) > 1 else 0.0
        mcts_margin = float(top_p - second_p)
        mcts_entropy = 0.0
        for p in (mcts.probs or []):
            pp = float(max(1e-12, p))
            mcts_entropy += -pp * math.log(pp)
        predicted_value = 0.0
        if values is not None:
            predicted_value = float(values.get(mcts.chosen_action, 0.0))
        transition = adapter.apply(mcts.chosen_action)
        if model is not None:
            xai_dyn = xai_dynamics_signals_for_action(
                model=model,
                observation=obs_encoded,
                chosen_action_id=mcts.chosen_action,
                action_dim=action_dim,
            )
            xai_signals.update(xai_dyn)
        action_kind, acting_unit_id = parse_action_id(mcts.chosen_action)
        acting_unit = next((u for u in obs.units if str(u.get("unit_id")) == acting_unit_id), None)
        acting_q = int(acting_unit.get("q")) if isinstance(acting_unit, dict) and isinstance(acting_unit.get("q"), int) else 0
        acting_r = int(acting_unit.get("r")) if isinstance(acting_unit, dict) and isinstance(acting_unit.get("r"), int) else 0
        acting_side = str(acting_unit.get("side")) if acting_unit is not None else (
            str(obs.to_play) if obs.to_play is not None else ""
        )
        before_by_unit = {str(u.get("unit_id")): u for u in obs.units if u.get("unit_id")}
        action_parts = str(mcts.chosen_action).split(":")
        attack_target_unit_id = ""
        for token in reversed(action_parts):
            tok = str(token).strip()
            if not tok or tok == str(acting_unit_id):
                continue
            u = before_by_unit.get(tok)
            if not isinstance(u, dict):
                continue
            if str(u.get("side", "")) != acting_side:
                attack_target_unit_id = tok
                break
        if not attack_target_unit_id:
            attack_target_unit_id = _infer_indirect_target_unit_id(
                action_id=mcts.chosen_action,
                before_by_unit=before_by_unit,
                acting_side=acting_side,
            )
        attack_target_before = before_by_unit.get(attack_target_unit_id, {})
        attack_target_class_attempt = str(attack_target_before.get("unit_key", "")).strip() or ""
        target_q = int(attack_target_before.get("q")) if isinstance(attack_target_before.get("q"), int) else 0
        target_r = int(attack_target_before.get("r")) if isinstance(attack_target_before.get("r"), int) else 0
        before_vp_owner = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
        before_vp_counts = _vp_control_counts(obs)
        canonical_vp_hexes = _canonical_vp_hexes_from_sim(sim)
        before_vp_hexes = {
            f"{int(vp.get('q'))},{int(vp.get('r'))}"
            for vp in (canonical_vp_hexes or [])
            if isinstance(vp.get("q"), int) and isinstance(vp.get("r"), int)
        }
        after_units = transition.state.units
        damage_dealt = 0.0
        kills_dealt = 0
        attack_target_class_damage: dict[str, float] = {}
        attack_target_class_kills: dict[str, int] = {}
        attack_target_distances: list[float] = []
        attack_target_covers: list[float] = []
        attack_target_los_blocks: list[float] = []
        acting_q = acting_unit.get("q") if isinstance(acting_unit, dict) else None
        acting_r = acting_unit.get("r") if isinstance(acting_unit, dict) else None
        terrain_cover_by_hex = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
        terrain_los_block_by_hex = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
        for u_after in after_units:
            u_id = str(getattr(u_after, "unit_id", ""))
            if not u_id:
                continue
            u_before = before_by_unit.get(u_id)
            if u_before is None:
                continue
            enemy = str(getattr(u_after, "side", "")) != acting_side
            hp_before = u_before.get("hp")
            hp_after = getattr(u_after, "hp", None)
            if enemy and isinstance(hp_before, (int, float)) and isinstance(hp_after, (int, float)):
                damage_delta = max(0.0, float(hp_before) - float(hp_after))
                damage_dealt += damage_delta
                if damage_delta > 0.0:
                    t_cls = str(u_before.get("unit_key", "")).strip() or "UNKNOWN_TARGET"
                    attack_target_class_damage[t_cls] = (
                        attack_target_class_damage.get(t_cls, 0.0) + float(damage_delta)
                    )
            alive_before = bool(u_before.get("alive", True))
            alive_after = bool(getattr(u_after, "alive", True))
            if enemy and alive_before and not alive_after:
                kills_dealt += 1
                t_cls = str(u_before.get("unit_key", "")).strip() or "UNKNOWN_TARGET"
                attack_target_class_kills[t_cls] = attack_target_class_kills.get(t_cls, 0) + 1
        tq = attack_target_before.get("q")
        tr = attack_target_before.get("r")
        if isinstance(acting_q, int) and isinstance(acting_r, int) and isinstance(tq, int) and isinstance(tr, int):
            attack_target_distances.append(float(max(abs(acting_q - tq), abs(acting_r - tr))))
            hkey = f"{int(tq)},{int(tr)}"
            attack_target_covers.append(float(terrain_cover_by_hex.get(hkey, 0.0)))
            attack_target_los_blocks.append(float(terrain_los_block_by_hex.get(hkey, 0.0)))
        post_obs = adapter.observation()
        acting_after = next(
            (u for u in (getattr(post_obs, "units", []) or []) if str(u.get("unit_id", "")) == str(acting_unit_id)),
            None,
        )
        # Progress is mission-level: compare the side's closest alive unit to
        # an uncaptured VP before/after action, not only the acting unit.
        obj_dist_before = _side_min_uncaptured_vp_distance(
            units=list(getattr(obs, "units", []) or []),
            side=acting_side,
            vp_hexes=canonical_vp_hexes,
            vp_owner_by_hex=before_vp_owner,
        )
        obj_dist_after = _side_min_uncaptured_vp_distance(
            units=list(getattr(post_obs, "units", []) or []),
            side=acting_side,
            vp_hexes=canonical_vp_hexes,
            vp_owner_by_hex=dict(getattr(post_obs, "vp_owner_by_hex", {}) or {}),
        )
        objective_progress_delta = 0.0
        if obj_dist_before >= 0.0 and obj_dist_after >= 0.0:
            objective_progress_delta = float(obj_dist_before - obj_dist_after)
        after_vp_owner = dict(getattr(post_obs, "vp_owner_by_hex", {}) or {})
        after_vp_counts = _vp_control_counts(post_obs)
        vp_captures = 0
        for hex_key in before_vp_hexes:
            owner_before = str(before_vp_owner.get(hex_key, ""))
            owner_after = str(after_vp_owner.get(hex_key, ""))
            if owner_before != owner_after and owner_after == acting_side:
                vp_captures += 1
        vp_gain_by_side: dict[str, int] = {}
        vp_loss_by_side: dict[str, int] = {}
        all_sides = set(before_vp_counts.keys()) | set(after_vp_counts.keys())
        for side in all_sides:
            b = int(before_vp_counts.get(side, 0))
            a = int(after_vp_counts.get(side, 0))
            delta = a - b
            vp_gain_by_side[side] = int(max(0, delta))
            vp_loss_by_side[side] = int(max(0, -delta))
        # Strict opportunity signal: side has a valid distance to at least one
        # uncaptured VP (single source of truth, no fallback masking).
        objective_had_opportunity = int(float(obj_dist_before) >= 0.0)
        objective_converted = int(
            int(vp_captures) > 0
            or int(vp_gain_by_side.get(str(acting_side), 0)) > 0
        )
        reward_target, reward_components = shaped_training_reward(
            root_to_play=obs.to_play,
            transition=transition,
            action_kind=action_kind,
            damage_dealt=damage_dealt,
            kills_dealt=kills_dealt,
            vp_captures=int(vp_captures),
            vp_net_delta=int(vp_gain_by_side.get(str(acting_side), 0))
            - int(vp_loss_by_side.get(str(acting_side), 0)),
            objective_had_opportunity=(int(objective_had_opportunity) > 0),
            objective_progress_delta=float(objective_progress_delta),
            has_attack_option=(int(legal_attack_options) > 0),
            has_capture_option=(int(legal_capture_options) > 0),
            reward_shaping=reward_shaping,
        )
        action_idx = action_id_to_index(mcts.chosen_action, action_dim)
        attack_distance_mean = (
            float(sum(attack_target_distances) / float(max(1, len(attack_target_distances))))
            if attack_target_distances
            else -1.0
        )
        attack_target_cover_mean = (
            float(sum(attack_target_covers) / float(max(1, len(attack_target_covers))))
            if attack_target_covers
            else -1.0
        )
        attack_target_los_block_mean = (
            float(sum(attack_target_los_blocks) / float(max(1, len(attack_target_los_blocks))))
            if attack_target_los_blocks
            else -1.0
        )
        samples.append(
            build_sample(
                observation=obs_encoded,
                action_index=action_idx,
                action_dim=action_dim,
                reward=reward_target,
                done=transition.done,
                info={
                    "step": step_idx,
                    "game_turn": int(getattr(obs, "turn", 0)),
                    "action_id": mcts.chosen_action,
                    "action_kind": str(action_kind),
                    "unit_id": str(acting_unit_id),
                    "unit_side": str(acting_side),
                    "unit_key": str(acting_unit.get("unit_key")) if acting_unit is not None else "",
                    "unit_label": str(acting_unit.get("unit_label")) if acting_unit is not None else "",
                    "damage_dealt": float(damage_dealt),
                    "kills_dealt": int(kills_dealt),
                    "vp_captures": int(vp_captures),
                    "vp_control_before_by_side": dict(before_vp_counts),
                    "vp_control_after_by_side": dict(after_vp_counts),
                    "vp_gain_by_side": dict(vp_gain_by_side),
                    "vp_loss_by_side": dict(vp_loss_by_side),
                    "reward_components": dict(reward_components),
                    "to_play": str(obs.to_play) if obs.to_play is not None else "",
                    "eligible_unit_ids": list(eligible_unit_ids),
                    "eligible_unit_count": int(len(eligible_unit_ids)),
                    "legal_action_count": int(len(legal)),
                    "legal_attack_options": int(legal_attack_options),
                    "legal_capture_options": int(legal_capture_options),
                    "legal_reaction_options": int(legal_reaction_options),
                    "objective_had_opportunity": int(objective_had_opportunity),
                    "objective_distance_before": float(obj_dist_before),
                    "objective_distance_after": float(obj_dist_after),
                    "objective_progress_delta": float(objective_progress_delta),
                    "objective_converted": int(objective_converted),
                    "objective_vp_hexes_count": int(len(canonical_vp_hexes)),
                    "objective_vp_owner_count": int(len(before_vp_owner)),
                    "objective_side_norm": str(_normalize_side_label(acting_side)),
                    "mcts_entropy": float(mcts_entropy),
                    "mcts_margin": float(mcts_margin),
                    "chosen_action_prob": float(chosen_prob),
                    "predicted_value": float(predicted_value),
                    "mcts_total_visits": int(mcts_total_visits),
                    "mcts_active_actions": int(mcts_active_actions),
                    "attack_target_unit_id": str(attack_target_unit_id),
                    "attack_target_class_attempt": str(attack_target_class_attempt),
                    "attack_target_class_damage": dict(attack_target_class_damage),
                    "attack_target_class_kills": dict(attack_target_class_kills),
                    "attack_distance_mean": float(attack_distance_mean),
                    "attack_target_cover_mean": float(attack_target_cover_mean),
                    "attack_target_los_block_mean": float(attack_target_los_block_mean),
                    "policy_top_actions": list(xai_signals.get("policy_top_actions", []) or []),
                    "policy_top_probs": [
                        float(v) for v in (xai_signals.get("policy_top_probs", []) or [])
                    ],
                    "latent_top_indices": [
                        int(v) for v in (xai_signals.get("latent_top_indices", []) or [])
                    ],
                    "latent_top_values": [
                        float(v) for v in (xai_signals.get("latent_top_values", []) or [])
                    ],
                    "latent_l2_norm": float(xai_signals.get("latent_l2_norm", 0.0)),
                    "predicted_value_root": float(xai_signals.get("predicted_value_root", 0.0)),
                    "dynamics_pred_reward": float(xai_signals.get("dynamics_pred_reward", 0.0)),
                    "dynamics_next_latent_l2": float(xai_signals.get("dynamics_next_latent_l2", 0.0)),
                    "dynamics_delta_l2": float(xai_signals.get("dynamics_delta_l2", 0.0)),
                    "acting_q": int(acting_q),
                    "acting_r": int(acting_r),
                    "target_q": int(target_q),
                    "target_r": int(target_r),
                    "terminal_reason": str(transition.state.end_reason)
                    if transition.state.end_reason is not None
                    else "",
                    "timeout": False,
                },
            )
        )
        obs = post_obs
        if progress_log_every > 0 and ((step_idx + 1) % progress_log_every == 0):
            elapsed = time.perf_counter() - t0
            print(
                f"[MuZero]     selfplay step={step_idx + 1}/{effective_max_steps} "
                f"elapsed_s={elapsed:.1f}"
            )
        if transition.done:
            break
    if not adapter.terminal() and samples:
        # Timeout penalty to discourage endless neutral rollouts.
        prev_total = float(samples[-1].reward_target)
        samples[-1].reward_target = float(timeout_penalty)
        samples[-1].value_target = float(timeout_penalty)
        samples[-1].info["timeout"] = True
        comp = dict(samples[-1].info.get("reward_components", {}) or {})
        timeout_delta = float(timeout_penalty) - prev_total
        comp["timeout"] = float(comp.get("timeout", 0.0)) + float(timeout_delta)
        comp["total"] = float(timeout_penalty)
        samples[-1].info["reward_components"] = comp
        sim = getattr(adapter, "sim", None)
        reached_turn_limit = False
        if sim is not None and hasattr(sim, "reached_turn_limit"):
            try:
                reached_turn_limit = bool(sim.reached_turn_limit())
            except Exception:
                reached_turn_limit = False
        samples[-1].info["terminal_reason"] = (
            "scenario_turn_limit" if reached_turn_limit else "turn_unit_budget"
        )
    return samples
