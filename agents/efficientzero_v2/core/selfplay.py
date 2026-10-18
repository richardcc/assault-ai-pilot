from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import torch

from agents.efficientzero_v2.core.mcts import run_mcts_puct
from agents.efficientzero_v2.core.observation import observation_to_tensor
from agents.efficientzero_v2.core.objective_signals import (
    hex_distance_axial,
    objective_min_distance_snapshot,
    objective_step_signal,
    parse_hex_key_to_qr,
)
from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner
from agents.efficientzero_v2.core.targets import build_sample

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
def _unit_combat_feature_table() -> dict:
    from assault_model.paths import UNIT_CATALOG_PATH
    raw = json.loads(UNIT_CATALOG_PATH.read_text(encoding="utf-8"))
    units = dict(raw.get("units", {}) or {})
    table: dict[str, dict[str, float]] = {}
    for unit_key, payload in units.items():
        attack = dict(payload.get("attack", {}) or {})
        max_range = 0.0
        attack_power = 0.0
        for mode_payload in attack.values():
            for target_ranges in dict(mode_payload or {}).values():
                for rk, rv in dict(target_ranges or {}).items():
                    max_range = max(max_range, float(_range_high(rk)))
                    attack_power = max(attack_power, _dice_power(dict(rv or {}).get("dice", [])))
        defense = dict(payload.get("base_defense", {}) or {})
        defense_power = 0.0
        sides = 0
        for dice in defense.values():
            defense_power += _dice_power(dice)
            sides += 1
        if sides > 0:
            defense_power /= float(sides)
        table[str(unit_key)] = {
            "attack_power": float(attack_power),
            "defense_power": float(defense_power),
            "max_range": float(max_range),
        }
    return table


def _expected_damage_proxy(
    attacker_key: str,
    defender_key: str,
    distance: float,
    cover: float,
    los_block: float,
) -> float:
    table = _unit_combat_feature_table()
    a = dict(table.get(str(attacker_key or ""), {}) or {})
    d = dict(table.get(str(defender_key or ""), {}) or {})
    atk = float(a.get("attack_power", 0.0))
    dfn = float(d.get("defense_power", 0.0))
    max_range = float(max(1.0, a.get("max_range", 1.0)))
    dist = float(max(0.0, distance))
    range_factor = max(0.20, 1.0 - (dist / max_range))
    cover_factor = max(0.0, float(cover))
    los_factor = max(0.0, float(los_block))
    defense_term = dfn * (1.0 + (0.75 * cover_factor) + (0.50 * los_factor))
    return float(max(0.0, (atk * range_factor) - (0.60 * defense_term)))


def _scenario_turn_limit_from_adapter(adapter) -> int:
    try:
        if hasattr(adapter, "scenario_max_turns"):
            return int(adapter.scenario_max_turns() or 0)
    except Exception:
        return 0
    try:
        sim = getattr(adapter, "sim", None)
        if sim is not None and hasattr(sim, "scenario_max_turns"):
            return int(sim.scenario_max_turns() or 0)
    except Exception:
        return 0
    return 0


def resolve_effective_step_budget(
    *,
    max_steps: int,
    max_steps_override: int = 0,
    max_turns_override: int = 0,
    unit_count: int = 0,
    scenario_turn_limit: int = 0,
) -> tuple[int, str]:
    units = int(unit_count)
    turns_override = int(max_turns_override)
    steps_override = int(max_steps_override)
    scenario_turns = int(scenario_turn_limit)
    fallback_steps = int(max_steps)
    if turns_override > 0 and units > 0:
        return int(turns_override * units), "max_turns_override*unit_count"
    if steps_override > 0:
        return steps_override, "max_steps_override"
    if scenario_turns > 0 and units > 0:
        return int(scenario_turns * units), "scenario_turn_limit*unit_count"
    return fallback_steps, "max_steps_fallback"


def _observation_to_vector(obs) -> list[float]:
    alive = sum(1 for u in obs.units if u.get("alive", True))
    mean_hp = 0.0
    hp_values = [float(u.get("hp", 0.0)) for u in obs.units if isinstance(u.get("hp"), (int, float))]
    if hp_values:
        mean_hp = float(sum(hp_values) / max(1, len(hp_values)))
    return [float(obs.turn), float(alive), float(mean_hp), float(obs.done)]


def _observation_to_tensor(obs, channels: int = DEFAULT_OBS_CHANNELS, height: int = DEFAULT_OBS_HEIGHT, width: int = DEFAULT_OBS_WIDTH):
    return observation_to_tensor(
        obs,
        channels=int(channels),
        height=int(height),
        width=int(width),
    )


def _action_id_to_index(action_id: str, action_dim: int) -> int:
    return sum(str(action_id).encode("utf-8")) % int(action_dim)


def _parse_action_id(action_id: str) -> tuple[str, str]:
    parts = str(action_id).split(":")
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _unit_field(unit, key: str, default=None):
    if isinstance(unit, dict):
        return unit.get(key, default)
    return getattr(unit, key, default)


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _to_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _normalize_side(side_value) -> str:
    return str(side_value or "").strip().upper()


def _derive_enemy_damage_kills(before_units: list, after_units: list, actor_side: str) -> tuple[float, int]:
    actor_side_norm = _normalize_side(actor_side)
    hp_before_by_id = {}
    hp_after_by_id = {}
    alive_before_by_id = {}
    alive_after_by_id = {}
    side_by_id = {}
    for unit in list(before_units or []):
        unit_id = str(_unit_field(unit, "unit_id", "") or "")
        if not unit_id:
            continue
        hp_before_by_id[unit_id] = _to_float(_unit_field(unit, "hp", 0.0), 0.0)
        alive_before_by_id[unit_id] = bool(_unit_field(unit, "alive", True))
        side_by_id[unit_id] = _normalize_side(_unit_field(unit, "side", ""))
    for unit in list(after_units or []):
        unit_id = str(_unit_field(unit, "unit_id", "") or "")
        if not unit_id:
            continue
        hp_after_by_id[unit_id] = _to_float(_unit_field(unit, "hp", hp_before_by_id.get(unit_id, 0.0)), 0.0)
        alive_after_by_id[unit_id] = bool(_unit_field(unit, "alive", True))
        side_by_id.setdefault(unit_id, _normalize_side(_unit_field(unit, "side", "")))

    enemy_damage = 0.0
    enemy_kills = 0
    for unit_id, hp_before in hp_before_by_id.items():
        unit_side = _normalize_side(side_by_id.get(unit_id, ""))
        if not actor_side_norm or not unit_side or unit_side == actor_side_norm:
            continue
        hp_after = float(hp_after_by_id.get(unit_id, hp_before))
        enemy_damage += max(0.0, float(hp_before) - hp_after)
        if bool(alive_before_by_id.get(unit_id, True)) and not bool(alive_after_by_id.get(unit_id, True)):
            enemy_kills += 1
    return float(enemy_damage), int(enemy_kills)


def _resolve_actor_damage_kills(info: dict, before_units: list, after_units: list, actor_side: str) -> tuple[float, int]:
    fallback_damage, fallback_kills = _derive_enemy_damage_kills(before_units, after_units, actor_side)
    damage_dealt = fallback_damage
    kills_dealt = fallback_kills
    if isinstance(info, dict):
        info_damage = _to_float(
            info.get("damage_dealt", info.get("damage", info.get("enemy_damage", fallback_damage))),
            fallback_damage,
        )
        info_kills = _to_int(
            info.get("kills_dealt", info.get("kills", info.get("enemy_kills", fallback_kills))),
            fallback_kills,
        )
        # Keep non-zero fallback if telemetry provides stale zeros.
        if float(info_damage) > 0.0 or float(fallback_damage) <= 0.0:
            damage_dealt = float(info_damage)
        if int(info_kills) > 0 or int(fallback_kills) <= 0:
            kills_dealt = int(info_kills)
    return float(damage_dealt), int(kills_dealt)


def _extract_actor_combat_dice_signals(info: dict, acting_unit_id: str) -> tuple[list[dict], list[dict], dict[str, int], dict[str, int], list[dict]]:
    runtime_events = list(dict(info or {}).get("runtime_events", []) or [])
    attack_dice_rolls: list[dict] = []
    defense_dice_rolls: list[dict] = []
    attack_components: dict[str, int] = {}
    defense_components: dict[str, int] = {}
    for evt in runtime_events:
        evt_dict = dict(evt or {})
        if str(evt_dict.get("type", "")) != "ACTION_EFFECT":
            continue
        payload_evt = dict(evt_dict.get("payload", {}) or {})
        attacker_evt = str(payload_evt.get("attacker", "")).strip()
        if attacker_evt and attacker_evt != str(acting_unit_id or ""):
            continue
        for d in list(payload_evt.get("attacker_attack_dice", []) or []):
            dd = dict(d or {})
            faces = [str(x) for x in (list(dd.get("faces", []) or []))]
            attack_dice_rolls.append({"side": "attack", "color": str(dd.get("color", "")), "faces": list(faces)})
            for face in faces:
                key = str(face).strip().upper()
                if not key:
                    continue
                attack_components[key] = int(attack_components.get(key, 0)) + 1
        for d in list(payload_evt.get("defender_defense_dice", []) or []):
            dd = dict(d or {})
            faces = [str(x) for x in (list(dd.get("faces", []) or []))]
            defense_dice_rolls.append({"side": "defense", "color": str(dd.get("color", "")), "faces": list(faces)})
            for face in faces:
                key = str(face).strip().upper()
                if not key:
                    continue
                defense_components[key] = int(defense_components.get(key, 0)) + 1
    return (
        list(attack_dice_rolls),
        list(defense_dice_rolls),
        dict(attack_components),
        dict(defense_components),
        list(runtime_events),
    )


def _action_target_qr(action_id: str) -> tuple[int | None, int | None]:
    parts = str(action_id).split(":")
    if len(parts) < 2:
        return None, None
    # Canonical format is "...:<q>:<r>", but some producers emit compact
    # forms such as "...:<q>,<r>" or "...:(q,r)".
    try:
        return int(parts[-2]), int(parts[-1])
    except Exception:
        pass
    tail = str(parts[-1] if parts else "")
    q1, r1 = parse_hex_key_to_qr(tail)
    if isinstance(q1, int) and isinstance(r1, int):
        return int(q1), int(r1)
    if len(parts) >= 2:
        combined = f"{parts[-2]},{parts[-1]}"
        q2, r2 = parse_hex_key_to_qr(combined)
        if isinstance(q2, int) and isinstance(r2, int):
            return int(q2), int(r2)
    return None, None


def _count_capture_options(legal_actions: list[str], vp_owner_by_hex: dict[str, str], to_play: str) -> int:
    side = str(to_play or "").strip().upper()
    count = 0
    for action_id in list(legal_actions or []):
        kind = str(_parse_action_id(action_id)[0]).upper()
        if "CAPTURE" in kind:
            count += 1
            continue
        parts = str(action_id).split(":")
        if len(parts) < 2:
            continue
        try:
            q = int(parts[-2])
            r = int(parts[-1])
        except Exception:
            continue
        owner = str((vp_owner_by_hex or {}).get(f"{q},{r}", "")).strip().upper()
        if owner and owner != side:
            count += 1
    return count


def _action_targets_enemy_or_neutral_vp(action_id: str, vp_owner_by_hex: dict[str, str], side: str) -> bool:
    tq, tr = _action_target_qr(action_id)
    if not isinstance(tq, int) or not isinstance(tr, int):
        return False
    owner = _normalize_side((vp_owner_by_hex or {}).get(f"{int(tq)},{int(tr)}", ""))
    side_norm = _normalize_side(side)
    return bool(owner) and owner != side_norm


def _unit_prefilter_ranking(
    *,
    legal_actions: list[str],
    units: list[dict],
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
    to_play: str,
    terrain_cover_by_hex: dict[str, float],
    terrain_los_block_by_hex: dict[str, float],
    top_k: int,
    vp_progress_weight: float,
    capture_opportunity_weight: float,
    threat_weight: float,
) -> tuple[str, list[str], list[dict]]:
    actions_by_unit: dict[str, list[str]] = {}
    for action_id in list(legal_actions or []):
        _kind, actor_unit_id = _parse_action_id(str(action_id))
        actor_unit_id = str(actor_unit_id or "").strip()
        if not actor_unit_id:
            continue
        actions_by_unit.setdefault(actor_unit_id, []).append(str(action_id))
    if not actions_by_unit:
        return "", [], []

    units_by_id = {str(u.get("unit_id", "")): dict(u or {}) for u in list(units or []) if isinstance(u, dict)}
    units_idx_by_id, units_idx_by_pos = _build_unit_indexes(list(units or []))
    side_norm = _normalize_side(to_play)
    best_vp_q, best_vp_r = _best_enemy_vp_qr_for_side(
        side=str(side_norm),
        vp_hexes=list(vp_hexes or []),
        vp_owner_by_hex=dict(vp_owner_by_hex or {}),
        best_vp_id="",
    )
    ranking_rows: list[dict] = []
    for unit_id, unit_actions in actions_by_unit.items():
        unit = dict(units_by_id.get(str(unit_id), {}) or {})
        uq = unit.get("q")
        ur = unit.get("r")
        baseline_dist = None
        if isinstance(uq, int) and isinstance(ur, int) and isinstance(best_vp_q, int) and isinstance(best_vp_r, int):
            baseline_dist = float(hex_distance_axial(int(uq), int(ur), int(best_vp_q), int(best_vp_r)))
        best_progress = 0.0
        capture_opportunity = 0.0
        best_threat = 0.0
        for action_id in list(unit_actions or []):
            action_kind = str(_parse_action_id(action_id)[0]).upper()
            if "CAPTURE" in action_kind or _action_targets_enemy_or_neutral_vp(action_id, dict(vp_owner_by_hex or {}), str(side_norm)):
                capture_opportunity = 1.0
            tq, tr = _action_target_qr(action_id)
            if (
                baseline_dist is not None
                and isinstance(tq, int)
                and isinstance(tr, int)
                and isinstance(best_vp_q, int)
                and isinstance(best_vp_r, int)
            ):
                after_dist = float(hex_distance_axial(int(tq), int(tr), int(best_vp_q), int(best_vp_r)))
                best_progress = max(best_progress, float(baseline_dist - after_dist))
            if _is_attack_like_action(action_kind):
                best_threat = max(
                    best_threat,
                    float(
                        _candidate_expected_damage(
                            action_id=str(action_id),
                            units=list(units or []),
                            terrain_cover_by_hex=dict(terrain_cover_by_hex or {}),
                            terrain_los_block_by_hex=dict(terrain_los_block_by_hex or {}),
                            units_by_id=dict(units_idx_by_id),
                            units_by_pos=dict(units_idx_by_pos),
                        )
                    ),
                )
        score = (
            float(vp_progress_weight) * max(0.0, float(best_progress))
            + float(capture_opportunity_weight) * float(capture_opportunity)
            + float(threat_weight) * max(0.0, float(best_threat))
        )
        ranking_rows.append(
            {
                "unit_id": str(unit_id),
                "score": float(score),
                "vp_progress_potential": float(max(0.0, float(best_progress))),
                "capture_opportunity": int(capture_opportunity > 0.0),
                "threat_proxy": float(max(0.0, float(best_threat))),
                "action_count": int(len(unit_actions)),
            }
        )
    ranked = sorted(
        ranking_rows,
        key=lambda row: (
            -float(row.get("score", 0.0) or 0.0),
            -int(row.get("capture_opportunity", 0) or 0),
            str(row.get("unit_id", "")),
        ),
    )
    k = max(1, int(top_k))
    top_rows = list(ranked[:k])
    selected_unit_id = str(top_rows[0].get("unit_id", "")) if top_rows else ""
    selected_actions = list(actions_by_unit.get(selected_unit_id, []) or [])
    return selected_unit_id, selected_actions, top_rows


def _select_prefilter_unit_simple(legal_actions: list[str]) -> tuple[str, list[str]]:
    actions_by_unit: dict[str, list[str]] = {}
    for action_id in list(legal_actions or []):
        _kind, actor_unit_id = _parse_action_id(str(action_id))
        actor_unit_id = str(actor_unit_id or "").strip()
        if not actor_unit_id:
            continue
        actions_by_unit.setdefault(actor_unit_id, []).append(str(action_id))
    if not actions_by_unit:
        return "", []

    def _score(unit_id: str, actions: list[str]) -> tuple[int, int, int, str]:
        capture_count = 0
        attack_like_count = 0
        for action_id in list(actions or []):
            action_kind = str(_parse_action_id(action_id)[0]).strip().upper()
            if "CAPTURE" in action_kind:
                capture_count += 1
            if _is_attack_like_action(action_kind):
                attack_like_count += 1
        return (-capture_count, -attack_like_count, -int(len(actions)), str(unit_id))

    selected_unit_id = sorted(
        list(actions_by_unit.keys()),
        key=lambda unit_id: _score(str(unit_id), list(actions_by_unit.get(str(unit_id), []) or [])),
    )[0]
    return str(selected_unit_id), list(actions_by_unit.get(str(selected_unit_id), []) or [])


def _action_consumes_unit_activation(action_id: str) -> bool:
    kind = str(_parse_action_id(str(action_id))[0] or "").strip().upper()
    # Opportunity windows are reactive and should not consume the unit's
    # regular activation slot within the turn.
    if kind.startswith("OPPORTUNITY_"):
        return False
    return True


def _best_enemy_vp_qr_for_side(
    *,
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
    best_vp_id: str,
) -> tuple[int | None, int | None]:
    side_norm = str(side or "").strip().upper()
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = str(owner_raw or "").strip().upper()
    by_id: dict[str, tuple[int, int]] = {}
    fallback: tuple[int, int] | None = None
    for idx, vp in enumerate(list(vp_hexes or [])):
        if not isinstance(vp, dict):
            continue
        q, r = None, None
        if isinstance(vp.get("q"), int) and isinstance(vp.get("r"), int):
            q, r = int(vp.get("q")), int(vp.get("r"))
        else:
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if q is None or r is None:
            continue
        owner = owners_by_qr.get((int(q), int(r)), "")
        if owner == side_norm:
            continue
        key = f"{int(q)},{int(r)}"
        vp_id = str(vp.get("vp_id", "")).strip() or f"VP_{idx}_{key}"
        by_id[vp_id] = (int(q), int(r))
        if fallback is None:
            fallback = (int(q), int(r))
    if best_vp_id and best_vp_id in by_id:
        return by_id[best_vp_id]
    if fallback is not None:
        return fallback
    return None, None


def _candidate_vp_progress_delta(
    *,
    action_id: str,
    acting_q: int | None,
    acting_r: int | None,
    best_vp_q: int | None,
    best_vp_r: int | None,
    fallback_progress_delta: float | None,
    legal_capture_options: int,
) -> tuple[float, str]:
    if (
        isinstance(acting_q, int)
        and isinstance(acting_r, int)
        and isinstance(best_vp_q, int)
        and isinstance(best_vp_r, int)
    ):
        before_d = float(hex_distance_axial(acting_q, acting_r, best_vp_q, best_vp_r))
        tq, tr = _action_target_qr(action_id)
        if isinstance(tq, int) and isinstance(tr, int):
            after_d = float(hex_distance_axial(int(tq), int(tr), best_vp_q, best_vp_r))
            return float(before_d - after_d), "target_hex_parse"
    kind = str(_parse_action_id(action_id)[0]).strip().upper()
    if "CAPTURE" in kind and int(legal_capture_options) > 0:
        base = (
            float(fallback_progress_delta)
            if fallback_progress_delta is not None
            else 1.0
        )
        return max(1.0, base), "capture_hint"
    if fallback_progress_delta is not None:
        return float(fallback_progress_delta), "state_fallback"
    return 0.0, "unknown"


def _candidate_vp_target_after(
    *,
    action_id: str,
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
    acting_q: int | None = None,
    acting_r: int | None = None,
) -> tuple[str, float | None, str]:
    tq, tr = _action_target_qr(action_id)
    source = "target_hex_parse"
    if not isinstance(tq, int) or not isinstance(tr, int):
        # Position-based fallback for non-targeted actions (WAIT/ATTACK/etc):
        # use actor current hex as terminal proxy so VP target/distance remain
        # deterministic and producer-side.
        if isinstance(acting_q, int) and isinstance(acting_r, int):
            tq, tr = int(acting_q), int(acting_r)
            source = "actor_position_fallback"
        else:
            return "", None, "unavailable_no_target_hex"
    side_norm = str(side or "").strip().upper()
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = str(owner_raw or "").strip().upper()
    best_vp_id = ""
    best_distance: float | None = None
    for idx, vp in enumerate(list(vp_hexes or [])):
        if not isinstance(vp, dict):
            continue
        vq, vr = None, None
        if isinstance(vp.get("q"), int) and isinstance(vp.get("r"), int):
            vq, vr = int(vp.get("q")), int(vp.get("r"))
        else:
            vq, vr = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if vq is None or vr is None:
            continue
        owner = owners_by_qr.get((int(vq), int(vr)), "")
        if owner == side_norm:
            continue
        vid = str(vp.get("vp_id", "")).strip() or f"VP_{idx}_{int(vq)},{int(vr)}"
        d = float(hex_distance_axial(int(tq), int(tr), int(vq), int(vr)))
        if best_distance is None or d < best_distance:
            best_distance = d
            best_vp_id = vid
    if best_distance is None:
        return "", None, "unavailable_no_enemy_vp"
    return str(best_vp_id), float(best_distance), str(source)


def _candidate_expected_damage(
    *,
    action_id: str,
    units: list[dict],
    terrain_cover_by_hex: dict[str, float],
    terrain_los_block_by_hex: dict[str, float],
    units_by_id: dict[str, dict] | None = None,
    units_by_pos: dict[tuple[int, int], list[dict]] | None = None,
) -> float:
    parts = str(action_id or "").split(":")
    if len(parts) < 2:
        return 0.0
    actor_id = str(parts[1] or "")
    actor = None
    if isinstance(units_by_id, dict):
        actor = units_by_id.get(actor_id, None)
    if not isinstance(actor, dict):
        actor = next((u for u in list(units or []) if str(u.get("unit_id", "")) == actor_id), None)
    if not isinstance(actor, dict):
        return 0.0
    target = None
    target_id = str(parts[2] or "") if len(parts) > 2 else ""
    if target_id:
        if isinstance(units_by_id, dict):
            target = units_by_id.get(target_id, None)
        if not isinstance(target, dict):
            target = next((u for u in list(units or []) if str(u.get("unit_id", "")) == target_id), None)
    if not isinstance(target, dict):
        tq, tr = _action_target_qr(action_id)
        if isinstance(tq, int) and isinstance(tr, int):
            if isinstance(units_by_pos, dict):
                same_hex = list(units_by_pos.get((int(tq), int(tr)), []) or [])
                target = next((u for u in same_hex if str(u.get("side", "")) != str(actor.get("side", ""))), None)
            if not isinstance(target, dict):
                target = next(
                    (
                        u for u in list(units or [])
                        if str(u.get("side", "")) != str(actor.get("side", ""))
                        and int(u.get("q")) == int(tq)
                        and int(u.get("r")) == int(tr)
                    ),
                    None,
                )
    if not isinstance(target, dict):
        return 0.0
    aq = actor.get("q")
    ar = actor.get("r")
    tq = target.get("q")
    tr = target.get("r")
    if not all(isinstance(v, int) for v in (aq, ar, tq, tr)):
        return 0.0
    dist = float(max(abs(int(aq) - int(tq)), abs(int(ar) - int(tr))))
    key = f"{int(tq)},{int(tr)}"
    return float(
        _expected_damage_proxy(
            attacker_key=str(actor.get("unit_key", "") or ""),
            defender_key=str(target.get("unit_key", "") or ""),
            distance=dist,
            cover=float((terrain_cover_by_hex or {}).get(key, 0.0) or 0.0),
            los_block=float((terrain_los_block_by_hex or {}).get(key, 0.0) or 0.0),
        )
    )


def _build_unit_indexes(units: list[dict]) -> tuple[dict[str, dict], dict[tuple[int, int], list[dict]]]:
    by_id: dict[str, dict] = {}
    by_pos: dict[tuple[int, int], list[dict]] = {}
    for unit in list(units or []):
        u = dict(unit or {})
        uid = str(u.get("unit_id", "")).strip()
        if uid:
            by_id[uid] = u
        uq = u.get("q")
        ur = u.get("r")
        if isinstance(uq, int) and isinstance(ur, int):
            by_pos.setdefault((int(uq), int(ur)), []).append(u)
    return by_id, by_pos


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, float(value))))


def _is_attack_like_action(action_kind: str) -> bool:
    kind = str(action_kind or "").strip().upper()
    return (
        "ASSAULT" in kind
        or "ATTACK" in kind
        or "OPPORTUNITY_FIRE" in kind
        or "RANGED" in kind
        or "FIRE" in kind
        or "MELEE" in kind
    )


def _reaction_fire_proxy_from_dice(
    attack_dice_rolls: list[dict],
    defense_dice_rolls: list[dict],
) -> float | None:
    attack_total = 0.0
    attack_success = 0.0
    for die in list(attack_dice_rolls or []):
        color_weight = float(_DICE_WEIGHT.get(str((dict(die or {})).get("color", "")).upper(), 1.0))
        faces = [str(x).strip().upper() for x in list((dict(die or {})).get("faces", []) or [])]
        if not faces:
            continue
        attack_total += color_weight * float(len(faces))
        attack_success += color_weight * float(sum(1 for f in faces if f in {"HIT", "CRIT", "SUPPRESSION"}))
    defense_total = 0.0
    defense_success = 0.0
    for die in list(defense_dice_rolls or []):
        color_weight = float(_DICE_WEIGHT.get(str((dict(die or {})).get("color", "")).upper(), 1.0))
        faces = [str(x).strip().upper() for x in list((dict(die or {})).get("faces", []) or [])]
        if not faces:
            continue
        defense_total += color_weight * float(len(faces))
        defense_success += color_weight * float(sum(1 for f in faces if f in {"BLOCK", "SAVE", "EVADE"}))
    if attack_total <= 0.0 and defense_total <= 0.0:
        return None
    attack_rate = _clamp01(attack_success / max(1e-6, attack_total))
    defense_rate = _clamp01(defense_success / max(1e-6, defense_total))
    return _clamp01(attack_rate - (0.60 * defense_rate))


def _reaction_fire_soft_signal(
    *,
    action_kind: str,
    attack_dice_rolls: list[dict],
    defense_dice_rolls: list[dict],
    expected_damage_proxy: float,
    reward_shaping: dict | None,
) -> tuple[float, float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(cfg.get("reaction_fire_soft_signal_enabled", True))
    if not enabled:
        return 0.0, 0.0, "disabled"
    kind = str(action_kind or "").strip().upper()
    if kind != "OPPORTUNITY_FIRE":
        return 0.0, 0.0, "non_reaction_action"
    weight = float(cfg.get("reaction_fire_soft_signal_weight", 0.04) or 0.0)
    if weight == 0.0:
        return 0.0, 0.0, "zero_weight"
    damage_scale = float(cfg.get("reaction_fire_soft_signal_expected_damage_scale", 4.0) or 4.0)
    dice_proxy = _reaction_fire_proxy_from_dice(
        attack_dice_rolls=list(attack_dice_rolls or []),
        defense_dice_rolls=list(defense_dice_rolls or []),
    )
    if dice_proxy is None:
        proxy_prob = _clamp01(float(expected_damage_proxy) / max(1e-6, float(damage_scale)))
        source = "expected_damage_proxy"
    else:
        fallback_prob = _clamp01(float(expected_damage_proxy) / max(1e-6, float(damage_scale)))
        proxy_prob = _clamp01((0.70 * float(dice_proxy)) + (0.30 * fallback_prob))
        source = "dice_plus_expected_damage"
    centered = (2.0 * float(proxy_prob)) - 1.0
    return float(weight * centered), float(proxy_prob), str(source)


def _reaction_exposure_component(
    *,
    action_kind: str,
    obs_enemy_reaction_fire_risk: float,
    reward_shaping: dict | None,
) -> tuple[float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(cfg.get("reaction_exposure_component_enabled", True))
    if not enabled:
        return 0.0, "disabled"
    kind = str(action_kind or "").strip().upper()
    if kind.startswith("OPPORTUNITY_"):
        return 0.0, "reaction_action"
    weight = float(cfg.get("reaction_exposure_component_weight", 0.08) or 0.0)
    if weight == 0.0:
        return 0.0, "zero_weight"
    cap = abs(float(cfg.get("reaction_exposure_component_cap_abs", 0.20) or 0.20))
    risk = _clamp01(float(obs_enemy_reaction_fire_risk))
    factor = 0.8
    if "MOVE" in kind:
        factor = 1.0
    elif kind in {"ASSAULT", "MELEE", "ASSAULT_MELEE"}:
        factor = 1.15
    elif kind in {"WAIT", "TIMEOUT"}:
        factor = 0.25
    component = -float(weight) * float(risk) * float(factor)
    if cap > 0.0:
        component = max(-cap, min(cap, component))
    return float(component), "risk_by_action_kind"


def _min_owned_vp_distance(
    *,
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> float | None:
    side_norm = _normalize_side(side)
    if not side_norm:
        return None
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = _normalize_side(owner_raw)
    owned_qr: list[tuple[int, int]] = []
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        if owners_by_qr.get((int(q), int(r))) == side_norm:
            owned_qr.append((int(q), int(r)))
    if not owned_qr:
        return None
    best: float | None = None
    for unit in list(units or []):
        if _normalize_side(unit.get("side", "")) != side_norm:
            continue
        if not bool(unit.get("alive", True)):
            continue
        uq = unit.get("q")
        ur = unit.get("r")
        if not isinstance(uq, int) or not isinstance(ur, int):
            continue
        dmin = min(float(hex_distance_axial(int(uq), int(ur), oq, or_)) for oq, or_ in owned_qr)
        if best is None or dmin < best:
            best = float(dmin)
    return best


def _min_distance_to_vp_for_side(
    *,
    units: list[dict],
    side: str,
    vp_q: int | None,
    vp_r: int | None,
) -> float | None:
    side_norm = _normalize_side(side)
    if not side_norm or not isinstance(vp_q, int) or not isinstance(vp_r, int):
        return None
    best: float | None = None
    for unit in list(units or []):
        if _normalize_side(unit.get("side", "")) != side_norm:
            continue
        if not bool(unit.get("alive", True)):
            continue
        uq = unit.get("q")
        ur = unit.get("r")
        if not isinstance(uq, int) or not isinstance(ur, int):
            continue
        d = float(hex_distance_axial(int(uq), int(ur), int(vp_q), int(vp_r)))
        if best is None or d < best:
            best = d
    return best


def _enemy_vp_team_min_distance_sum(
    *,
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> float | None:
    side_norm = _normalize_side(side)
    if not side_norm:
        return None
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = _normalize_side(owner_raw)
    enemy_vps: list[tuple[int, int]] = []
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        if owners_by_qr.get((int(q), int(r))) == side_norm:
            continue
        enemy_vps.append((int(q), int(r)))
    if not enemy_vps:
        return None
    friendly_units = [
        u
        for u in list(units or [])
        if _normalize_side(u.get("side", "")) == side_norm and bool(u.get("alive", True))
    ]
    if not friendly_units:
        return None
    total = 0.0
    for vq, vr in enemy_vps:
        best: float | None = None
        for u in friendly_units:
            uq = u.get("q")
            ur = u.get("r")
            if not isinstance(uq, int) or not isinstance(ur, int):
                continue
            d = float(hex_distance_axial(int(uq), int(ur), int(vq), int(vr)))
            if best is None or d < best:
                best = d
        if best is None:
            continue
        total += float(best)
    return float(total)


def _min_steps_to_non_owned_vp_for_side(
    *,
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> float | None:
    side_norm = _normalize_side(side)
    if not side_norm:
        return None
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = _normalize_side(owner_raw)
    candidate_vps: list[tuple[int, int]] = []
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        if owners_by_qr.get((int(q), int(r))) == side_norm:
            continue
        candidate_vps.append((int(q), int(r)))
    if not candidate_vps:
        return None
    best: float | None = None
    for unit in list(units or []):
        if _normalize_side(unit.get("side", "")) != side_norm:
            continue
        if not bool(unit.get("alive", True)):
            continue
        uq = unit.get("q")
        ur = unit.get("r")
        if not isinstance(uq, int) or not isinstance(ur, int):
            continue
        d = min(float(hex_distance_axial(int(uq), int(ur), vq, vr)) for vq, vr in candidate_vps)
        if best is None or d < best:
            best = d
    return best


def _enemy_threat_signals(
    *,
    actor_side: str,
    units: list[dict],
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
) -> tuple[int | None, float | None]:
    actor_side_norm = _normalize_side(actor_side)
    if not actor_side_norm:
        return None, None
    enemy_sides = {
        _normalize_side(u.get("side", ""))
        for u in list(units or [])
        if _normalize_side(u.get("side", "")) not in {"", actor_side_norm}
    }
    if not enemy_sides:
        return None, None
    min_steps_candidates: list[float] = []
    for enemy_side in enemy_sides:
        d = _min_steps_to_non_owned_vp_for_side(
            units=list(units or []),
            side=str(enemy_side),
            vp_hexes=list(vp_hexes or []),
            vp_owner_by_hex=dict(vp_owner_by_hex or {}),
        )
        if isinstance(d, float):
            min_steps_candidates.append(float(d))
    if not min_steps_candidates:
        return None, None
    min_steps = float(min(min_steps_candidates))
    can_capture_next = int(min_steps <= 1.0)
    return can_capture_next, min_steps


def _enemy_threat_component(
    *,
    reward_shaping: dict | None,
    enemy_can_capture_vp_next: int | None,
    enemy_min_steps_to_vp: float | None,
) -> tuple[float, float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(
        cfg.get(
            "enemy_threat_component_enabled",
            cfg.get("enemy_threat_decision_enabled", False),
        )
    )
    if not enabled:
        return 0.0, 0.0, "disabled"
    weight = float(
        cfg.get(
            "enemy_threat_component_weight",
            cfg.get("enemy_threat_decision_weight", 0.01),
        )
        or 0.0
    )
    if weight <= 0.0:
        return 0.0, 0.0, "zero_weight"
    if enemy_can_capture_vp_next is None or not isinstance(enemy_min_steps_to_vp, (int, float)):
        return 0.0, 0.0, "unavailable"
    horizon_steps = max(
        1.0,
        float(
            cfg.get(
                "enemy_threat_component_horizon_steps",
                cfg.get("enemy_threat_decision_horizon_steps", 6.0),
            )
            or 6.0
        ),
    )
    cap_abs = max(
        0.0,
        float(
            cfg.get(
                "enemy_threat_component_cap_abs",
                cfg.get("enemy_threat_decision_cap_abs", 0.03),
            )
            or 0.03
        ),
    )
    immediate_bonus = float(
        cfg.get(
            "enemy_threat_component_immediate_capture_bonus",
            cfg.get("enemy_threat_decision_immediate_capture_bonus", 0.40),
        )
        or 0.40
    )
    proximity_signal = _clamp01((horizon_steps - float(enemy_min_steps_to_vp)) / horizon_steps)
    if int(enemy_can_capture_vp_next) > 0:
        proximity_signal = _clamp01(proximity_signal + immediate_bonus)
    component = -min(cap_abs, weight * proximity_signal)
    return float(component), float(proximity_signal), "steps_to_vp"


def _unit_hex_masks_from_actions(
    *,
    legal_actions: list[str],
    include_action: callable,
) -> dict[str, list[dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    for action_id in list(legal_actions or []):
        action_kind, unit_id = _parse_action_id(str(action_id))
        unit_key = str(unit_id or "").strip()
        if not unit_key:
            continue
        kind_norm = str(action_kind or "").strip().upper()
        if not include_action(kind_norm):
            continue
        tq, tr = _action_target_qr(str(action_id))
        if not isinstance(tq, int) or not isinstance(tr, int):
            continue
        unit_map = out.setdefault(unit_key, {})
        unit_map[f"{int(tq)},{int(tr)}"] = {"q": int(tq), "r": int(tr)}
    return {
        unit_id: sorted(
            list(hexes.values()),
            key=lambda h: (int(h.get("q", 0)), int(h.get("r", 0))),
        )
        for unit_id, hexes in out.items()
    }


def _obs_reachable_hex_mask_by_unit(legal_actions: list[str]) -> dict[str, list[dict[str, int]]]:
    return _unit_hex_masks_from_actions(
        legal_actions=list(legal_actions or []),
        include_action=lambda kind: (
            kind.startswith("MOVE")
            or kind.startswith("STEP")
            or kind.startswith("ADVANCE")
            or kind.startswith("FLANK")
            or kind.startswith("RETREAT")
        ),
    )


def _obs_attackable_hex_mask_by_unit(legal_actions: list[str]) -> dict[str, list[dict[str, int]]]:
    return _unit_hex_masks_from_actions(
        legal_actions=list(legal_actions or []),
        include_action=lambda kind: _is_attack_like_action(kind),
    )


def _obs_enemy_vp_threat_map(
    *,
    units: list[dict],
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
    actor_side: str,
    threat_radius: int = 6,
) -> dict[str, float]:
    side_norm = _normalize_side(actor_side)
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = _normalize_side(owner_raw)
    radius = max(1, int(threat_radius))
    enemy_units = [
        u for u in list(units or [])
        if _normalize_side(u.get("side", "")) not in {"", side_norm}
        and bool(u.get("alive", True))
    ]
    out: dict[str, float] = {}
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        owner = owners_by_qr.get((int(q), int(r)), "")
        if owner == side_norm:
            continue
        best: float | None = None
        for enemy in enemy_units:
            eq = enemy.get("q")
            er = enemy.get("r")
            if not isinstance(eq, int) or not isinstance(er, int):
                continue
            d = float(hex_distance_axial(int(eq), int(er), int(q), int(r)))
            if best is None or d < best:
                best = d
        if best is None:
            out[f"{int(q)},{int(r)}"] = 0.0
            continue
        out[f"{int(q)},{int(r)}"] = float(_clamp01((float(radius) - float(best)) / float(radius)))
    return out


def _obs_enemy_reaction_fire_risk(
    *,
    legal_actions: list[str],
    units: list[dict],
    actor_side: str,
) -> float:
    side_norm = _normalize_side(actor_side)
    units_by_id = {str(u.get("unit_id", "")): dict(u or {}) for u in list(units or []) if isinstance(u, dict)}
    total_reaction = 0
    enemy_reaction = 0
    for action_id in list(legal_actions or []):
        kind, unit_id = _parse_action_id(str(action_id))
        if str(kind).strip().upper() != "OPPORTUNITY_FIRE":
            continue
        total_reaction += 1
        side = _normalize_side((units_by_id.get(str(unit_id), {}) or {}).get("side", ""))
        if side and side != side_norm:
            enemy_reaction += 1
    if total_reaction > 0:
        return float(_clamp01(float(enemy_reaction) / float(total_reaction)))

    # Fallback when explicit reaction options are not exposed in legal actions:
    # approximate enemy reaction pressure by nearest enemy proximity to actor units.
    actor_units = [
        dict(u or {})
        for u in list(units or [])
        if isinstance(u, dict)
        and bool(u.get("alive", True))
        and _normalize_side(u.get("side", "")) == side_norm
    ]
    enemy_units = [
        dict(u or {})
        for u in list(units or [])
        if isinstance(u, dict)
        and bool(u.get("alive", True))
        and _normalize_side(u.get("side", ""))
        and _normalize_side(u.get("side", "")) != side_norm
    ]
    if not actor_units or not enemy_units:
        return 0.0
    radius = 6.0
    risk = 0.0
    for actor in actor_units:
        aq = actor.get("q")
        ar = actor.get("r")
        if not isinstance(aq, int) or not isinstance(ar, int):
            continue
        best: float | None = None
        for enemy in enemy_units:
            eq = enemy.get("q")
            er = enemy.get("r")
            if not isinstance(eq, int) or not isinstance(er, int):
                continue
            d = float(hex_distance_axial(int(aq), int(ar), int(eq), int(er)))
            if best is None or d < best:
                best = d
        if best is None:
            continue
        risk = max(risk, _clamp01((radius - float(best)) / radius))
    return float(_clamp01(risk))


def _obs_vp_ownership_ttl(
    *,
    units: list[dict],
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
    ttl_cap: int = 8,
) -> dict[str, int]:
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = _normalize_side(owner_raw)
    enemy_by_side: dict[str, list[dict]] = {}
    for u in list(units or []):
        if not isinstance(u, dict) or not bool(u.get("alive", True)):
            continue
        side = _normalize_side(u.get("side", ""))
        if not side:
            continue
        enemy_by_side.setdefault(side, []).append(dict(u))
    cap = max(1, int(ttl_cap))
    out: dict[str, int] = {}
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        owner = owners_by_qr.get((int(q), int(r)), "")
        key = f"{int(q)},{int(r)}"
        if not owner:
            out[key] = 0
            continue
        enemy_units = [
            u for side, side_units in enemy_by_side.items()
            if side != owner for u in side_units
        ]
        if not enemy_units:
            out[key] = cap
            continue
        dmin: float | None = None
        for enemy in enemy_units:
            eq = enemy.get("q")
            er = enemy.get("r")
            if not isinstance(eq, int) or not isinstance(er, int):
                continue
            d = float(hex_distance_axial(int(eq), int(er), int(q), int(r)))
            if dmin is None or d < dmin:
                dmin = d
        if dmin is None:
            out[key] = cap
            continue
        out[key] = int(max(0, min(cap, int(round(float(dmin) - 1.0)))))
    return out


def _mobility_opportunity_cost_component(
    *,
    reward_shaping: dict | None,
    action_vp_progress: float,
    best_unit_vp_progress: float,
) -> tuple[float, float, str]:
    cfg = dict(reward_shaping or {})
    if not bool(cfg.get("mobility_opportunity_cost_component_enabled", False)):
        return 0.0, 0.0, "disabled"
    weight = float(cfg.get("mobility_opportunity_cost_component_weight", 0.0) or 0.0)
    if weight <= 0.0:
        return 0.0, 0.0, "zero_weight"
    cap_abs = max(0.0, float(cfg.get("mobility_opportunity_cost_component_cap_abs", 0.02) or 0.02))
    denom = max(1.0, abs(float(best_unit_vp_progress)))
    signal = _clamp01(max(0.0, float(best_unit_vp_progress) - float(action_vp_progress)) / denom)
    component = -min(cap_abs, float(weight) * float(signal))
    return float(component), float(signal), "unit_vp_progress_gap"


def _cross_unit_synergy_component(
    *,
    reward_shaping: dict | None,
    action_id: str,
    actor_unit_id: str,
    actor_side: str,
    units: list[dict],
    reachable_hex_mask_by_unit: dict[str, list[dict[str, int]]],
    attackable_hex_mask_by_unit: dict[str, list[dict[str, int]]],
) -> tuple[float, float, str]:
    cfg = dict(reward_shaping or {})
    if not bool(cfg.get("cross_unit_synergy_component_enabled", False)):
        return 0.0, 0.0, "disabled"
    weight = float(cfg.get("cross_unit_synergy_component_weight", 0.0) or 0.0)
    if weight <= 0.0:
        return 0.0, 0.0, "zero_weight"
    tq, tr = _action_target_qr(str(action_id))
    if not isinstance(tq, int) or not isinstance(tr, int):
        return 0.0, 0.0, "no_target_hex"
    target_key = f"{int(tq)},{int(tr)}"
    side_norm = _normalize_side(actor_side)
    allies = [
        str(u.get("unit_id", ""))
        for u in list(units or [])
        if _normalize_side(u.get("side", "")) == side_norm
        and bool(u.get("alive", True))
        and str(u.get("unit_id", "")) != str(actor_unit_id)
    ]
    if not allies:
        return 0.0, 0.0, "no_allies"
    support_count = 0
    for ally_id in allies:
        reachable = {
            f"{int(h.get('q', 0))},{int(h.get('r', 0))}"
            for h in list(reachable_hex_mask_by_unit.get(str(ally_id), []) or [])
            if isinstance(h, dict)
        }
        attackable = {
            f"{int(h.get('q', 0))},{int(h.get('r', 0))}"
            for h in list(attackable_hex_mask_by_unit.get(str(ally_id), []) or [])
            if isinstance(h, dict)
        }
        if target_key in reachable or target_key in attackable:
            support_count += 1
    signal = _clamp01(float(support_count) / float(max(1, len(allies))))
    cap_abs = max(0.0, float(cfg.get("cross_unit_synergy_component_cap_abs", 0.02) or 0.02))
    component = min(cap_abs, float(weight) * float(signal))
    return float(component), float(signal), "ally_target_overlap"


def _safe_enemy_threat_defaults(
    *,
    can_capture_default: int,
    min_steps_default: float,
) -> tuple[int, float]:
    return int(can_capture_default), float(min_steps_default)


def _objective_progress_soft_signal(
    *,
    reward_shaping: dict | None,
    objective_had_opportunity: int,
    objective_converted: int,
    objective_progress_delta: float,
    team_progress_delta: float,
    legal_capture_options: int,
    action_kind: str,
) -> tuple[float, dict[str, float | int | bool]]:
    cfg = dict(reward_shaping or {})
    if int(objective_had_opportunity) <= 0:
        return 0.0, {
            "objective_soft_enabled": 0,
            "objective_soft_had_opportunity": 0,
            "objective_soft_component": 0.0,
        }
    if int(objective_converted) > 0:
        # If conversion already happened on this step, ignore progress-delta shaping to avoid
        # mixing "new target" deltas with a successful conversion event.
        return 0.0, {
            "objective_soft_enabled": 1,
            "objective_soft_had_opportunity": 1,
            "objective_soft_component": 0.0,
            "objective_soft_progress_masked_on_convert": True,
        }
    progress_bonus = float(cfg.get("objective_progress_bonus_per_hex", 0.0) or 0.0)
    team_progress_bonus = float(
        cfg.get("objective_team_progress_bonus_per_hex", progress_bonus)
        or progress_bonus
    )
    no_progress_penalty = float(cfg.get("objective_no_progress_penalty", 0.0) or 0.0)
    no_progress_attack_penalty = float(
        cfg.get("objective_no_progress_attack_penalty", 0.0) or 0.0
    )
    progress_cap_abs = float(cfg.get("objective_progress_cap_abs", 1.0) or 1.0)
    team_progress_cap_abs = float(cfg.get("objective_team_progress_cap_abs", 1.5) or 1.5)
    progress_capped = max(0.0, min(float(progress_cap_abs), float(objective_progress_delta)))
    team_progress_capped = max(0.0, min(float(team_progress_cap_abs), float(team_progress_delta)))
    component = (progress_bonus * progress_capped) + (team_progress_bonus * team_progress_capped)
    no_progress = progress_capped <= 0.0 and team_progress_capped <= 0.0
    if no_progress:
        component -= abs(no_progress_penalty)
        if int(legal_capture_options) > 0 and _is_attack_like_action(str(action_kind)):
            component -= abs(no_progress_attack_penalty)
    return float(component), {
        "objective_soft_enabled": 1,
        "objective_soft_had_opportunity": 1,
        "objective_soft_component": float(component),
        "objective_soft_progress_delta_raw": float(objective_progress_delta),
        "objective_soft_progress_delta_capped": float(progress_capped),
        "objective_soft_team_progress_delta_raw": float(team_progress_delta),
        "objective_soft_team_progress_delta_capped": float(team_progress_capped),
        "objective_soft_no_progress_triggered": bool(no_progress),
        "objective_soft_progress_bonus_per_hex": float(progress_bonus),
        "objective_soft_team_progress_bonus_per_hex": float(team_progress_bonus),
        "objective_soft_no_progress_penalty": float(no_progress_penalty),
        "objective_soft_no_progress_attack_penalty": float(no_progress_attack_penalty),
    }


def _vp_control_counts(vp_owner_by_hex: dict[str, str], side: str) -> tuple[int, int]:
    side_norm = _normalize_side(side)
    friendly = 0
    enemy = 0
    for owner in dict(vp_owner_by_hex or {}).values():
        owner_norm = _normalize_side(owner)
        if not owner_norm:
            continue
        if owner_norm == side_norm:
            friendly += 1
        else:
            enemy += 1
    return int(friendly), int(enemy)


def _count_units_in_vp_ring(
    *,
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_ring_radius: int,
) -> int:
    side_norm = _normalize_side(side)
    if not side_norm:
        return 0
    radius = max(0, int(vp_ring_radius))
    vp_qr: list[tuple[int, int]] = []
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if isinstance(q, int) and isinstance(r, int):
            vp_qr.append((int(q), int(r)))
    if not vp_qr:
        return 0
    count = 0
    for unit in list(units or []):
        if _normalize_side(unit.get("side", "")) != side_norm:
            continue
        if not bool(unit.get("alive", True)):
            continue
        uq = unit.get("q")
        ur = unit.get("r")
        if not isinstance(uq, int) or not isinstance(ur, int):
            continue
        dmin = min(hex_distance_axial(int(uq), int(ur), vq, vr) for vq, vr in vp_qr)
        if int(dmin) <= int(radius):
            count += 1
    return int(count)


def _enemy_threat_on_owned_vp(
    *,
    units: list[dict],
    side: str,
    vp_hexes: list[dict],
    vp_owner_by_hex: dict[str, str],
    threat_radius: int,
) -> float:
    side_norm = _normalize_side(side)
    if not side_norm:
        return 0.0
    owners_by_qr: dict[tuple[int, int], str] = {}
    for raw_key, owner_raw in dict(vp_owner_by_hex or {}).items():
        qk, rk = parse_hex_key_to_qr(str(raw_key))
        if qk is None or rk is None:
            continue
        owners_by_qr[(int(qk), int(rk))] = _normalize_side(owner_raw)
    owned_qr: list[tuple[int, int]] = []
    for vp in list(vp_hexes or []):
        if not isinstance(vp, dict):
            continue
        q = vp.get("q")
        r = vp.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            q, r = parse_hex_key_to_qr(vp.get("hex_key", ""))
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        if owners_by_qr.get((int(q), int(r))) == side_norm:
            owned_qr.append((int(q), int(r)))
    if not owned_qr:
        return 0.0
    enemy_units = [
        u for u in list(units or [])
        if _normalize_side(u.get("side", "")) not in {"", side_norm} and bool(u.get("alive", True))
    ]
    if not enemy_units:
        return 0.0
    radius = max(1, int(threat_radius))
    threat = 0.0
    for oq, or_ in owned_qr:
        best: float | None = None
        for e in enemy_units:
            eq = e.get("q")
            er = e.get("r")
            if not isinstance(eq, int) or not isinstance(er, int):
                continue
            d = float(hex_distance_axial(int(eq), int(er), int(oq), int(or_)))
            if best is None or d < best:
                best = d
        if best is None:
            continue
        # Nearer enemy -> higher threat in [0,1].
        threat += _clamp01((float(radius) - float(best)) / float(radius))
    return float(threat / max(1, len(owned_qr)))


def _role_kind_for_action(action_kind: str) -> str:
    kind = str(action_kind or "").strip().upper()
    if "CAPTURE" in kind:
        return "capture"
    if kind.startswith("MOVE") or kind.startswith("STEP"):
        return "screen"
    if kind.startswith("SUPPORT") or kind.startswith("OVERWATCH"):
        return "support"
    if kind.startswith("ASSAULT") or kind.startswith("ATTACK"):
        return "support"
    return "default"


def _global_strategy_soft_signal(
    *,
    side: str,
    action_kind: str,
    before_units: list[dict],
    after_units: list[dict],
    before_vp_owner_by_hex: dict[str, str],
    after_vp_owner_by_hex: dict[str, str],
    vp_hexes: list[dict],
    reward_shaping: dict | None,
    sustained_advantage_turns: int,
    previous_setup_strength: float,
    vp_captures: int,
) -> tuple[float, dict[str, float | int | str]]:
    cfg = dict(reward_shaping or {})
    if not bool(cfg.get("global_strategy_soft_enabled", True)):
        return 0.0, {"enabled": 0}

    vp_ring_radius = int(cfg.get("global_strategy_vp_ring_radius", 2) or 2)
    threat_radius = int(cfg.get("global_strategy_enemy_threat_radius", 3) or 3)

    before_friendly, before_enemy = _vp_control_counts(before_vp_owner_by_hex, side)
    after_friendly, after_enemy = _vp_control_counts(after_vp_owner_by_hex, side)
    vp_total = max(1, before_friendly + before_enemy)
    vp_control_delta = ((after_friendly - after_enemy) - (before_friendly - before_enemy)) / float(vp_total)
    vp_control_delta = max(-1.0, min(1.0, float(vp_control_delta)))

    units_before = _count_units_in_vp_ring(
        units=before_units,
        side=side,
        vp_hexes=vp_hexes,
        vp_ring_radius=vp_ring_radius,
    )
    units_after = _count_units_in_vp_ring(
        units=after_units,
        side=side,
        vp_hexes=vp_hexes,
        vp_ring_radius=vp_ring_radius,
    )
    friendly_alive = max(
        1,
        sum(
            1
            for u in list(after_units or [])
            if _normalize_side(u.get("side", "")) == _normalize_side(side) and bool(u.get("alive", True))
        ),
    )
    units_ring_delta = max(-1.0, min(1.0, float(units_after - units_before) / float(friendly_alive)))

    threat_before = _enemy_threat_on_owned_vp(
        units=before_units,
        side=side,
        vp_hexes=vp_hexes,
        vp_owner_by_hex=before_vp_owner_by_hex,
        threat_radius=threat_radius,
    )
    threat_after = _enemy_threat_on_owned_vp(
        units=after_units,
        side=side,
        vp_hexes=vp_hexes,
        vp_owner_by_hex=after_vp_owner_by_hex,
        threat_radius=threat_radius,
    )
    enemy_threat_reduced = max(-1.0, min(1.0, float(threat_before - threat_after)))

    sustain_min_turns = int(cfg.get("global_strategy_sustained_advantage_min_turns", 2) or 2)
    sustained_bonus_raw = 1.0 if int(sustained_advantage_turns) >= int(sustain_min_turns) else 0.0

    role_kind = _role_kind_for_action(action_kind)
    if role_kind == "capture":
        role_consistency = _clamp01((vp_control_delta + max(0.0, units_ring_delta) + float(vp_captures > 0)) / 2.0)
    elif role_kind == "screen":
        role_consistency = _clamp01((max(0.0, enemy_threat_reduced) + max(0.0, units_ring_delta)) / 1.5)
    elif role_kind == "support":
        role_consistency = _clamp01((max(0.0, units_ring_delta) + max(0.0, -enemy_threat_reduced)) / 1.5)
    else:
        role_consistency = 0.0

    setup_convert_bonus_raw = _clamp01(previous_setup_strength) if int(vp_captures) > 0 else 0.0
    next_setup_strength = _clamp01(
        max(
            0.0,
            (0.55 * max(0.0, units_ring_delta)) + (0.45 * max(0.0, enemy_threat_reduced)),
        )
    )

    weighted = (
        float(cfg.get("global_strategy_vp_control_net_gain_weight", 0.08) or 0.0) * float(vp_control_delta)
        + float(cfg.get("global_strategy_units_in_vp_ring_weight", 0.04) or 0.0) * float(units_ring_delta)
        + float(cfg.get("global_strategy_enemy_vp_threat_reduced_weight", 0.05) or 0.0) * float(enemy_threat_reduced)
        + float(cfg.get("global_strategy_sustained_vp_advantage_weight", 0.02) or 0.0) * float(sustained_bonus_raw)
        + float(cfg.get("global_strategy_role_consistency_weight", 0.03) or 0.0) * float(role_consistency)
        + float(cfg.get("global_strategy_setup_convert_weight", 0.03) or 0.0) * float(setup_convert_bonus_raw)
    )
    cap = float(cfg.get("global_strategy_total_cap_abs", 0.15) or 0.15)
    component = max(-abs(cap), min(abs(cap), float(weighted)))
    return float(component), {
        "enabled": 1,
        "vp_control_net_gain_signal": float(vp_control_delta),
        "units_in_vp_ring_signal": float(units_ring_delta),
        "enemy_vp_threat_reduced_signal": float(enemy_threat_reduced),
        "sustained_vp_advantage_turns": int(sustained_advantage_turns),
        "sustained_vp_advantage_bonus_signal": float(sustained_bonus_raw),
        "soft_role_kind": str(role_kind),
        "soft_role_consistency_signal": float(role_consistency),
        "setup_convert_signal": float(setup_convert_bonus_raw),
        "next_setup_strength": float(next_setup_strength),
        "vp_ring_radius": int(vp_ring_radius),
        "enemy_threat_radius": int(threat_radius),
    }


def _vp_horizon_soft_components(
    *,
    reward_shaping: dict | None,
    objective_had_opportunity: int,
    baseline_horizon_steps: float | None,
    vp_progress_delta: float,
) -> tuple[float, float, float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(cfg.get("vp_horizon_soft_enabled", True))
    if not enabled:
        return 0.0, -1.0, 0.0, "disabled"
    if int(objective_had_opportunity) <= 0:
        return 0.0, -1.0, 0.0, "no_opportunity"
    weight = float(cfg.get("vp_horizon_soft_weight", 0.02) or 0.0)
    if weight == 0.0:
        return 0.0, -1.0, 0.0, "zero_weight"
    horizon_cap = max(1.0, float(cfg.get("vp_horizon_soft_cap_steps", 8.0) or 8.0))
    base = float(baseline_horizon_steps) if isinstance(baseline_horizon_steps, (int, float)) else horizon_cap
    projected = max(0.0, min(horizon_cap, float(base) - max(0.0, float(vp_progress_delta))))
    signal = _clamp01((horizon_cap - float(projected)) / horizon_cap)
    centered = max(-1.0, min(1.0, (2.0 * float(signal)) - 1.0))
    component = float(weight * centered)
    return component, float(projected), float(signal), "progress_projection"


def _choose_candidate_action(
    candidate_actions: list[dict],
    score_epsilon: float,
    q_root_score_spread: float = 0.0,
    q_flat_spread_epsilon: float = 1e-6,
    flat_q_score_epsilon: float = 0.02,
    flat_q_vp_min_progress: float = 0.0,
) -> tuple[str, str, dict]:
    if not candidate_actions:
        return "", "none", {}
    eps = max(0.0, float(score_epsilon))
    ranked = sorted(
        candidate_actions,
        key=lambda c: (
            -float(c.get("final_score", 0.0) or 0.0),
            str(c.get("action_id", "")),
        ),
    )
    best = dict(ranked[0])
    tied = [
        dict(c)
        for c in ranked
        if abs(float(c.get("final_score", 0.0) or 0.0) - float(best.get("final_score", 0.0) or 0.0))
        <= eps
    ]
    if len(tied) <= 1:
        best_score = float(best.get("final_score", 0.0) or 0.0)
        close_eps = max(float(eps), float(flat_q_score_epsilon))
        close = [
            dict(c)
            for c in ranked
            if (best_score - float(c.get("final_score", 0.0) or 0.0)) <= close_eps
        ]
        q_spread = max(0.0, float(q_root_score_spread))
        if q_spread <= max(0.0, float(q_flat_spread_epsilon)) and len(close) > 1:
            vp_candidates = [
                dict(c)
                for c in close
                if float(c.get("vp_progress_delta", 0.0) or 0.0) > float(flat_q_vp_min_progress)
            ]
            if vp_candidates:
                vp_sorted = sorted(
                    vp_candidates,
                    key=lambda c: (
                        -float(c.get("vp_progress_delta", 0.0) or 0.0),
                        -float(c.get("final_score", 0.0) or 0.0),
                        str(c.get("action_id", "")),
                    ),
                )
                selected = dict(vp_sorted[0])
                return str(selected.get("action_id", "")), "vp_progress_flat_q_override", {
                    "score_epsilon": float(eps),
                    "flat_q_score_epsilon": float(close_eps),
                    "q_root_score_spread": float(q_spread),
                    "q_flat_spread_epsilon": float(q_flat_spread_epsilon),
                    "flat_q_vp_min_progress": float(flat_q_vp_min_progress),
                    "close_action_ids": [str(c.get("action_id", "")) for c in close],
                    "selected_vp_progress_delta": float(selected.get("vp_progress_delta", 0.0) or 0.0),
                }
        return str(best.get("action_id", "")), "none", {
            "score_epsilon": float(eps),
            "flat_q_score_epsilon": float(close_eps),
            "q_root_score_spread": float(q_spread),
            "q_flat_spread_epsilon": float(q_flat_spread_epsilon),
            "flat_q_vp_min_progress": float(flat_q_vp_min_progress),
            "score_gap_vs_runner_up": (
                float(best.get("final_score", 0.0) or 0.0)
                - float(ranked[1].get("final_score", 0.0) or 0.0)
                if len(ranked) > 1
                else 0.0
            ),
        }
    tied_sorted = sorted(
        tied,
        key=lambda c: (
            -float(c.get("vp_progress_delta", 0.0) or 0.0),
            str(c.get("action_id", "")),
        ),
    )
    selected = dict(tied_sorted[0])
    return str(selected.get("action_id", "")), "vp_progress_tiebreak", {
        "score_epsilon": float(eps),
        "tied_action_ids": [str(c.get("action_id", "")) for c in tied_sorted],
        "selected_vp_progress_delta": float(selected.get("vp_progress_delta", 0.0) or 0.0),
        "max_tied_vp_progress_delta": float(tied_sorted[0].get("vp_progress_delta", 0.0) or 0.0),
    }


def _decision_ranked_candidates(
    *,
    candidate_actions: list[dict],
    tiebreak_path: str,
    tiebreak_meta: dict,
    score_epsilon: float,
    flat_q_score_epsilon: float,
) -> list[dict]:
    rows = [dict(c or {}) for c in list(candidate_actions or [])]
    if not rows:
        return []
    eps = max(float(score_epsilon or 0.0), 0.0)
    close_eps = max(eps, float(flat_q_score_epsilon or 0.0))
    best_score = max([float(r.get("final_score", 0.0) or 0.0) for r in rows], default=0.0)
    tied_ids = {str(a) for a in list((dict(tiebreak_meta or {})).get("tied_action_ids", []) or [])}
    close_ids = {str(a) for a in list((dict(tiebreak_meta or {})).get("close_action_ids", []) or [])}
    mode = str(tiebreak_path or "none")

    def _key(row: dict) -> tuple:
        aid = str(row.get("action_id", ""))
        final_score = float(row.get("final_score", 0.0) or 0.0)
        visit_count = int(row.get("visit_count", 0) or 0)
        vp_progress = float(row.get("vp_progress_delta", 0.0) or 0.0)
        if mode == "vp_progress_tiebreak":
            is_tied = (aid in tied_ids) or (abs(final_score - float(best_score)) <= eps)
            return (0 if is_tied else 1, -vp_progress, -final_score, -visit_count, aid)
        if mode == "vp_progress_flat_q_override":
            is_close = (aid in close_ids) or ((float(best_score) - final_score) <= close_eps)
            return (0 if is_close else 1, -vp_progress, -final_score, -visit_count, aid)
        return (-final_score, -visit_count, aid)

    sorted_rows = sorted(rows, key=_key)
    rank_by_id = {str(r.get("action_id", "")): int(i + 1) for i, r in enumerate(sorted_rows)}
    for row in rows:
        aid = str(row.get("action_id", ""))
        row["decision_rank"] = int(rank_by_id.get(aid, len(rows)))
        row["real_decision_score"] = float(row.get("final_score", 0.0) or 0.0)
        row["decision_criterion"] = str(mode if mode else "none")
        row["decision_components"] = {
            "visit_count": int(row.get("visit_count", 0) or 0),
            "q_value": (
                float(row.get("mcts_q_value"))
                if row.get("mcts_q_value", None) is not None
                else None
            ),
            "u_value": (
                float(row.get("mcts_u_value"))
                if row.get("mcts_u_value", None) is not None
                else None
            ),
            "success_prob_proxy": (
                float(row.get("mcts_success_prob_proxy"))
                if row.get("mcts_success_prob_proxy", None) is not None
                else None
            ),
            "success_component": (
                float(row.get("mcts_success_component"))
                if row.get("mcts_success_component", None) is not None
                else None
            ),
            "puct_score": (
                float(row.get("mcts_puct_score"))
                if row.get("mcts_puct_score", None) is not None
                else None
            ),
            "policy_prior": (
                float(row.get("policy_prior"))
                if row.get("policy_prior", None) is not None
                else None
            ),
            "tie_break_term": (
                float(row.get("vp_progress_delta"))
                if row.get("vp_progress_delta", None) is not None
                else None
            ),
            "tie_break_source": str(row.get("vp_progress_source", "unknown") or "unknown"),
            "vp_horizon_steps": (
                float(row.get("vp_horizon_steps"))
                if row.get("vp_horizon_steps", None) is not None
                else None
            ),
            "vp_horizon_signal": (
                float(row.get("vp_horizon_signal"))
                if row.get("vp_horizon_signal", None) is not None
                else None
            ),
            "vp_horizon_component": (
                float(row.get("vp_horizon_component"))
                if row.get("vp_horizon_component", None) is not None
                else None
            ),
            "vp_horizon_source": str(row.get("vp_horizon_source", "unknown") or "unknown"),
            "enemy_can_capture_vp_next": row.get("enemy_can_capture_vp_next"),
            "enemy_min_steps_to_vp": row.get("enemy_min_steps_to_vp"),
            "enemy_threat_component": float(row.get("enemy_threat_component", 0.0) or 0.0),
            "enemy_threat_proximity_signal": float(row.get("enemy_threat_proximity_signal", 0.0) or 0.0),
            "enemy_threat_source": str(row.get("enemy_threat_source", "unknown") or "unknown"),
            "mobility_opportunity_cost_component": float(row.get("mobility_opportunity_cost_component", 0.0) or 0.0),
            "mobility_opportunity_cost_signal": float(row.get("mobility_opportunity_cost_signal", 0.0) or 0.0),
            "mobility_opportunity_cost_source": str(row.get("mobility_opportunity_cost_source", "unknown") or "unknown"),
            "cross_unit_synergy_component": float(row.get("cross_unit_synergy_component", 0.0) or 0.0),
            "cross_unit_synergy_signal": float(row.get("cross_unit_synergy_signal", 0.0) or 0.0),
            "cross_unit_synergy_source": str(row.get("cross_unit_synergy_source", "unknown") or "unknown"),
        }
    return rows


def _priors_and_values(model, obs_encoded, legal_actions: list[str], action_dim: int):
    if model is None or not legal_actions:
        return None, None, {}
    model_device = next(model.parameters()).device
    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = obs_encoded.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([obs_encoded], dtype=torch.float32, device=model_device)
        _, policy_logits, value_root, _ = model.initial_inference(obs_tensor)
        logits = policy_logits[0]
        idx = [_action_id_to_index(a, action_dim) for a in legal_actions]
        idx_t = torch.tensor(idx, dtype=torch.long, device=model_device)
        legal_logits = torch.index_select(logits, dim=0, index=idx_t).to(torch.float32)
        probs = torch.softmax(legal_logits, dim=0).detach().cpu().tolist()
        priors = {a: float(p) for a, p in zip(legal_actions, probs)}
        # Producer-first contract: initial_inference provides only a root state-value.
        # Do not broadcast that scalar across actions as pseudo action-conditional values.
        values = None
        return priors, values, {
            "latent_top_indices": [],
            "latent_top_values": [],
            "predicted_value_root": float(value_root[0, 0].item()),
            "mcts_action_value_source": "root_only_no_broadcast",
            "mcts_action_value_fallback_expected": True,
        }


class SelfplayBackend(Protocol):
    def play_episode(self, **kwargs: Any) -> list:
        ...


class _NativeEZV2SelfplayBackend:
    def play_episode(self, **kwargs: Any) -> list:
        return list(self._play_episode(**kwargs))

    def _play_episode(
        self,
        adapter,
        scenario_id: str,
        seed: int,
        max_steps: int = 100,
        max_steps_override: int = 0,
        max_turns_override: int = 0,
        action_dim: int = DEFAULT_ACTION_DIM,
        model=None,
        mcts_simulations: int = 32,
        mcts_c_puct: float = 1.5,
        mcts_temperature: float = 1.0,
        mcts_dirichlet_alpha: float = 0.3,
        mcts_dirichlet_epsilon: float = 0.0,
        mcts_q_clip_abs: float = 10.0,
        mcts_q_root_normalization_mode: str = "adaptive_minmax",
        mcts_q_root_normalization_strength: float = 0.35,
        mcts_chance_mode: str = "off",
        mcts_chance_samples_per_expansion: int = 1,
        mcts_chance_value_noise_std: float = 0.0,
        mcts_success_prob_enabled: bool = False,
        mcts_success_prob_alpha: float = 0.0,
        mcts_success_prob_center: float = 0.5,
        mcts_success_prob_scale: float = 0.5,
        mcts_success_prob_centered_clip_abs: float = 1.0,
        mcts_min_root_visits_per_action: int = 0,
        mcts_min_root_visits_top_n: int = 0,
        mcts_value_rescale_mode: str = "tanh",
        mcts_value_rescale_temperature: float = 10.0,
        mcts_success_prob_expected_damage_scale: float = 4.0,
        mcts_vp_tiebreak_epsilon: float = 0.01,
        mcts_q_flat_spread_epsilon: float = 1e-6,
        mcts_vp_flat_q_score_epsilon: float = 0.02,
        mcts_vp_flat_q_min_progress: float = 0.0,
        timeout_penalty: float = -0.1,
        reward_shaping: dict | None = None,
        objective_opportunity_near_vp_max_dist: float = 2.0,
        enemy_can_capture_vp_next_default: int = 0,
        enemy_min_steps_to_vp_default: float = 99.0,
        enemy_threat_component_default: float = 0.0,
        mobility_opportunity_cost_component_default: float = 0.0,
        cross_unit_synergy_component_default: float = 0.0,
        unit_prefilter_enabled: bool = False,
        unit_prefilter_replan_enabled: bool = False,
        unit_prefilter_top_k: int = 1,
        unit_prefilter_vp_progress_weight: float = 1.0,
        unit_prefilter_capture_opportunity_weight: float = 2.0,
        unit_prefilter_threat_weight: float = 0.25,
        matchup_modes: list[str] | None = None,
        matchup_mode_weights: dict | None = None,
        procedural_terrain_mutation_prob: float = 0.0,
        procedural_unit_jitter_prob: float = 0.0,
        procedural_asymmetric_strength_jitter: float = 0.0,
        **_: Any,
    ) -> list:
        def _normalize_mode(raw: object) -> str:
            m = str(raw or "").strip().lower()
            if m in {"self_vs_self", "self_self", "self"}:
                return "self_vs_self"
            if m in {"self_vs_random", "self_random", "random"}:
                return "self_vs_random"
            return "self_vs_self"

        def _resolve_episode_mode(seed_val: int) -> str:
            modes_raw = list(matchup_modes or []) or ["self_vs_self"]
            weights_raw = dict(matchup_mode_weights or {})
            expanded: list[str] = []
            for mode_raw in modes_raw:
                mode = _normalize_mode(mode_raw)
                w = int(weights_raw.get(mode_raw, weights_raw.get(mode, 1)) or 1)
                for _i in range(max(1, w)):
                    expanded.append(mode)
            if not expanded:
                expanded = ["self_vs_self"]
            return str(expanded[int(abs(int(seed_val))) % int(len(expanded))])

        def _resolve_policy_by_side(obs_obj, seed_val: int) -> tuple[str, dict[str, str]]:
            mode = _resolve_episode_mode(seed_val)
            sides = sorted(
                {
                    str((u or {}).get("side", "")).strip()
                    for u in list(getattr(obs_obj, "units", []) or [])
                    if str((u or {}).get("side", "")).strip()
                }
            )
            policy_map: dict[str, str] = {str(s): "mcts" for s in sides}
            if mode == "self_vs_random" and sides:
                random_side = str(sides[int(abs(int(seed_val))) % int(len(sides))])
                policy_map[random_side] = "random"
            return mode, policy_map

        samples = []
        if (
            procedural_terrain_mutation_prob > 0.0
            or procedural_unit_jitter_prob > 0.0
            or procedural_asymmetric_strength_jitter > 0.0
        ):
            try:
                obs = adapter.initial_state(
                    scenario_id=str(scenario_id),
                    seed=int(seed),
                    terrain_mutation_prob=float(procedural_terrain_mutation_prob),
                    unit_jitter_prob=float(procedural_unit_jitter_prob),
                    asymmetric_strength_jitter=float(procedural_asymmetric_strength_jitter),
                )
            except TypeError:
                obs = adapter.initial_state(scenario_id=str(scenario_id), seed=int(seed))
        else:
            obs = adapter.initial_state(scenario_id=str(scenario_id), seed=int(seed))
        episode_matchup_mode, episode_policy_by_side = _resolve_policy_by_side(obs, int(seed))
        unit_count = len(getattr(obs, "units", []) or [])
        scenario_turn_limit = _scenario_turn_limit_from_adapter(adapter)
        effective_max_steps, budget_source = resolve_effective_step_budget(
            max_steps=int(max_steps),
            max_steps_override=int(max_steps_override),
            max_turns_override=int(max_turns_override),
            unit_count=int(unit_count),
            scenario_turn_limit=int(scenario_turn_limit),
        )
        sustained_advantage_turns_by_side: dict[str, int] = {}
        pending_setup_strength_by_side: dict[str, float] = {}

        macro_planner = MacroStrategyPlanner()
        activated_units_by_side_turn: dict[tuple[str, int], set[str]] = {}
        for step_idx in range(max(1, effective_max_steps)):
            global_legal = list(adapter.legal_actions() or [])
            if not global_legal:
                break
            turn_now = int(getattr(obs, "turn", 0) or 0)
            side_now = _normalize_side(str(getattr(obs, "to_play", "") or ""))
            macro_plan = macro_planner.compute_macro_plan(obs)
            legal_reaction_options = sum(1 for a in global_legal if str(a).upper().startswith("OPPORTUNITY_"))
            legal_capture_options = _count_capture_options(global_legal, dict(getattr(obs, "vp_owner_by_hex", {}) or {}), str(getattr(obs, "to_play", "") or ""))
            if str(getattr(model, "encoder_type", "mlp")) == "cnn":
                obs_encoded = _observation_to_tensor(
                    obs,
                    channels=int(getattr(model, "observation_channels", DEFAULT_OBS_CHANNELS)) if model is not None else DEFAULT_OBS_CHANNELS,
                    height=int(getattr(model, "observation_height", DEFAULT_OBS_HEIGHT)) if model is not None else DEFAULT_OBS_HEIGHT,
                    width=int(getattr(model, "observation_width", DEFAULT_OBS_WIDTH)) if model is not None else DEFAULT_OBS_WIDTH,
                )
            else:
                obs_encoded = _observation_to_vector(obs)
            unit_prefilter_active = False
            unit_prefilter_selected_unit_id = ""
            unit_prefilter_candidate_ranking: list[dict] = []
            unit_prefilter_global_candidate_count = int(len(global_legal))
            legal = list(global_legal)
            step_units = [dict(u or {}) for u in list(getattr(obs, "units", []) or []) if isinstance(u, dict)]
            step_units_by_id, step_units_by_pos = _build_unit_indexes(step_units)
            unit_prefilter_requested = bool(unit_prefilter_enabled) or bool(unit_prefilter_replan_enabled)
            precomputed_plan: dict[str, object] = {}
            if unit_prefilter_requested:
                activated_now = set(activated_units_by_side_turn.get((str(side_now), int(turn_now)), set()))
                pending_non_opportunity_actions = [
                    str(a)
                    for a in list(global_legal or [])
                    if _action_consumes_unit_activation(str(a))
                    and str(_parse_action_id(str(a))[1] or "").strip()
                    and str(_parse_action_id(str(a))[1] or "").strip() not in activated_now
                ]
                prefilter_legal_pool = (
                    list(pending_non_opportunity_actions)
                    if pending_non_opportunity_actions
                    else list(global_legal)
                )
                if bool(unit_prefilter_replan_enabled):
                    units_for_rank = [dict(u or {}) for u in list(getattr(obs, "units", []) or []) if isinstance(u, dict)]
                    vp_hexes_for_rank = [dict(vp or {}) for vp in list(getattr(obs, "vp_hexes", []) or []) if isinstance(vp, dict)]
                    vp_owner_for_rank = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
                    terrain_cover_for_rank = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
                    terrain_los_for_rank = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
                    unit_prefilter_selected_unit_id, selected_actions, ranking_rows = _unit_prefilter_ranking(
                        legal_actions=list(prefilter_legal_pool),
                        units=list(units_for_rank),
                        vp_hexes=list(vp_hexes_for_rank),
                        vp_owner_by_hex=dict(vp_owner_for_rank),
                        to_play=str(getattr(obs, "to_play", "") or ""),
                        terrain_cover_by_hex=dict(terrain_cover_for_rank),
                        terrain_los_block_by_hex=dict(terrain_los_for_rank),
                        top_k=int(max(1, unit_prefilter_top_k)),
                        vp_progress_weight=float(unit_prefilter_vp_progress_weight),
                        capture_opportunity_weight=float(unit_prefilter_capture_opportunity_weight),
                        threat_weight=float(unit_prefilter_threat_weight),
                    )
                    unit_prefilter_candidate_ranking = list(ranking_rows or [])
                    actions_by_unit: dict[str, list[str]] = {}
                    for action_id in list(prefilter_legal_pool or []):
                        _kind_probe, actor_probe = _parse_action_id(str(action_id))
                        actor_probe = str(actor_probe or "").strip()
                        if not actor_probe:
                            continue
                        actions_by_unit.setdefault(actor_probe, []).append(str(action_id))
                    ranked_unit_ids = [
                        str(r.get("unit_id", "")).strip()
                        for r in list(unit_prefilter_candidate_ranking or [])
                        if str(r.get("unit_id", "")).strip()
                    ]
                    if not ranked_unit_ids and unit_prefilter_selected_unit_id:
                        ranked_unit_ids = [str(unit_prefilter_selected_unit_id)]
                    best_plan = None
                    # Use full simulation budget per replanned unit so train/eval
                    # does not collapse to tiny per-unit trees when many units
                    # are considered.
                    per_unit_sims = max(8, int(mcts_simulations))
                    for uid in ranked_unit_ids:
                        unit_actions = list(actions_by_unit.get(str(uid), []) or [])
                        if not unit_actions:
                            continue
                        priors_u, values_u, xai_u = _priors_and_values(model, obs_encoded, unit_actions, int(action_dim))
                        priors_u = macro_planner.modulate_priors(
                            priors_u,
                            macro_plan,
                            unit_actions,
                            dict(getattr(obs, "vp_owner_by_hex", {}) or {}),
                            str(getattr(obs, "to_play", "") or ""),
                        )
                        success_prob_by_action_u: dict[str, float] = {}
                        expected_damage_by_action_u: dict[str, float] = {}
                        success_damage_scale_u = max(1e-6, float(mcts_success_prob_expected_damage_scale))
                        for aid in list(unit_actions or []):
                            action_kind_probe_u, _ = _parse_action_id(str(aid))
                            expected_damage_u = float(
                                _candidate_expected_damage(
                                    action_id=str(aid),
                                    units=list(step_units),
                                    terrain_cover_by_hex=dict(getattr(obs, "terrain_cover_by_hex", {}) or {}),
                                    terrain_los_block_by_hex=dict(getattr(obs, "terrain_los_block_by_hex", {}) or {}),
                                    units_by_id=dict(step_units_by_id),
                                    units_by_pos=dict(step_units_by_pos),
                                )
                            )
                            expected_damage_by_action_u[str(aid)] = float(expected_damage_u)
                            if _is_attack_like_action(action_kind_probe_u):
                                success_prob_by_action_u[str(aid)] = _clamp01(expected_damage_u / success_damage_scale_u)
                            else:
                                success_prob_by_action_u[str(aid)] = 0.5
                        mcts_u = run_mcts_puct(
                            legal_actions=unit_actions,
                            num_simulations=int(per_unit_sims),
                            c_puct=float(mcts_c_puct),
                            priors_by_action=priors_u,
                            values_by_action=values_u,
                            temperature=float(mcts_temperature),
                            dirichlet_alpha=float(mcts_dirichlet_alpha),
                            dirichlet_epsilon=float(mcts_dirichlet_epsilon),
                            q_clip_abs=float(mcts_q_clip_abs),
                            q_root_normalization_mode=str(mcts_q_root_normalization_mode),
                            q_root_normalization_strength=float(mcts_q_root_normalization_strength),
                            chance_mode=str(mcts_chance_mode),
                            chance_samples_per_expansion=int(mcts_chance_samples_per_expansion),
                            chance_value_noise_std=float(mcts_chance_value_noise_std),
                            success_prob_by_action=dict(success_prob_by_action_u),
                            success_prob_enabled=bool(mcts_success_prob_enabled),
                            success_prob_alpha=float(mcts_success_prob_alpha),
                            success_prob_center=float(mcts_success_prob_center),
                            success_prob_scale=float(mcts_success_prob_scale),
                            success_prob_centered_clip_abs=float(mcts_success_prob_centered_clip_abs),
                            min_root_visits_per_action=int(mcts_min_root_visits_per_action),
                            min_root_visits_top_n=int(mcts_min_root_visits_top_n),
                            value_rescale_mode=str(mcts_value_rescale_mode),
                            value_rescale_temperature=float(mcts_value_rescale_temperature),
                        )
                        chosen_u = str(mcts_u.chosen_action or "")
                        breakdown_u = {
                            str(row.get("action_id", "")): dict(row)
                            for row in list(getattr(mcts_u, "root_candidate_breakdown", []) or [])
                            if isinstance(row, dict)
                        }
                        chosen_breakdown_u = dict(breakdown_u.get(chosen_u, {}) or {})
                        chosen_score_u = float(chosen_breakdown_u.get("puct_score", 0.0) or 0.0)
                        chosen_visits_u = 0
                        chosen_prob_u = 0.0
                        for aid_u, vis_u, prob_u in zip(
                            list(getattr(mcts_u, "actions", []) or []),
                            list(getattr(mcts_u, "visits", []) or []),
                            list(getattr(mcts_u, "probs", []) or []),
                        ):
                            if str(aid_u) != chosen_u:
                                continue
                            chosen_visits_u = int(vis_u or 0)
                            chosen_prob_u = float(prob_u or 0.0)
                            break
                        plan_key = (float(chosen_score_u), int(chosen_visits_u), float(chosen_prob_u), str(uid))
                        if best_plan is None or plan_key > best_plan["plan_key"]:
                            best_plan = {
                                "plan_key": plan_key,
                                "unit_id": str(uid),
                                "legal": list(unit_actions),
                                "priors": dict(priors_u or {}),
                                "values": dict(values_u or {}),
                                "xai": dict(xai_u or {}),
                                "mcts": mcts_u,
                                "success_prob_by_action": dict(success_prob_by_action_u),
                                "expected_damage_by_action": dict(expected_damage_by_action_u),
                            }
                    if best_plan is not None:
                        unit_prefilter_selected_unit_id = str(best_plan.get("unit_id", "") or "")
                        legal = list(best_plan.get("legal", []) or list(global_legal))
                        unit_prefilter_active = bool(len(legal) > 0)
                        precomputed_plan = dict(best_plan)
                    else:
                        unit_prefilter_selected_unit_id, selected_actions = _select_prefilter_unit_simple(
                            legal_actions=list(prefilter_legal_pool),
                        )
                        if selected_actions:
                            legal = list(selected_actions)
                            unit_prefilter_active = True
                        else:
                            legal = list(global_legal)
                else:
                    unit_prefilter_selected_unit_id, selected_actions = _select_prefilter_unit_simple(
                        legal_actions=list(prefilter_legal_pool),
                    )
                    if selected_actions:
                        legal = list(selected_actions)
                        unit_prefilter_active = True
                    else:
                        legal = list(global_legal)
            if precomputed_plan:
                priors = dict(precomputed_plan.get("priors", {}) or {})
                values = dict(precomputed_plan.get("values", {}) or {})
                xai = dict(precomputed_plan.get("xai", {}) or {})
            else:
                priors, values, xai = _priors_and_values(model, obs_encoded, legal, int(action_dim))
                priors = macro_planner.modulate_priors(
                    priors,
                    macro_plan,
                    legal,
                    dict(getattr(obs, "vp_owner_by_hex", {}) or {}),
                    str(getattr(obs, "to_play", "") or ""),
                )
            success_prob_by_action: dict[str, float] = {}
            expected_damage_by_action: dict[str, float] = {}
            success_damage_scale = max(1e-6, float(mcts_success_prob_expected_damage_scale))
            if precomputed_plan:
                success_prob_by_action = dict(precomputed_plan.get("success_prob_by_action", {}) or {})
                expected_damage_by_action = dict(precomputed_plan.get("expected_damage_by_action", {}) or {})
                mcts = precomputed_plan.get("mcts")
            else:
                for aid in list(legal or []):
                    action_kind_probe, _ = _parse_action_id(str(aid))
                    expected_damage = float(
                        _candidate_expected_damage(
                            action_id=str(aid),
                            units=list(step_units),
                            terrain_cover_by_hex=dict(getattr(obs, "terrain_cover_by_hex", {}) or {}),
                            terrain_los_block_by_hex=dict(getattr(obs, "terrain_los_block_by_hex", {}) or {}),
                            units_by_id=dict(step_units_by_id),
                            units_by_pos=dict(step_units_by_pos),
                        )
                    )
                    expected_damage_by_action[str(aid)] = float(expected_damage)
                    if _is_attack_like_action(action_kind_probe):
                        success_prob_by_action[str(aid)] = _clamp01(expected_damage / success_damage_scale)
                    else:
                        # Neutral for non-attack actions; centered term resolves to ~0 by default.
                        success_prob_by_action[str(aid)] = 0.5
                mcts = run_mcts_puct(
                    legal_actions=legal,
                    num_simulations=int(mcts_simulations),
                    c_puct=float(mcts_c_puct),
                    priors_by_action=priors,
                    values_by_action=values,
                    temperature=float(mcts_temperature),
                    dirichlet_alpha=float(mcts_dirichlet_alpha),
                    dirichlet_epsilon=float(mcts_dirichlet_epsilon),
                    q_clip_abs=float(mcts_q_clip_abs),
                    q_root_normalization_mode=str(mcts_q_root_normalization_mode),
                    q_root_normalization_strength=float(mcts_q_root_normalization_strength),
                    chance_mode=str(mcts_chance_mode),
                    chance_samples_per_expansion=int(mcts_chance_samples_per_expansion),
                    chance_value_noise_std=float(mcts_chance_value_noise_std),
                    success_prob_by_action=dict(success_prob_by_action),
                    success_prob_enabled=bool(mcts_success_prob_enabled),
                    success_prob_alpha=float(mcts_success_prob_alpha),
                    success_prob_center=float(mcts_success_prob_center),
                    success_prob_scale=float(mcts_success_prob_scale),
                    success_prob_centered_clip_abs=float(mcts_success_prob_centered_clip_abs),
                    min_root_visits_per_action=int(mcts_min_root_visits_per_action),
                    min_root_visits_top_n=int(mcts_min_root_visits_top_n),
                    value_rescale_mode=str(mcts_value_rescale_mode),
                    value_rescale_temperature=float(mcts_value_rescale_temperature),
                )
            sorted_probs = sorted([float(p) for p in list(mcts.probs or [])], reverse=True)
            mcts_margin = float((sorted_probs[0] if sorted_probs else 0.0) - (sorted_probs[1] if len(sorted_probs) > 1 else 0.0))
            mcts_chosen = str(mcts.chosen_action)
            action_kind, unit_id = _parse_action_id(mcts_chosen)
            side = ""
            acting_q: int | None = None
            acting_r: int | None = None
            for u in list(getattr(obs, "units", []) or []):
                if str(u.get("unit_id", "")) == str(unit_id):
                    side = str(u.get("side", "") or "")
                    acting_q = int(u.get("q")) if isinstance(u.get("q"), int) else None
                    acting_r = int(u.get("r")) if isinstance(u.get("r"), int) else None
                    break
            before_vp = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
            best_vp_q, best_vp_r = _best_enemy_vp_qr_for_side(
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=before_vp,
                best_vp_id="",
            )
            candidate_actions = []
            mcts_breakdown_by_action = {
                str(row.get("action_id", "")): dict(row)
                for row in list(getattr(mcts, "root_candidate_breakdown", []) or [])
                if isinstance(row, dict)
            }
            mcts_visits_by_action = {
                str(aid): int(visits)
                for aid, visits in zip(list(getattr(mcts, "actions", []) or []), list(getattr(mcts, "visits", []) or []))
            }
            objective_baseline_before, _, _ = objective_min_distance_snapshot(
                units=list(getattr(obs, "units", []) or []),
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=before_vp,
            )
            obs_reachable_hex_mask_by_unit = _obs_reachable_hex_mask_by_unit(list(global_legal or []))
            obs_attackable_hex_mask_by_unit = _obs_attackable_hex_mask_by_unit(list(global_legal or []))
            obs_enemy_vp_threat_map = _obs_enemy_vp_threat_map(
                units=list(getattr(obs, "units", []) or []),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=dict(before_vp),
                actor_side=str(side),
                threat_radius=int(
                    dict(reward_shaping or {}).get("obs_enemy_vp_threat_radius", 6)
                    or 6
                ),
            )
            obs_enemy_reaction_fire_risk = _obs_enemy_reaction_fire_risk(
                legal_actions=list(global_legal or []),
                units=list(getattr(obs, "units", []) or []),
                actor_side=str(side),
            )
            obs_vp_ownership_ttl = _obs_vp_ownership_ttl(
                units=list(getattr(obs, "units", []) or []),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=dict(before_vp),
                ttl_cap=int(dict(reward_shaping or {}).get("obs_vp_ownership_ttl_cap", 8) or 8),
            )
            step_enemy_can_capture_vp_next, step_enemy_min_steps_to_vp = _safe_enemy_threat_defaults(
                can_capture_default=int(enemy_can_capture_vp_next_default),
                min_steps_default=float(enemy_min_steps_to_vp_default),
            )
            vp_best_action_id = ""
            vp_best_progress = None
            unit_best_vp_progress_by_unit: dict[str, float] = {}
            for aid, prob in zip(list(mcts.actions or []), list(mcts.probs or [])):
                mcts_row = dict(mcts_breakdown_by_action.get(str(aid), {}) or {})
                prior_raw = None
                if isinstance(priors, dict):
                    prior_raw = priors.get(str(aid), None)
                try:
                    policy_prior = (
                        float(prior_raw)
                        if prior_raw is not None
                        else float(prob)
                    )
                except Exception:
                    policy_prior = float(prob)
                candidate_vp_owner = dict(before_vp)
                if "CAPTURE" in str(_parse_action_id(str(aid))[0]).upper():
                    tq, tr = _action_target_qr(str(aid))
                    if isinstance(tq, int) and isinstance(tr, int):
                        candidate_vp_owner[f"{int(tq)},{int(tr)}"] = str(side)
                vp_delta, source = _candidate_vp_progress_delta(
                    action_id=str(aid),
                    acting_q=acting_q,
                    acting_r=acting_r,
                    best_vp_q=best_vp_q,
                    best_vp_r=best_vp_r,
                    fallback_progress_delta=None,
                    legal_capture_options=int(legal_capture_options),
                )
                vp_target_id, vp_distance_after, vp_distance_source = _candidate_vp_target_after(
                    action_id=str(aid),
                    side=str(side),
                    vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                    vp_owner_by_hex=dict(candidate_vp_owner),
                    acting_q=acting_q,
                    acting_r=acting_r,
                )
                row = {
                    "action_id": str(aid),
                    "policy_prior": float(policy_prior),
                    "visit_policy_prob": float(prob),
                    "policy_prior_source": "policy_head_prior",
                    "policy_prior_available": True,
                    "final_score": float(prob),
                    "visit_count": int(mcts_visits_by_action.get(str(aid), 0)),
                    "vp_progress_delta": float(vp_delta) if vp_delta is not None else None,
                    "vp_progress_source": str(source or "unknown"),
                    "vp_target_id": str(vp_target_id),
                    "vp_target_source": str(vp_distance_source or "unknown"),
                    "vp_distance_after": (
                        float(vp_distance_after)
                        if isinstance(vp_distance_after, (int, float))
                        else None
                    ),
                    "vp_distance_source": str(vp_distance_source or "unknown"),
                    "expected_damage_proxy": float(
                        expected_damage_by_action.get(str(aid), 0.0)
                    ),
                    "mcts_q_value": (
                        float(mcts_row.get("q_value"))
                        if mcts_row.get("q_value", None) is not None
                        else None
                    ),
                    "mcts_q_unclipped": (
                        float(mcts_row.get("q_unclipped"))
                        if mcts_row.get("q_unclipped", None) is not None
                        else None
                    ),
                    "mcts_q_clipped": (
                        float(mcts_row.get("q_clipped"))
                        if mcts_row.get("q_clipped", None) is not None
                        else None
                    ),
                    "mcts_q_norm_applied": bool(mcts_row.get("q_norm_applied", False)),
                    "mcts_q_value_source": "mcts_root_candidate_breakdown",
                    "mcts_q_value_available": bool(mcts_row.get("q_value", None) is not None),
                    "mcts_u_value": (
                        float(mcts_row.get("u_value"))
                        if mcts_row.get("u_value", None) is not None
                        else None
                    ),
                    "mcts_u_value_source": "mcts_root_candidate_breakdown",
                    "mcts_u_value_available": bool(mcts_row.get("u_value", None) is not None),
                    "mcts_success_prob_proxy": (
                        float(mcts_row.get("success_prob_proxy"))
                        if mcts_row.get("success_prob_proxy", None) is not None
                        else (
                            float(success_prob_by_action.get(str(aid)))
                            if success_prob_by_action.get(str(aid), None) is not None
                            else None
                        )
                    ),
                    "mcts_success_prob_proxy_source": (
                        "mcts_root_candidate_breakdown"
                        if mcts_row.get("success_prob_proxy", None) is not None
                        else (
                            "success_prob_by_action"
                            if success_prob_by_action.get(str(aid), None) is not None
                            else "missing"
                        )
                    ),
                    "mcts_success_prob_proxy_available": bool(
                        mcts_row.get("success_prob_proxy", None) is not None
                        or success_prob_by_action.get(str(aid), None) is not None
                    ),
                    "mcts_success_prob_centered": float(mcts_row.get("success_prob_centered", 0.0) or 0.0),
                    "mcts_success_component": (
                        float(mcts_row.get("success_component"))
                        if mcts_row.get("success_component", None) is not None
                        else None
                    ),
                    "mcts_success_component_source": (
                        "mcts_root_candidate_breakdown"
                        if mcts_row.get("success_component", None) is not None
                        else "missing"
                    ),
                    "mcts_success_component_available": bool(
                        mcts_row.get("success_component", None) is not None
                    ),
                    "mcts_puct_score": (
                        float(mcts_row.get("puct_score"))
                        if mcts_row.get("puct_score", None) is not None
                        else None
                    ),
                }
                enemy_can_capture_vp_next, enemy_min_steps_to_vp = _enemy_threat_signals(
                    actor_side=str(side),
                    units=list(getattr(obs, "units", []) or []),
                    vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                    vp_owner_by_hex=dict(candidate_vp_owner),
                )
                enemy_threat_component, enemy_threat_proximity_signal, enemy_threat_source = _enemy_threat_component(
                    reward_shaping=dict(reward_shaping or {}),
                    enemy_can_capture_vp_next=enemy_can_capture_vp_next,
                    enemy_min_steps_to_vp=enemy_min_steps_to_vp,
                )
                row["enemy_can_capture_vp_next"] = (
                    int(enemy_can_capture_vp_next)
                    if enemy_can_capture_vp_next is not None
                    else int(enemy_can_capture_vp_next_default)
                )
                row["enemy_min_steps_to_vp"] = (
                    float(enemy_min_steps_to_vp)
                    if isinstance(enemy_min_steps_to_vp, (int, float))
                    else float(enemy_min_steps_to_vp_default)
                )
                row["enemy_threat_component"] = (
                    float(enemy_threat_component)
                    if str(enemy_threat_source) != "unavailable"
                    else float(enemy_threat_component_default)
                )
                row["enemy_threat_proximity_signal"] = float(enemy_threat_proximity_signal)
                row["enemy_threat_source"] = str(enemy_threat_source)
                row["obs_enemy_vp_threat_map"] = dict(obs_enemy_vp_threat_map)
                row["obs_reachable_hex_mask_by_unit"] = dict(obs_reachable_hex_mask_by_unit)
                row["obs_attackable_hex_mask_by_unit"] = dict(obs_attackable_hex_mask_by_unit)
                row["obs_enemy_reaction_fire_risk"] = float(obs_enemy_reaction_fire_risk)
                row["obs_vp_ownership_ttl"] = dict(obs_vp_ownership_ttl)
                if vp_delta is not None:
                    vp_horizon_component, vp_horizon_steps, vp_horizon_signal, vp_horizon_source = _vp_horizon_soft_components(
                        reward_shaping=dict(reward_shaping or {}),
                        objective_had_opportunity=int(objective_baseline_before >= 0.0),
                        baseline_horizon_steps=float(objective_baseline_before) if float(objective_baseline_before) >= 0.0 else None,
                        vp_progress_delta=float(vp_delta),
                    )
                    row["vp_horizon_steps"] = float(vp_horizon_steps)
                    row["vp_horizon_signal"] = float(vp_horizon_signal)
                    row["vp_horizon_component"] = float(vp_horizon_component)
                    row["vp_horizon_source"] = str(vp_horizon_source)
                else:
                    row["vp_horizon_steps"] = None
                    row["vp_horizon_signal"] = None
                    row["vp_horizon_component"] = None
                    row["vp_horizon_source"] = "missing_vp_progress"
                unit_for_row = str(_parse_action_id(str(aid))[1] or "")
                unit_best_vp_progress_by_unit[unit_for_row] = max(
                    float(unit_best_vp_progress_by_unit.get(unit_for_row, 0.0)),
                    float(row.get("vp_progress_delta", 0.0) or 0.0),
                )
                candidate_actions.append(row)
                if str(aid) == str(mcts_chosen):
                    step_enemy_can_capture_vp_next = int(row["enemy_can_capture_vp_next"])
                    step_enemy_min_steps_to_vp = float(row["enemy_min_steps_to_vp"])
                if vp_best_progress is None or float(vp_delta) > float(vp_best_progress):
                    vp_best_progress = float(vp_delta)
                    vp_best_action_id = str(aid)
            for row in candidate_actions:
                action_id = str(row.get("action_id", "") or "")
                row_unit_id = str(_parse_action_id(action_id)[1] or "")
                mobility_component, mobility_signal, mobility_source = _mobility_opportunity_cost_component(
                    reward_shaping=dict(reward_shaping or {}),
                    action_vp_progress=float(row.get("vp_progress_delta", 0.0) or 0.0),
                    best_unit_vp_progress=float(unit_best_vp_progress_by_unit.get(row_unit_id, 0.0) or 0.0),
                )
                if str(mobility_source) == "disabled":
                    mobility_component = float(mobility_opportunity_cost_component_default)
                row["mobility_opportunity_cost_component"] = float(mobility_component)
                row["mobility_opportunity_cost_signal"] = float(mobility_signal)
                row["mobility_opportunity_cost_source"] = str(mobility_source)
                synergy_component, synergy_signal, synergy_source = _cross_unit_synergy_component(
                    reward_shaping=dict(reward_shaping or {}),
                    action_id=action_id,
                    actor_unit_id=str(row_unit_id),
                    actor_side=str(side),
                    units=list(getattr(obs, "units", []) or []),
                    reachable_hex_mask_by_unit=dict(obs_reachable_hex_mask_by_unit),
                    attackable_hex_mask_by_unit=dict(obs_attackable_hex_mask_by_unit),
                )
                if str(synergy_source) == "disabled":
                    synergy_component = float(cross_unit_synergy_component_default)
                row["cross_unit_synergy_component"] = float(synergy_component)
                row["cross_unit_synergy_signal"] = float(synergy_signal)
                row["cross_unit_synergy_source"] = str(synergy_source)
                row["final_score"] = (
                    float(row.get("final_score", 0.0) or 0.0)
                    + float(row.get("vp_horizon_component", 0.0) or 0.0)
                    + float(row.get("enemy_threat_component", 0.0) or 0.0)
                    + float(mobility_component)
                    + float(synergy_component)
                )
            chosen, tiebreak_path, tiebreak_meta = _choose_candidate_action(
                candidate_actions=candidate_actions,
                score_epsilon=float(mcts_vp_tiebreak_epsilon),
                q_root_score_spread=float(getattr(mcts, "q_root_score_spread", 0.0) or 0.0),
                q_flat_spread_epsilon=float(mcts_q_flat_spread_epsilon),
                flat_q_score_epsilon=float(mcts_vp_flat_q_score_epsilon),
                flat_q_vp_min_progress=float(mcts_vp_flat_q_min_progress),
            )
            step_policy = str(
                episode_policy_by_side.get(str(getattr(obs, "to_play", "") or ""), "mcts")
                or "mcts"
            ).strip().lower()
            if step_policy == "random" and legal:
                chosen = str(random.choice(list(legal)))
                tiebreak_path = "random_policy"
                tiebreak_meta = dict(tiebreak_meta or {})
                tiebreak_meta["policy_override"] = "random"
            candidate_actions = _decision_ranked_candidates(
                candidate_actions=candidate_actions,
                tiebreak_path=str(tiebreak_path),
                tiebreak_meta=dict(tiebreak_meta or {}),
                score_epsilon=float(mcts_vp_tiebreak_epsilon),
                flat_q_score_epsilon=float(mcts_vp_flat_q_score_epsilon),
            )
            if not chosen:
                chosen = str(mcts_chosen)
            for row in candidate_actions:
                action_id = str(row.get("action_id", ""))
                row["selected_action"] = bool(action_id == str(chosen))
                if str(tiebreak_path) == "none":
                    row["selected_by"] = "probability"
                elif str(tiebreak_path) == "vp_progress_tiebreak":
                    row["selected_by"] = "direct_score_tiebreak_vp_progress"
                elif str(tiebreak_path) == "vp_progress_flat_q_override":
                    row["selected_by"] = "direct_score_flat_q_vp_override"
                else:
                    row["selected_by"] = str(tiebreak_path or "unknown")
            chosen_prob = next(
                (
                    float(c.get("final_score", 0.0) or 0.0)
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                ),
                0.0,
            )
            chosen_expected_damage_proxy = next(
                (
                    float(c.get("expected_damage_proxy", 0.0) or 0.0)
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                ),
                0.0,
            )
            transition = adapter.apply(chosen)
            post_obs = adapter.observation()
            action_kind, unit_id = _parse_action_id(chosen)
            if _action_consumes_unit_activation(str(chosen)):
                chosen_unit_id = str(unit_id or "").strip()
                side_key = _normalize_side(str(side or getattr(obs, "to_play", "") or ""))
                if chosen_unit_id and side_key:
                    activated_units_by_side_turn.setdefault((str(side_key), int(turn_now)), set()).add(chosen_unit_id)
            info = dict(getattr(transition, "info", {}) or {})
            attack_dice_rolls, defense_dice_rolls, attack_components, defense_components, runtime_events = _extract_actor_combat_dice_signals(
                info=info,
                acting_unit_id=str(unit_id),
            )
            after_vp = dict(getattr(post_obs, "vp_owner_by_hex", {}) or {})
            vp_captures = sum(1 for k, v in after_vp.items() if before_vp.get(k) != v and str(v) == str(side))
            objective = objective_step_signal(
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                legal_actions=legal,
                before_units=list(getattr(obs, "units", []) or []),
                before_vp_owner_by_hex=before_vp,
                after_units=list(getattr(post_obs, "units", []) or []),
                after_vp_owner_by_hex=after_vp,
                legal_capture_options=int(legal_capture_options),
                capture_taken=("CAPTURE" in str(action_kind).upper()),
                vp_captures=int(vp_captures),
                vp_gain_for_side=int(vp_captures),
                opportunity_near_vp_max_dist=float(objective_opportunity_near_vp_max_dist),
            )
            objective_progress_delta = float(objective.objective_progress_delta)
            selected_vp_q, selected_vp_r = _best_enemy_vp_qr_for_side(
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=before_vp,
                best_vp_id=str(objective.objective_best_vp_id or ""),
            )
            selected_before = _min_distance_to_vp_for_side(
                units=list(getattr(obs, "units", []) or []),
                side=str(side),
                vp_q=selected_vp_q,
                vp_r=selected_vp_r,
            )
            selected_after = _min_distance_to_vp_for_side(
                units=list(getattr(post_obs, "units", []) or []),
                side=str(side),
                vp_q=selected_vp_q,
                vp_r=selected_vp_r,
            )
            if isinstance(selected_before, float) and isinstance(selected_after, float):
                objective_progress_delta = float(selected_before - selected_after)
            # Keep progress diagnostics focused on actionable objective windows.
            if (
                objective_progress_delta > 0.0
                and float(objective.objective_min_dist_before) > float(objective_opportunity_near_vp_max_dist)
                and int(legal_capture_options) <= 0
                and not bool("CAPTURE" in str(action_kind).upper())
                and int(vp_captures) <= 0
            ):
                objective_progress_delta = 0.0
            owned_before = _min_owned_vp_distance(
                units=list(getattr(obs, "units", []) or []),
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=before_vp,
            )
            owned_after = _min_owned_vp_distance(
                units=list(getattr(post_obs, "units", []) or []),
                side=str(side),
                vp_hexes=list(getattr(post_obs, "vp_hexes", []) or []),
                vp_owner_by_hex=after_vp,
            )
            if (
                objective_progress_delta > 0.0
                and isinstance(owned_before, float)
                and isinstance(owned_after, float)
                and float(owned_after) < float(owned_before)
                and int(legal_capture_options) <= 0
                and not bool("CAPTURE" in str(action_kind).upper())
            ):
                objective_progress_delta = 0.0
            for row in candidate_actions:
                if str(row.get("action_id", "")) == str(chosen) and str(row.get("vp_progress_source", "")) == "state_fallback":
                    row["vp_progress_delta"] = float(objective_progress_delta)
                    if not str(row.get("vp_target_id", "") or "").strip():
                        row["vp_target_id"] = str(getattr(objective, "objective_best_vp_id", "") or "")
                        if str(row.get("vp_target_id", "") or "").strip():
                            row["vp_target_source"] = "post_transition_objective"
                    if (
                        row.get("vp_distance_after", None) is None
                        and isinstance(selected_after, float)
                    ):
                        row["vp_distance_after"] = float(selected_after)
                        row["vp_distance_source"] = "post_transition_objective"
            damage_dealt, kills_dealt = _resolve_actor_damage_kills(
                info=info,
                before_units=list(getattr(obs, "units", []) or []),
                after_units=list(getattr(post_obs, "units", []) or []),
                actor_side=side,
            )
            done = bool(getattr(transition, "done", False))
            terminal_reason = str(getattr(getattr(transition, "state", None), "end_reason", "") or "")
            cfg_shaping = dict(reward_shaping or {})
            terminal_scale = float(cfg_shaping.get("terminal_scale", 1.0) or 1.0)
            terminal_win_bonus = float(cfg_shaping.get("terminal_win_bonus", 0.0) or 0.0)
            terminal_loss_penalty = float(cfg_shaping.get("terminal_loss_penalty", 0.0) or 0.0)
            terminal_draw_bonus = float(cfg_shaping.get("terminal_draw_bonus", 0.0) or 0.0)

            if not done:
                reward = 0.0
            else:
                winner = getattr(getattr(transition, "state", None), "winner", None)
                to_play = getattr(obs, "to_play", None)
                if winner is not None and str(winner) == str(to_play):
                    reward = terminal_scale * (1.0 + terminal_win_bonus)
                elif winner is not None and str(winner) != str(to_play):
                    reward = terminal_scale * (-1.0 - terminal_loss_penalty)
                else:
                    reward = terminal_scale * terminal_draw_bonus
            reaction_fire_soft_component, reaction_fire_success_proxy, reaction_fire_proxy_source = _reaction_fire_soft_signal(
                action_kind=str(action_kind),
                attack_dice_rolls=list(attack_dice_rolls),
                defense_dice_rolls=list(defense_dice_rolls),
                expected_damage_proxy=float(chosen_expected_damage_proxy),
                reward_shaping=dict(reward_shaping or {}),
            )
            reaction_exposure_component, reaction_exposure_source = _reaction_exposure_component(
                action_kind=str(action_kind),
                obs_enemy_reaction_fire_risk=float(obs_enemy_reaction_fire_risk),
                reward_shaping=dict(reward_shaping or {}),
            )
            side_norm = _normalize_side(side)
            before_friendly_vp, before_enemy_vp = _vp_control_counts(before_vp, side_norm)
            after_friendly_vp, after_enemy_vp = _vp_control_counts(after_vp, side_norm)
            vp_advantage = int(after_friendly_vp - after_enemy_vp)
            prev_sustain = int(sustained_advantage_turns_by_side.get(side_norm, 0))
            if side_norm and vp_advantage > 0:
                sustained_turns = prev_sustain + 1
            else:
                sustained_turns = 0
            if side_norm:
                sustained_advantage_turns_by_side[side_norm] = int(sustained_turns)
            previous_setup_strength = float(pending_setup_strength_by_side.get(side_norm, 0.0))
            global_strategy_soft_component, global_strategy_meta = _global_strategy_soft_signal(
                side=str(side_norm),
                action_kind=str(action_kind),
                before_units=list(getattr(obs, "units", []) or []),
                after_units=list(getattr(post_obs, "units", []) or []),
                before_vp_owner_by_hex=before_vp,
                after_vp_owner_by_hex=after_vp,
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                reward_shaping=dict(reward_shaping or {}),
                sustained_advantage_turns=int(sustained_turns),
                previous_setup_strength=float(previous_setup_strength),
                vp_captures=int(vp_captures),
            )
            if side_norm:
                pending_setup_strength_by_side[side_norm] = float(global_strategy_meta.get("next_setup_strength", 0.0) or 0.0)
            team_progress_before = _enemy_vp_team_min_distance_sum(
                units=list(getattr(obs, "units", []) or []),
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                vp_owner_by_hex=before_vp,
            )
            team_progress_after = _enemy_vp_team_min_distance_sum(
                units=list(getattr(post_obs, "units", []) or []),
                side=str(side),
                vp_hexes=list(getattr(post_obs, "vp_hexes", []) or []),
                vp_owner_by_hex=before_vp,
            )
            team_progress_delta = 0.0
            if isinstance(team_progress_before, float) and isinstance(team_progress_after, float):
                team_progress_delta = float(team_progress_before - team_progress_after)
            objective_soft_component, objective_soft_meta = _objective_progress_soft_signal(
                reward_shaping=dict(reward_shaping or {}),
                objective_had_opportunity=int(objective.objective_had_opportunity),
                objective_converted=int(objective.objective_converted),
                objective_progress_delta=float(objective_progress_delta),
                team_progress_delta=float(team_progress_delta),
                legal_capture_options=int(legal_capture_options),
                action_kind=str(action_kind),
            )
            chosen_vp_horizon_component = next(
                (
                    float(c.get("vp_horizon_component"))
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                    and c.get("vp_horizon_component", None) is not None
                ),
                None,
            )
            chosen_vp_horizon_steps = next(
                (
                    float(c.get("vp_horizon_steps"))
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                    and c.get("vp_horizon_steps", None) is not None
                ),
                None,
            )
            chosen_vp_horizon_signal = next(
                (
                    float(c.get("vp_horizon_signal"))
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                    and c.get("vp_horizon_signal", None) is not None
                ),
                None,
            )
            chosen_vp_horizon_source = next(
                (
                    str(c.get("vp_horizon_source", "unknown") or "unknown")
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                ),
                "unknown",
            )
            chosen_enemy_threat_component = next(
                (
                    float(c.get("enemy_threat_component", 0.0) or 0.0)
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                ),
                0.0,
            )
            chosen_mobility_opportunity_cost_component = next(
                (
                    float(c.get("mobility_opportunity_cost_component", 0.0) or 0.0)
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                ),
                float(mobility_opportunity_cost_component_default),
            )
            chosen_cross_unit_synergy_component = next(
                (
                    float(c.get("cross_unit_synergy_component", 0.0) or 0.0)
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(chosen)
                ),
                float(cross_unit_synergy_component_default),
            )
            damage_weight = float(cfg_shaping.get("damage_weight", 0.0) or 0.0)
            kill_weight = float(cfg_shaping.get("kill_weight", 0.0) or 0.0)
            capture_bonus = float(cfg_shaping.get("capture_bonus", 0.0) or 0.0)
            vp_capture_bonus_per_hex = float(cfg_shaping.get("vp_capture_bonus_per_hex", 0.0) or 0.0)
            idle_penalty = float(cfg_shaping.get("idle_penalty", 0.0) or 0.0)

            combat_reward = (float(damage_dealt) * damage_weight) + (float(kills_dealt) * kill_weight)
            capture_reward = (
                float(vp_captures) * (capture_bonus + vp_capture_bonus_per_hex)
                if int(vp_captures) > 0
                else 0.0
            )

            is_wait_or_pass = "WAIT" in str(action_kind).upper() or "PASS" in str(action_kind).upper()
            idle_component = idle_penalty if (is_wait_or_pass and not done and idle_penalty != 0.0) else 0.0

            reward = (
                float(reward)
                + float(combat_reward)
                + float(capture_reward)
                + float(idle_component)
                + float(reaction_fire_soft_component)
                + float(reaction_exposure_component)
                + float(global_strategy_soft_component)
                + float(objective_soft_component)
            )
            chosen_score = next(
                (float(c.get("final_score", 0.0)) for c in candidate_actions if str(c.get("action_id", "")) == chosen),
                0.0,
            )
            chosen_visit_count = next(
                (int(c.get("visit_count", 0)) for c in candidate_actions if str(c.get("action_id", "")) == chosen),
                0,
            )
            best_visit_count = max([int(c.get("visit_count", 0) or 0) for c in candidate_actions], default=0)
            vp_best_score = next(
                (
                    float(c.get("final_score", 0.0))
                    for c in candidate_actions
                    if str(c.get("action_id", "")) == str(vp_best_action_id)
                ),
                0.0,
            )
            why_text = (
                "selected action is also best toward VP"
                if str(vp_best_action_id) == chosen
                else "selected action trades off VP progress against policy prior"
            )
            if str(tiebreak_path) == "vp_progress_tiebreak":
                why_text = "selected action used VP progress tie-break"
            elif str(tiebreak_path) == "vp_progress_flat_q_override":
                why_text = "selected action used VP progress flat-Q safeguard"
            if str(tiebreak_path) == "none":
                if int(chosen_visit_count) >= int(best_visit_count) and int(best_visit_count) > 0:
                    decision_win_basis = "visits_and_probability"
                else:
                    decision_win_basis = "probability"
            else:
                decision_win_basis = "direct_score_criterion"
            samples.append(
                build_sample(
                    observation=obs_encoded,
                    action_index=_action_id_to_index(chosen, int(action_dim)),
                    action_dim=int(action_dim),
                    reward=float(reward),
                    done=done,
                    info={
                        "step": int(step_idx),
                        "action_id": chosen,
                        "action_kind": str(action_kind),
                        "unit_id": str(unit_id),
                        "unit_side": str(side),
                        "macro_posture": str(macro_plan.posture),
                        "macro_target_vp_id": str(macro_plan.target_vp_id),
                        "unit_macro_role": str(macro_plan.get_role(unit_id)),
                        "game_turn": int(getattr(obs, "turn", 0) or 0),
                        "to_play": str(getattr(obs, "to_play", "") or ""),
                        "damage_dealt": float(damage_dealt),
                        "kills_dealt": int(kills_dealt),
                        "combat_reward": float(combat_reward),
                        "capture_reward": float(capture_reward),
                        "idle_component": float(idle_component),
                        "expected_damage_proxy_selected": float(chosen_expected_damage_proxy),
                        "reaction_fire_success_proxy": float(reaction_fire_success_proxy),
                        "reaction_fire_proxy_source": str(reaction_fire_proxy_source),
                        "reaction_fire_soft_reward_component": float(reaction_fire_soft_component),
                        "reaction_exposure_component": float(reaction_exposure_component),
                        "reaction_exposure_source": str(reaction_exposure_source),
                        "global_strategy_soft_reward_component": float(global_strategy_soft_component),
                        "objective_soft_reward_component": float(objective_soft_component),
                        "vp_horizon_steps": (
                            float(chosen_vp_horizon_steps)
                            if chosen_vp_horizon_steps is not None
                            else None
                        ),
                        "vp_horizon_signal": (
                            float(chosen_vp_horizon_signal)
                            if chosen_vp_horizon_signal is not None
                            else None
                        ),
                        "vp_horizon_decision_component": (
                            float(chosen_vp_horizon_component)
                            if chosen_vp_horizon_component is not None
                            else None
                        ),
                        "vp_horizon_source": str(chosen_vp_horizon_source),
                        "enemy_can_capture_vp_next": step_enemy_can_capture_vp_next,
                        "enemy_min_steps_to_vp": (
                            float(step_enemy_min_steps_to_vp)
                            if isinstance(step_enemy_min_steps_to_vp, (int, float))
                            else None
                        ),
                        "enemy_threat_component": float(chosen_enemy_threat_component),
                        "mobility_opportunity_cost_component": float(chosen_mobility_opportunity_cost_component),
                        "cross_unit_synergy_component": float(chosen_cross_unit_synergy_component),
                        "obs_enemy_vp_threat_map": dict(obs_enemy_vp_threat_map),
                        "obs_reachable_hex_mask_by_unit": dict(obs_reachable_hex_mask_by_unit),
                        "obs_attackable_hex_mask_by_unit": dict(obs_attackable_hex_mask_by_unit),
                        "obs_enemy_reaction_fire_risk": float(obs_enemy_reaction_fire_risk),
                        "obs_vp_ownership_ttl": dict(obs_vp_ownership_ttl),
                        "objective_team_progress_delta": float(team_progress_delta),
                        "objective_soft_no_progress_triggered": bool(
                            objective_soft_meta.get("objective_soft_no_progress_triggered", False)
                        ),
                        "objective_soft_progress_delta_capped": float(
                            objective_soft_meta.get("objective_soft_progress_delta_capped", 0.0) or 0.0
                        ),
                        "objective_soft_team_progress_delta_capped": float(
                            objective_soft_meta.get("objective_soft_team_progress_delta_capped", 0.0) or 0.0
                        ),
                        "objective_soft_progress_bonus_per_hex": float(
                            objective_soft_meta.get("objective_soft_progress_bonus_per_hex", 0.0) or 0.0
                        ),
                        "objective_soft_team_progress_bonus_per_hex": float(
                            objective_soft_meta.get("objective_soft_team_progress_bonus_per_hex", 0.0) or 0.0
                        ),
                        "objective_soft_no_progress_penalty": float(
                            objective_soft_meta.get("objective_soft_no_progress_penalty", 0.0) or 0.0
                        ),
                        "vp_control_net_gain_signal": float(global_strategy_meta.get("vp_control_net_gain_signal", 0.0) or 0.0),
                        "units_in_vp_ring_signal": float(global_strategy_meta.get("units_in_vp_ring_signal", 0.0) or 0.0),
                        "enemy_vp_threat_reduced_signal": float(global_strategy_meta.get("enemy_vp_threat_reduced_signal", 0.0) or 0.0),
                        "sustained_vp_advantage_turns": int(global_strategy_meta.get("sustained_vp_advantage_turns", 0) or 0),
                        "sustained_vp_advantage_bonus_signal": float(global_strategy_meta.get("sustained_vp_advantage_bonus_signal", 0.0) or 0.0),
                        "soft_role_kind": str(global_strategy_meta.get("soft_role_kind", "default") or "default"),
                        "soft_role_consistency_signal": float(global_strategy_meta.get("soft_role_consistency_signal", 0.0) or 0.0),
                        "setup_convert_signal": float(global_strategy_meta.get("setup_convert_signal", 0.0) or 0.0),
                        "global_strategy_soft_enabled": bool(int(global_strategy_meta.get("enabled", 0) or 0) == 1),
                        "legal_action_count": int(len(global_legal)),
                        "legal_reaction_options": int(legal_reaction_options),
                        "legal_capture_options": int(legal_capture_options),
                        "unit_prefilter_enabled": bool(unit_prefilter_requested),
                        "unit_prefilter_selected_unit_id": str(unit_prefilter_selected_unit_id),
                        "unit_prefilter_constrained_count": int(len(legal)),
                        "unit_prefilter_global_count": int(unit_prefilter_global_candidate_count),
                        "unit_prefilter_mode_active": bool(unit_prefilter_active),
                        "unit_prefilter_candidate_ranking": list(unit_prefilter_candidate_ranking),
                        "unit_prefilter_global_candidate_count": int(unit_prefilter_global_candidate_count),
                        "unit_prefilter_constrained_candidate_count": int(len(legal)),
                        "vp_captures": int(vp_captures),
                        "objective_had_opportunity": int(objective.objective_had_opportunity),
                        "objective_progress_delta": float(objective_progress_delta),
                        "objective_converted": int(objective.objective_converted),
                        "objective_best_vp_id": str(objective.objective_best_vp_id),
                        "vp_distance_vector": dict(objective.vp_distance_vector),
                        "vp_distance_vector_size": int(len(objective.vp_distance_vector)),
                        "objective_min_dist_before": float(objective.objective_min_dist_before),
                        "objective_min_dist_after": float(objective.objective_min_dist_after),
                        "objective_outcome_bucket_actor": "unknown",
                        "chosen_action_prob": float(chosen_prob),
                        "real_decision_score": float(chosen_score),
                        "decision_win_basis": str(decision_win_basis),
                        "mcts_margin": float(mcts_margin),
                        "mcts_q_guardrail_clipped_count": int(
                            getattr(mcts, "q_guardrail_clipped_count", 0)
                        ),
                        "mcts_q_guardrail_clip_limit": (
                            float(getattr(mcts, "q_guardrail_clip_limit", 0.0))
                            if getattr(mcts, "q_guardrail_clip_limit", None) is not None
                            else None
                        ),
                        "mcts_q_root_score_spread": float(
                            getattr(mcts, "q_root_score_spread", 0.0)
                        ),
                        "mcts_q_root_normalization_applied": bool(
                            getattr(mcts, "q_root_normalization_applied", False)
                        ),
                        "mcts_q_root_normalization_mode": str(mcts_q_root_normalization_mode),
                        "mcts_q_root_normalization_strength": float(
                            mcts_q_root_normalization_strength
                        ),
                        "mcts_chance_mode": str(mcts_chance_mode),
                        "mcts_chance_samples_per_expansion": int(
                            getattr(mcts, "chance_samples_per_expansion", 1)
                        ),
                        "mcts_chance_value_noise_std": float(mcts_chance_value_noise_std),
                        "mcts_success_prob_enabled": bool(mcts_success_prob_enabled),
                        "mcts_success_prob_alpha": float(mcts_success_prob_alpha),
                        "mcts_success_prob_center": float(mcts_success_prob_center),
                        "mcts_success_prob_scale": float(mcts_success_prob_scale),
                        "mcts_success_prob_centered_clip_abs": float(mcts_success_prob_centered_clip_abs),
                        "mcts_min_root_visits_per_action": int(mcts_min_root_visits_per_action),
                        "mcts_min_root_visits_top_n": int(mcts_min_root_visits_top_n),
                        "mcts_success_prob_expected_damage_scale": float(
                            mcts_success_prob_expected_damage_scale
                        ),
                        "mcts_tiebreak_path": str(tiebreak_path),
                        "mcts_tiebreak_epsilon": float(mcts_vp_tiebreak_epsilon),
                        "mcts_q_flat_spread_epsilon": float(mcts_q_flat_spread_epsilon),
                        "mcts_vp_flat_q_score_epsilon": float(mcts_vp_flat_q_score_epsilon),
                        "mcts_vp_flat_q_min_progress": float(mcts_vp_flat_q_min_progress),
                        "mcts_original_chosen_action": str(mcts_chosen),
                        "episode_matchup_mode": str(episode_matchup_mode),
                        "step_policy_mode": str(step_policy),
                        "step_policy_random": bool(step_policy == "random"),
                        "mcts_tiebreak_meta": dict(tiebreak_meta),
                        "latent_top_indices": list(xai.get("latent_top_indices", []) or []),
                        "latent_top_values": list(xai.get("latent_top_values", []) or []),
                        "predicted_value_root": float(xai.get("predicted_value_root", 0.0)),
                        "mcts_action_value_source": str(
                            xai.get("mcts_action_value_source", "unknown")
                        ),
                        "mcts_action_value_fallback_used": bool(
                            xai.get("mcts_action_value_fallback_expected", False)
                        ),
                        "mcts_action_candidates": list(candidate_actions),
                        "attack_dice_rolls": list(attack_dice_rolls),
                        "defense_dice_rolls": list(defense_dice_rolls),
                        "attack_components_by_die": dict(attack_components),
                        "defense_components_by_die": dict(defense_components),
                        "runtime_events": list(runtime_events),
                        "why_action_vs_vp": {
                            "top_k": int(len(candidate_actions)),
                            "chosen_action_id": str(chosen),
                            "vp_best_action_id": str(vp_best_action_id),
                            "delta_score": float(chosen_score - vp_best_score),
                            "score_components_priority": [
                                "policy_prior",
                                "vp_progress_delta",
                                *(["attack_die_components"] if attack_components else []),
                                *(["defense_die_components"] if defense_components else []),
                            ],
                            "tie_break_path": str(tiebreak_path),
                            "tie_break_epsilon": float(mcts_vp_tiebreak_epsilon),
                            "tie_break_meta": dict(tiebreak_meta),
                            "explanation": str(why_text),
                            "candidate_actions": list(candidate_actions),
                        },
                        "why_action_vs_vp_text": str(why_text),
                        "effective_max_steps": int(effective_max_steps),
                        "step_budget_source": str(budget_source),
                        "timeout": False,
                        "terminal_reason": str(terminal_reason),
                    },
                )
            )
            obs = post_obs
            if done:
                break

        if samples and not adapter.terminal():
            samples[-1].reward_target = float(timeout_penalty)
            samples[-1].value_target = float(timeout_penalty)
            samples[-1].info["timeout"] = True
            samples[-1].info["terminal_reason"] = "turn_unit_budget"
        return samples


_BACKEND: SelfplayBackend = _NativeEZV2SelfplayBackend()


def current_backend_name() -> str:
    return _BACKEND.__class__.__name__


def set_selfplay_backend(backend: SelfplayBackend) -> None:
    global _BACKEND
    _BACKEND = backend


def play_episode(**kwargs: Any) -> list:
    return _BACKEND.play_episode(**kwargs)


__all__ = ["play_episode", "set_selfplay_backend", "current_backend_name", "SelfplayBackend"]
