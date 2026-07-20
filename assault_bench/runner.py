from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import nullcontext
import json
import math
import random
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from assault_bench.configs.config_loader import load_benchmark_config
from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.selfplay import (
    _unit_prefilter_ranking as ezv2_unit_prefilter_ranking,
)
from agents.efficientzero_v2.core.mcts import run_mcts_puct as run_mcts_puct_ezv2
from agents.muzero.adapter_voec import MuZeroVOECAdapter
from agents.muzero.configs.config_loader import load_muzero_config
from agents.muzero.core.mcts import run_mcts_puct as run_mcts_puct_muzero
from agents.muzero.core.network import MuZeroNetwork
from agents.muzero.core.selfplay import (
    observation_to_tensor,
    observation_to_vector,
    priors_and_values_from_model,
    value_signs_from_to_play,
    xai_dynamics_signals_for_action,
    xai_root_signals_from_model,
)
from agents.muzero.objective_signals import objective_step_signal
from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator

DEFAULT_MATCHUP_PROFILES: tuple[str, ...] = (
    "muzero_selfplay",
    "muzero_vs_random_side_a",
    "muzero_vs_random_side_b",
)


def _start_mlflow_run(experiment_name: str, run_name: str):
    try:
        import mlflow  # type: ignore
    except Exception:
        return None, nullcontext()
    mlflow.set_experiment(str(experiment_name))
    ctx = mlflow.start_run(run_name=str(run_name) if str(run_name).strip() else None)
    return mlflow, ctx


def _mlflow_log_metrics(mlflow_mod, metrics: dict) -> None:
    if mlflow_mod is None:
        return
    for k, v in (metrics or {}).items():
        if isinstance(v, (int, float)):
            try:
                mlflow_mod.log_metric(str(k), float(v))
            except Exception:
                continue


def _resolve_bench_device(device_cfg: str) -> str:
    import torch

    raw = str(device_cfg or "cuda").strip().lower()
    if raw == "auto":
        raw = "cuda"
    if raw == "cuda" and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _resolve_bench_device_choice(config_device_cfg: str, cli_device: str = "") -> str:
    override = str(cli_device or "").strip().lower()
    if override in {"cpu", "cuda", "auto"}:
        return _resolve_bench_device(override)
    return _resolve_bench_device(config_device_cfg)


def _resolve_enabled_profiles(benchmark_cfg: Dict[str, object]) -> set[str]:
    configured_profiles = list(
        benchmark_cfg.get(
            "matchup_profiles",
            list(DEFAULT_MATCHUP_PROFILES),
        )
        or []
    )
    return {str(x).strip() for x in configured_profiles if str(x).strip()}


def _json_default(value):
    """Best-effort JSON fallback for bench payloads/replays."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return list(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    as_dict = getattr(value, "__dict__", None)
    if isinstance(as_dict, dict):
        return as_dict
    return str(value)


def _json_dumps(payload: object, indent: int = 2) -> str:
    return json.dumps(payload, indent=indent, default=_json_default)


def _load_state_dict(path, device: str) -> dict:
    import torch
    map_location = "cuda" if str(device).strip().lower() == "cuda" else "cpu"
    try:
        state = torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        # Backward compatibility for older torch without weights_only arg.
        state = torch.load(path, map_location=map_location)
    if not isinstance(state, dict):
        return state
    # Checkpoints saved from torch.compile-wrapped modules may prefix all keys
    # with "_orig_mod.". Normalize on load for eval/bench compatibility.
    keys = list(state.keys())
    if keys and all(str(k).startswith("_orig_mod.") for k in keys):
        return {str(k)[10:]: v for k, v in state.items()}
    return state


@dataclass
class BenchmarkResult:
    agent_name: str
    matchup_profile: str
    matchup_group: str
    measurement_goal: str
    policy_name: str
    policy_by_side: Dict[str, str]
    episodes: int
    avg_return: float
    avg_steps: float
    terminal_rate: float
    timeout_rate: float
    win_rate: float
    terminal_reasons: Dict[str, float]
    vp_initial_avg_by_side: Dict[str, float]
    vp_final_avg_by_side: Dict[str, float]
    vp_net_avg_by_side: Dict[str, float]
    vp_gained_avg_by_side: Dict[str, float]
    vp_lost_avg_by_side: Dict[str, float]
    vp_final_distribution_by_side: Dict[str, Dict[str, float]]
    winner_side_counts: Dict[str, int]
    winner_side_rates: Dict[str, float]
    tracked_side: str
    tracked_metric: str
    tracked_captured_avg: float
    tracked_captured_distribution: Dict[str, float]
    scenario_outcome_counts: Dict[str, int]
    scenario_outcome_rates: Dict[str, float]
    scenario_outcome_class_counts: Dict[str, int]
    scenario_outcome_class_rates: Dict[str, float]
    tracked_outcome_bucket_counts: Dict[str, int]
    tracked_outcome_bucket_rates: Dict[str, float]
    opponent_outcome_bucket_counts: Dict[str, int]
    opponent_outcome_bucket_rates: Dict[str, float]
    phase_2_9_eval_kpis: Dict[str, float]
    phase_2_9_eval_kpis_by_side: Dict[str, Dict[str, float]]
    eval_decision_summary: Dict[str, object]
    eval_decisions_top: List[Dict[str, object]]
    eval_decision_steps_top: List[Dict[str, object]]


def _action_kind_from_id(action_id: str) -> str:
    raw = str(action_id or "").strip()
    if not raw:
        return ""
    return raw.split(":", 1)[0].strip().upper()


def _action_unit_id_from_id(action_id: str) -> str:
    parts = str(action_id or "").split(":")
    if len(parts) < 2:
        return ""
    return str(parts[1] or "")


def _is_capture_like_action_kind(kind: str) -> bool:
    k = str(kind or "").strip().upper()
    if not k:
        return False
    return ("CAPTURE" in k) or ("SEIZE" in k) or ("OCCUPY" in k)


def _is_stationary_action_kind(kind: str) -> bool:
    k = str(kind or "").strip().upper()
    if not k:
        return False
    return k in {
        "WAIT",
        "PASS",
        "HOLD",
        "END_TURN",
        "OPPORTUNITY_SKIP",
        "OPPORTUNITY_WAIT",
        "NOOP",
    }


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


def _count_capture_like_actions(legal_actions: List[str]) -> int:
    return int(
        sum(
            1
            for a in list(legal_actions or [])
            if _is_capture_like_action_kind(_action_kind_from_id(str(a)))
        )
    )


def _parse_owner_hex_key(key: str) -> Optional[tuple[int, int]]:
    raw = str(key or "").strip()
    if not raw:
        return None
    for sep in (",", ":"):
        if sep not in raw:
            continue
        parts = raw.split(sep, 1)
        if len(parts) != 2:
            continue
        try:
            return int(parts[0]), int(parts[1])
        except Exception:
            return None
    return None


def _capturable_vp_hexes_for_side(
    *,
    side: str,
    vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
) -> set[tuple[int, int]]:
    side_norm = _normalize_side_key(side)
    vp_qr = {(int(vq), int(vr)) for vq, vr, _ in _extract_vp_hexes(vp_hexes)}
    owners_by_qr: Dict[tuple[int, int], str] = {}
    for raw_key, owner in dict(vp_owner_by_hex or {}).items():
        parsed = _parse_owner_hex_key(str(raw_key))
        if parsed is None:
            continue
        owners_by_qr[(int(parsed[0]), int(parsed[1]))] = _normalize_side_key(owner)
    return {
        (int(q), int(r))
        for q, r in vp_qr
        if _normalize_side_key(owners_by_qr.get((int(q), int(r)), "")) != side_norm
    }


def _owner_by_qr(vp_owner_by_hex: Dict[str, str]) -> Dict[tuple[int, int], str]:
    owners_by_qr: Dict[tuple[int, int], str] = {}
    for raw_key, owner in dict(vp_owner_by_hex or {}).items():
        parsed = _parse_owner_hex_key(str(raw_key))
        if parsed is None:
            continue
        owners_by_qr[(int(parsed[0]), int(parsed[1]))] = _normalize_side_key(owner)
    return owners_by_qr


def _is_move_action_kind(kind: str) -> bool:
    return str(kind or "").strip().upper() == "MOVE"


def _count_immediate_vp_capture_move_options(
    *,
    side: str,
    legal_actions: List[str],
    vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
) -> int:
    capturable_hexes = _capturable_vp_hexes_for_side(
        side=str(side),
        vp_hexes=list(vp_hexes or []),
        vp_owner_by_hex=dict(vp_owner_by_hex or {}),
    )
    if not capturable_hexes:
        return 0
    count = 0
    for action_id in list(legal_actions or []):
        kind = _action_kind_from_id(str(action_id))
        if not _is_move_action_kind(kind):
            continue
        target = _parse_action_target_hex(str(action_id))
        if target is None:
            continue
        if (int(target[0]), int(target[1])) in capturable_hexes:
            count += 1
    return int(count)


def _is_immediate_vp_capture_move_taken(
    *,
    side: str,
    chosen_action_id: str,
    vp_hexes: List[object],
    before_vp_owner_by_hex: Dict[str, str],
    after_vp_owner_by_hex: Dict[str, str],
) -> bool:
    chosen_kind = _action_kind_from_id(str(chosen_action_id))
    if not _is_move_action_kind(chosen_kind):
        return False
    chosen_target = _parse_action_target_hex(str(chosen_action_id))
    if chosen_target is None:
        return False
    capturable_hexes_before = _capturable_vp_hexes_for_side(
        side=str(side),
        vp_hexes=list(vp_hexes or []),
        vp_owner_by_hex=dict(before_vp_owner_by_hex or {}),
    )
    target_qr = (int(chosen_target[0]), int(chosen_target[1]))
    if target_qr not in capturable_hexes_before:
        return False
    side_norm = _normalize_side_key(side)
    before_owner = _normalize_side_key(_owner_by_qr(dict(before_vp_owner_by_hex or {})).get(target_qr, ""))
    after_owner = _normalize_side_key(_owner_by_qr(dict(after_vp_owner_by_hex or {})).get(target_qr, ""))
    return bool(after_owner == side_norm and before_owner != side_norm)


def _metric_from_row(row: Dict[str, object], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key not in row:
            continue
        raw = row.get(key, None)
        if raw is None:
            continue
        try:
            return float(raw)
        except Exception:
            continue
    return float(default)


def _extract_actor_combat_dice_signals(
    *,
    transition_info: Optional[object],
    acting_unit_id: str,
) -> tuple[list[dict], list[dict], dict[str, int], dict[str, int], list[dict]]:
    info = dict(transition_info or {})
    runtime_events = list(info.get("runtime_events", []) or [])
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


def _extract_actor_damage_kills_from_runtime_events(
    *,
    runtime_events: List[object],
    acting_unit_id: str,
) -> tuple[float, int]:
    damage_dealt = 0.0
    kills_dealt = 0
    actor_id = str(acting_unit_id or "").strip()
    for evt in list(runtime_events or []):
        evt_dict = dict(evt or {})
        if str(evt_dict.get("type", "")) != "ACTION_EFFECT":
            continue
        payload_evt = dict(evt_dict.get("payload", {}) or {})
        attacker_evt = str(payload_evt.get("attacker", "")).strip()
        if attacker_evt and actor_id and attacker_evt != actor_id:
            continue

        attacker_effects = dict(payload_evt.get("attacker_effects", {}) or {})
        if "damage" in attacker_effects:
            try:
                damage_dealt += max(0.0, float(attacker_effects.get("damage", 0.0) or 0.0))
            except Exception:
                pass
        if bool(payload_evt.get("defender_killed", False)):
            kills_dealt += 1

        for round_evt in list(payload_evt.get("rounds", []) or []):
            rr = dict(round_evt or {})
            rr_attacker_effects = dict(rr.get("attacker_effects", {}) or {})
            if "damage" in rr_attacker_effects:
                try:
                    damage_dealt += max(0.0, float(rr_attacker_effects.get("damage", 0.0) or 0.0))
                except Exception:
                    pass
            else:
                try:
                    hp_before = float(rr.get("defender_hp_before", 0.0) or 0.0)
                    hp_after = float(rr.get("defender_hp_after", hp_before) or hp_before)
                    damage_dealt += max(0.0, hp_before - hp_after)
                except Exception:
                    pass
            try:
                hp_before = float(rr.get("defender_hp_before", 0.0) or 0.0)
                hp_after = float(rr.get("defender_hp_after", hp_before) or hp_before)
                if hp_before > 0.0 and hp_after <= 0.0:
                    kills_dealt += 1
            except Exception:
                pass
    return float(damage_dealt), int(kills_dealt)


def _axial_distance(a_q: int, a_r: int, b_q: int, b_r: int) -> int:
    dq = int(a_q) - int(b_q)
    dr = int(a_r) - int(b_r)
    ds = (int(a_q) + int(a_r)) - (int(b_q) + int(b_r))
    return int(max(abs(dq), abs(dr), abs(ds)))


def _parse_action_target_hex(action_id: str) -> Optional[tuple[int, int]]:
    parts = str(action_id or "").split(":")
    if len(parts) < 4:
        return None
    try:
        return int(parts[-2]), int(parts[-1])
    except Exception:
        return None


def _extract_vp_hexes(vp_hexes: List[object]) -> List[tuple[int, int, str]]:
    rows: List[tuple[int, int, str]] = []
    for vp in list(vp_hexes or []):
        if isinstance(vp, dict):
            q = vp.get("q", None)
            r = vp.get("r", None)
            vp_id = str(vp.get("vp_id", vp.get("id", "")) or "")
        else:
            q = getattr(vp, "q", None)
            r = getattr(vp, "r", None)
            vp_id = str(getattr(vp, "vp_id", getattr(vp, "id", "")) or "")
        try:
            rows.append((int(q), int(r), vp_id))
        except Exception:
            continue
    return rows


def _extract_unit_position(unit: object) -> Optional[tuple[int, int]]:
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

    # 1) Direct q/r aliases
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

    # 2) Nested containers commonly used by snapshots/adapters
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


def _extract_unit_identifier(unit: object) -> str:
    def _read(obj: object, key: str, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for key in ("unit_id", "unitId", "id", "unit_key", "unitKey"):
        value = str(_read(unit, key, "") or "").strip()
        if value:
            return value
    return ""


def _lookup_actor_position_from_units(
    *,
    actor_unit_id: str,
    step_units_snapshot: Optional[List[object]],
) -> Optional[tuple[int, int]]:
    actor_key = str(actor_unit_id or "").strip()
    if not actor_key:
        return None
    for unit in list(step_units_snapshot or []):
        if _extract_unit_identifier(unit) != actor_key:
            continue
        pos = _extract_unit_position(unit)
        if pos is not None:
            return pos
    return None


def _select_vp_best_action(
    *,
    candidates: List[Dict[str, object]],
    chosen_action: str,
    objective_best_vp_id: str = "",
) -> Dict[str, object]:
    chosen_action_id = str(chosen_action or "")
    chosen = next((c for c in candidates if str(c.get("action_id", "")) == chosen_action_id), None)
    chosen_unit_id = _action_unit_id_from_id(chosen_action_id)
    chosen_kind = _action_kind_from_id(chosen_action_id)
    objective_best_vp_id = str(objective_best_vp_id or "").strip()

    # Restrict VP-best search to MOVE actions of the acting unit.
    move_candidates = [
        c
        for c in candidates
        if _action_kind_from_id(str(c.get("action_id", ""))) == "MOVE"
        and _action_unit_id_from_id(str(c.get("action_id", ""))) == chosen_unit_id
    ]
    if not move_candidates:
        if chosen is not None:
            return dict(chosen)
        return {}

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

    # If VP progress is flat/missing, prefer closest resulting VP distance.
    if objective_best_vp_id:
        target_filtered = [
            c for c in move_candidates if str(c.get("vp_target_id", "") or "") == objective_best_vp_id
        ]
        if target_filtered:
            move_candidates = target_filtered

    distance_candidates = [
        c for c in move_candidates if c.get("vp_distance_after", None) is not None
    ]
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

    # Deterministic terminal fallback when candidates cannot be evaluated.
    if chosen is not None and chosen_kind == "MOVE":
        return dict(chosen)
    return dict(primary_best)


def _build_why_action_vs_vp(
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
    top_k: Optional[int],
    objective_best_vp_id: str = "",
    q_clip_abs: Optional[float] = 10.0,
) -> Dict[str, object]:
    def _normalize_vp_candidate(candidate: Dict[str, object]) -> Dict[str, object]:
        out = dict(candidate or {})
        vp_delta = out.get("vp_progress_delta", None)
        try:
            out["vp_progress_delta"] = float(vp_delta) if vp_delta is not None else None
        except Exception:
            out["vp_progress_delta"] = None
        src = str(out.get("vp_progress_source", "") or "").strip()
        if not src:
            src = "unknown"
        out["vp_progress_source"] = src
        return out

    def _canonicalize_decision_candidates(
        candidate_rows: List[Dict[str, object]],
        chosen_action_id: str,
    ) -> List[Dict[str, object]]:
        rows = [dict(c or {}) for c in list(candidate_rows or [])]
        if not rows:
            return []
        chosen_action_id = str(chosen_action_id or "")
        for row in rows:
            action_id = str(row.get("action_id", "") or "")
            final_score = row.get("real_decision_score", row.get("final_score", 0.0))
            try:
                final_score_f = float(final_score if final_score is not None else 0.0)
            except Exception:
                final_score_f = 0.0
            visit_count = row.get("visit_count", 0)
            try:
                visit_count_i = int(visit_count if visit_count is not None else 0)
            except Exception:
                visit_count_i = 0
            q_value = row.get("mcts_q_value", 0.0)
            u_value = row.get("mcts_u_value", 0.0)
            try:
                q_value_f = float(q_value if q_value is not None else 0.0)
            except Exception:
                q_value_f = 0.0
            try:
                u_value_f = float(u_value if u_value is not None else 0.0)
            except Exception:
                u_value_f = 0.0
            selected_by = str(row.get("selected_by", "") or "").strip() or "mcts_puct"
            row["action_id"] = action_id
            row["final_score"] = float(final_score_f)
            row["real_decision_score"] = float(final_score_f)
            row["visit_count"] = int(max(0, visit_count_i))
            row["mcts_q_value"] = float(q_value_f)
            row["mcts_u_value"] = float(u_value_f)
            row["mcts_success_prob_proxy"] = float(
                row.get("mcts_success_prob_proxy", 0.5) or 0.5
            )
            row["mcts_success_component"] = float(
                row.get("mcts_success_component", 0.0) or 0.0
            )
            row["mcts_puct_score"] = float(
                row.get("mcts_puct_score", row["final_score"]) or row["final_score"]
            )
            row["policy_prior"] = float(row.get("policy_prior", 0.0) or 0.0)
            row["vp_horizon_steps"] = (
                float(row.get("vp_horizon_steps"))
                if row.get("vp_horizon_steps", None) is not None
                else None
            )
            row["vp_horizon_signal"] = (
                float(row.get("vp_horizon_signal"))
                if row.get("vp_horizon_signal", None) is not None
                else None
            )
            row["vp_horizon_component"] = (
                float(row.get("vp_horizon_component"))
                if row.get("vp_horizon_component", None) is not None
                else None
            )
            _h_dec = row.get("vp_horizon_decision_component", row.get("vp_horizon_component", None))
            row["vp_horizon_decision_component"] = float(_h_dec) if _h_dec is not None else None
            row["selected_action"] = bool(action_id == chosen_action_id)
            row["selected_by"] = selected_by
            row["decision_criterion"] = str(row.get("decision_criterion", "mcts_puct"))
            row["decision_components"] = {
                "visit_count": int(row["visit_count"]),
                "q_value": float(row["mcts_q_value"]),
                "u_value": float(row["mcts_u_value"]),
                "success_prob_proxy": float(row["mcts_success_prob_proxy"]),
                "success_component": float(row["mcts_success_component"]),
                "puct_score": float(row["mcts_puct_score"]),
                "policy_prior": float(row["policy_prior"]),
                "tie_break_term": (
                    float(row.get("vp_progress_delta"))
                    if row.get("vp_progress_delta", None) is not None
                    else None
                ),
                "tie_break_source": str(row.get("vp_progress_source", "unknown") or "unknown"),
                "vp_horizon_steps": (
                    float(row["vp_horizon_steps"])
                    if row.get("vp_horizon_steps", None) is not None
                    else None
                ),
                "vp_horizon_signal": (
                    float(row["vp_horizon_signal"])
                    if row.get("vp_horizon_signal", None) is not None
                    else None
                ),
                "vp_horizon_component": (
                    float(row["vp_horizon_component"])
                    if row.get("vp_horizon_component", None) is not None
                    else None
                ),
            }
        ranked = sorted(
            rows,
            key=lambda r: (
                -float(r.get("real_decision_score", 0.0) or 0.0),
                -int(r.get("visit_count", 0) or 0),
                str(r.get("action_id", "")),
            ),
        )
        rank_by_action = {
            str(r.get("action_id", "")): int(i + 1)
            for i, r in enumerate(ranked)
        }
        for row in rows:
            row["decision_rank"] = int(
                rank_by_action.get(str(row.get("action_id", "")), len(rows))
            )
        return rows

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
    total_visits = int(sum(int(max(0, visits_by_action.get(a, 0))) for a in legal_actions))
    root_sqrt = math.sqrt(max(1, total_visits))
    vp_cells_all = _extract_vp_hexes(vp_hexes=vp_hexes)
    side_norm = _normalize_side_key(active_side)
    owners_by_qr = _owner_by_qr(dict(vp_owner_by_hex or {}))
    # Compute VP progress against non-owned objectives only.
    vp_cells = [
        (int(vq), int(vr), str(vp_id or ""))
        for vq, vr, vp_id in vp_cells_all
        if (
            not side_norm
            or _normalize_side_key(owners_by_qr.get((int(vq), int(vr)), "")) != side_norm
        )
    ]
    base_actor_q = int(acting_unit_q) if isinstance(acting_unit_q, int) else None
    base_actor_r = int(acting_unit_r) if isinstance(acting_unit_r, int) else None
    chosen_unit_id = _action_unit_id_from_id(str(chosen_action or ""))
    candidates: List[Dict[str, object]] = []
    for action_id in legal_actions:
        action_id = str(action_id or "")
        action_kind = _action_kind_from_id(action_id)
        candidate_unit_id = _action_unit_id_from_id(action_id)
        # Use per-candidate actor position. Reuse probed actor only when the
        # candidate belongs to the same unit as chosen_action.
        if candidate_unit_id and candidate_unit_id == chosen_unit_id:
            candidate_actor_q = base_actor_q
            candidate_actor_r = base_actor_r
        else:
            candidate_actor_q = None
            candidate_actor_r = None
        if vp_cells and (candidate_actor_q is None or candidate_actor_r is None):
            candidate_actor = _lookup_actor_position_from_units(
                actor_unit_id=candidate_unit_id,
                step_units_snapshot=step_units_snapshot,
            )
            if candidate_actor is not None:
                candidate_actor_q, candidate_actor_r = candidate_actor
        vp_dist_before = None
        if candidate_actor_q is not None and candidate_actor_r is not None and vp_cells:
            vp_dist_before = min(
                _axial_distance(candidate_actor_q, candidate_actor_r, vp_q, vp_r)
                for vp_q, vp_r, _ in vp_cells
            )
        prior = None
        if isinstance(priors_by_action, dict):
            raw_prior = priors_by_action.get(action_id, None)
            if raw_prior is not None:
                try:
                    prior = float(raw_prior)
                except Exception:
                    prior = None
        if prior is None:
            prior = 0.0
        q_est = None
        if isinstance(values_by_action, dict):
            raw_q = values_by_action.get(action_id, None)
            if raw_q is not None:
                try:
                    q_est = float(raw_q)
                except Exception:
                    q_est = None
        if q_est is None:
            q_est = 0.0
        if isinstance(value_sign_by_action, dict):
            sgn = int(value_sign_by_action.get(action_id, 1))
            if sgn < 0:
                q_est *= -1.0
        q_est, _ = _clip_q_guardrail(q_est, q_clip_abs)
        visits = int(max(0, visits_by_action.get(action_id, 0)))
        u = float(c_puct) * float(prior) * (float(root_sqrt) / float(1 + visits))
        final_score = float(q_est) + float(u)
        vp_progress_delta = 0.0
        vp_progress_source = "unknown"
        vp_target_id = ""
        vp_distance_after = None
        target_hex = _parse_action_target_hex(action_id=action_id)
        if vp_dist_before is not None and target_hex is not None and vp_cells:
            t_q, t_r = target_hex
            best_after = None
            best_vp = ""
            for vp_q, vp_r, vp_id in vp_cells:
                d = _axial_distance(t_q, t_r, vp_q, vp_r)
                if best_after is None or d < best_after:
                    best_after = d
                    best_vp = str(vp_id or "")
            if best_after is not None:
                vp_progress_delta = float(vp_dist_before - best_after)
                vp_progress_source = "target_hex_parse"
                vp_target_id = best_vp
                vp_distance_after = float(best_after)
        elif (
            action_kind == "MOVE"
            and vp_dist_before is not None
            and vp_cells
            and target_hex is None
        ):
            # MOVE candidate has actor origin + VP context but undecodable target.
            # Keep deterministic zero fallback while marking provenance explicitly.
            vp_progress_delta = 0.0
            vp_progress_source = "state_fallback"
            vp_distance_after = float(vp_dist_before)
        elif vp_dist_before is not None and _is_stationary_action_kind(action_kind):
            # Stationary/no-move actions should still report a meaningful VP delta.
            vp_progress_delta = 0.0
            vp_progress_source = "state_fallback"
            vp_distance_after = float(vp_dist_before)
        elif vp_dist_before is not None:
            vp_progress_source = "unavailable_non_positional_action"
            vp_distance_after = float(vp_dist_before)
        elif not vp_cells:
            vp_progress_source = "unavailable_no_vp_context"
        else:
            vp_progress_source = "unavailable_no_actor_position"
        candidates.append(
            _normalize_vp_candidate(
                {
                "action_id": action_id,
                "policy_prior": float(prior),
                "q_estimate": float(q_est),
                "reward_estimate": (
                    float(dynamics_pred_reward)
                    if dynamics_pred_reward is not None and action_id == str(chosen_action or "")
                    else None
                ),
                "exploration_bonus_u": float(u),
                "final_score": float(final_score),
                "vp_progress_delta": vp_progress_delta,
                "vp_progress_source": str(vp_progress_source),
                "vp_target_id": str(vp_target_id),
                "vp_distance_after": vp_distance_after,
                "visit_count": int(visits),
                "real_decision_score": float(final_score),
                "mcts_q_value": float(q_est),
                "mcts_u_value": float(u),
                "mcts_success_prob_proxy": 0.5,
                "mcts_success_component": 0.0,
                "mcts_puct_score": float(final_score),
                "selected_by": "mcts_puct",
                "decision_criterion": "mcts_puct",
                "decision_components": {
                    "visit_count": int(visits),
                    "q_value": float(q_est),
                    "u_value": float(u),
                    "success_prob_proxy": 0.5,
                    "success_component": 0.0,
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
    if chosen is not None and not any(
        str(c.get("action_id", "")) == str(chosen.get("action_id", ""))
        for c in ranked_top
    ):
        # Keep diagnostics bounded to top-k while guaranteeing visibility of
        # the actually executed action for replay/debug consistency.
        if ranked_top:
            ranked_top[-1] = dict(chosen)
        else:
            ranked_top.append(dict(chosen))
    vp_best = _select_vp_best_action(
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
            (
                "vp_progress",
                abs(float(chosen.get("vp_progress_delta", 0.0) or 0.0) - float(vp_best.get("vp_progress_delta", 0.0) or 0.0)),
            ),
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
    ranked_top = _canonicalize_decision_candidates(
        ranked_top,
        chosen_action_id=str(chosen_action or ""),
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


def _backfill_why_action_vs_vp_from_observed_transition(
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
    chosen_kind = _action_kind_from_id(chosen_action)
    chosen_parts = chosen_action.split(":")
    chosen_actor_id = chosen_parts[1] if len(chosen_parts) > 1 else ""
    legal_actions = [str(a or "") for a in list(legal_actions or [])]
    legal_move_actions = [
        a
        for a in legal_actions
        if _action_kind_from_id(a) == "MOVE"
        and (a.split(":")[1] if len(a.split(":")) > 1 else "") == chosen_actor_id
    ]
    if not candidates and legal_move_actions:
        # Final deterministic fallback for legacy/missing telemetry rows:
        # ensure MOVE rows still expose comparable candidate IDs.
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
                "visit_count": 0,
                "real_decision_score": 0.0,
                "mcts_q_value": 0.0,
                "mcts_u_value": 0.0,
                "mcts_success_prob_proxy": 0.5,
                "mcts_success_component": 0.0,
                "mcts_puct_score": 0.0,
                "selected_by": "mcts_puct",
                "decision_criterion": "mcts_puct",
                "decision_components": {
                    "visit_count": 0,
                    "q_value": 0.0,
                    "u_value": 0.0,
                    "success_prob_proxy": 0.5,
                    "success_component": 0.0,
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
        kind = _action_kind_from_id(aid)
        vp_delta = c.get("vp_progress_delta", None)
        if vp_delta is None and _is_stationary_action_kind(kind):
            c["vp_progress_delta"] = 0.0
            c["vp_progress_source"] = str(c.get("vp_progress_source", "") or "state_fallback")
        src_text = str(c.get("vp_progress_source", "") or "").strip().lower()
        vp_delta_missing = c.get("vp_progress_delta", None) is None
        vp_delta_unknownish = src_text in {"", "unknown"}
        if (
            aid == chosen_action
            and observed_delta is not None
            and (vp_delta_missing or vp_delta_unknownish or src_text == "state_fallback")
        ):
            c["vp_progress_delta"] = float(observed_delta)
            c["vp_progress_source"] = str(c.get("vp_progress_source", "") or "state_fallback")
        if c.get("vp_progress_delta", None) is not None:
            try:
                c["vp_progress_delta"] = float(c.get("vp_progress_delta"))
            except Exception:
                c["vp_progress_delta"] = None
        c["vp_progress_source"] = str(c.get("vp_progress_source", "") or "unknown")
    def _canonicalize_decision_candidates(
        candidate_rows: List[Dict[str, object]],
        chosen_action_id: str,
    ) -> List[Dict[str, object]]:
        rows = [dict(c or {}) for c in list(candidate_rows or [])]
        if not rows:
            return []
        chosen_action_id = str(chosen_action_id or "")
        for row in rows:
            aid = str(row.get("action_id", "") or "")
            row["action_id"] = aid
            row["real_decision_score"] = float(row.get("real_decision_score", row.get("final_score", 0.0)) or 0.0)
            row["visit_count"] = int(row.get("visit_count", 0) or 0)
            row["mcts_q_value"] = float(row.get("mcts_q_value", 0.0) or 0.0)
            row["mcts_u_value"] = float(row.get("mcts_u_value", 0.0) or 0.0)
            row["mcts_success_prob_proxy"] = float(row.get("mcts_success_prob_proxy", 0.5) or 0.5)
            row["mcts_success_component"] = float(row.get("mcts_success_component", 0.0) or 0.0)
            row["mcts_puct_score"] = float(row.get("mcts_puct_score", row.get("final_score", 0.0)) or 0.0)
            row["vp_horizon_steps"] = (
                float(row.get("vp_horizon_steps"))
                if row.get("vp_horizon_steps", None) is not None
                else None
            )
            row["vp_horizon_signal"] = (
                float(row.get("vp_horizon_signal"))
                if row.get("vp_horizon_signal", None) is not None
                else None
            )
            row["vp_horizon_component"] = (
                float(row.get("vp_horizon_component"))
                if row.get("vp_horizon_component", None) is not None
                else None
            )
            _h_dec = row.get("vp_horizon_decision_component", row.get("vp_horizon_component", None))
            row["vp_horizon_decision_component"] = float(_h_dec) if _h_dec is not None else None
            row["selected_action"] = bool(aid == chosen_action_id)
            row["selected_by"] = str(row.get("selected_by", "") or "mcts_puct")
            row["decision_criterion"] = str(row.get("decision_criterion", "mcts_puct"))
            row["decision_components"] = {
                "visit_count": int(row["visit_count"]),
                "q_value": float(row["mcts_q_value"]),
                "u_value": float(row["mcts_u_value"]),
                "success_prob_proxy": float(row["mcts_success_prob_proxy"]),
                "success_component": float(row["mcts_success_component"]),
                "puct_score": float(row["mcts_puct_score"]),
                "policy_prior": float(row.get("policy_prior", 0.0) or 0.0),
                "tie_break_term": (
                    float(row.get("vp_progress_delta"))
                    if row.get("vp_progress_delta", None) is not None
                    else None
                ),
                "tie_break_source": str(row.get("vp_progress_source", "unknown") or "unknown"),
                "vp_horizon_steps": (
                    float(row["vp_horizon_steps"])
                    if row.get("vp_horizon_steps", None) is not None
                    else None
                ),
                "vp_horizon_signal": (
                    float(row["vp_horizon_signal"])
                    if row.get("vp_horizon_signal", None) is not None
                    else None
                ),
                "vp_horizon_component": (
                    float(row["vp_horizon_component"])
                    if row.get("vp_horizon_component", None) is not None
                    else None
                ),
            }
        ranked = sorted(
            rows,
            key=lambda r: (
                -float(r.get("real_decision_score", 0.0) or 0.0),
                -int(r.get("visit_count", 0) or 0),
                str(r.get("action_id", "")),
            ),
        )
        rank_by_action = {
            str(r.get("action_id", "")): int(i + 1)
            for i, r in enumerate(ranked)
        }
        for row in rows:
            row["decision_rank"] = int(
                rank_by_action.get(str(row.get("action_id", "")), len(rows))
            )
        return rows

    out["candidate_actions"] = _canonicalize_decision_candidates(
        candidates,
        chosen_action_id=str(chosen_action),
    )
    chosen = next((c for c in candidates if str(c.get("action_id", "")) == chosen_action), None)
    vp_best = _select_vp_best_action(
        candidates=candidates,
        chosen_action=chosen_action,
        objective_best_vp_id=str(objective_best_vp_id or ""),
    )
    if not vp_best and _action_kind_from_id(chosen_action) == "MOVE" and legal_move_actions:
        # Keep replay behavior deterministic when objective/vp telemetry is missing.
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
        chosen_id = str(chosen.get("action_id", ""))
        vp_id = str(vp_best.get("action_id", ""))
        if chosen_id == vp_id:
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


def _build_eval_decision_steps_top(
    trace_rows: List[Dict[str, object]], *, limit: int = 40
) -> List[Dict[str, object]]:
    def _num_or_none(src: Dict[str, object], key: str) -> Optional[float]:
        if key not in src:
            return None
        raw = src.get(key, None)
        if raw is None:
            return None
        try:
            val = float(raw)
        except Exception:
            return None
        return val if math.isfinite(val) else None

    def _int_or_none(src: Dict[str, object], key: str) -> Optional[int]:
        if key not in src:
            return None
        raw = src.get(key, None)
        if raw is None:
            return None
        try:
            return int(raw)
        except Exception:
            return None

    def _str_or_none(src: Dict[str, object], key: str) -> Optional[str]:
        if key not in src:
            return None
        raw = src.get(key, None)
        if raw is None:
            return None
        txt = str(raw).strip()
        return txt if txt else None

    def _normalize_candidate_strict(candidate: Dict[str, object]) -> Dict[str, object]:
        c_out = dict(candidate or {})
        c_out["action_id"] = str(c_out.get("action_id", "") or "")
        c_out["real_decision_score"] = _num_or_none(c_out, "real_decision_score")
        c_out["visit_count"] = _int_or_none(c_out, "visit_count")
        c_out["decision_rank"] = _int_or_none(c_out, "decision_rank")
        c_out["mcts_q_value"] = _num_or_none(c_out, "mcts_q_value")
        c_out["mcts_u_value"] = _num_or_none(c_out, "mcts_u_value")
        c_out["mcts_q_unclipped"] = _num_or_none(c_out, "mcts_q_unclipped")
        c_out["mcts_q_clipped"] = _num_or_none(c_out, "mcts_q_clipped")
        c_out["mcts_q_norm_applied"] = bool(c_out.get("mcts_q_norm_applied", False))
        c_out["policy_prior"] = _num_or_none(c_out, "policy_prior")
        c_out["visit_policy_prob"] = _num_or_none(c_out, "visit_policy_prob")
        c_out["policy_prior_source"] = _str_or_none(c_out, "policy_prior_source")
        c_out["policy_prior_available"] = bool(c_out.get("policy_prior_available", False))
        c_out["mcts_q_value_source"] = _str_or_none(c_out, "mcts_q_value_source")
        c_out["mcts_q_value_available"] = bool(c_out.get("mcts_q_value_available", False))
        c_out["mcts_u_value_source"] = _str_or_none(c_out, "mcts_u_value_source")
        c_out["mcts_u_value_available"] = bool(c_out.get("mcts_u_value_available", False))
        c_out["mcts_success_prob_proxy_source"] = _str_or_none(c_out, "mcts_success_prob_proxy_source")
        c_out["mcts_success_prob_proxy_available"] = bool(
            c_out.get("mcts_success_prob_proxy_available", False)
        )
        c_out["mcts_success_component_source"] = _str_or_none(c_out, "mcts_success_component_source")
        c_out["mcts_success_component_available"] = bool(
            c_out.get("mcts_success_component_available", False)
        )
        c_out["selection_source"] = _str_or_none(c_out, "selection_source")
        c_out["visit_share"] = _num_or_none(c_out, "visit_share")
        c_out["chosen_action_prob"] = _num_or_none(c_out, "chosen_action_prob")
        if not isinstance(c_out.get("decision_components", None), dict):
            c_out["decision_components"] = {}
        else:
            c_out["decision_components"] = dict(c_out.get("decision_components", {}) or {})
        return c_out

    out: List[Dict[str, object]] = []
    for row in list(trace_rows or [])[: max(1, int(limit or 40))]:
        r = dict(row or {})
        candidates = [dict(c or {}) for c in list(r.get("mcts_action_candidates", []) or [])]
        normalized_candidates: List[Dict[str, object]] = []
        for c in candidates:
            normalized_candidates.append(_normalize_candidate_strict(c))
        why = dict(r.get("why_action_vs_vp", {}) or {})
        why_candidates = [dict(c or {}) for c in list(why.get("candidate_actions", []) or [])]
        if not why_candidates and normalized_candidates:
            why_candidates = [dict(c) for c in normalized_candidates]
        why["candidate_actions"] = [_normalize_candidate_strict(c) for c in why_candidates]
        out.append(
            {
                "step": int(r.get("step", 0) or 0),
                "game_turn": int(r.get("game_turn", r.get("turn", 0)) or 0),
                "action_id": str(r.get("action_id", "") or ""),
                "action_kind": str(r.get("action_kind", "") or ""),
                "unit_side": str(r.get("unit_side", "") or ""),
                "chosen_action_prob": float(r.get("chosen_action_prob", 0.0) or 0.0),
                "real_decision_score": (
                    float(r.get("real_decision_score", 0.0))
                    if r.get("real_decision_score", None) is not None
                    else None
                ),
                # Explicit alias used by Eval Metrics table.
                "decision_score_selected": (
                    float(r.get("real_decision_score", 0.0))
                    if r.get("real_decision_score", None) is not None
                    else None
                ),
                "decision_score_selected_source": str(
                    r.get("decision_score_selected_source", "missing") or "missing"
                ),
                "decision_score_selected_available": bool(
                    r.get("decision_score_selected_available", None)
                ),
                "mcts_margin": float(r.get("mcts_margin", 0.0) or 0.0),
                "objective_progress_delta": float(r.get("objective_progress_delta", 0.0) or 0.0),
                "vp_progress": (
                    float(r.get("vp_progress", 0.0))
                    if r.get("vp_progress", None) is not None
                    else None
                ),
                "strategy_label": str(r.get("strategy_label", "") or ""),
                "unit_prefilter_enabled": (
                    bool(r.get("unit_prefilter_enabled"))
                    if r.get("unit_prefilter_enabled", None) is not None
                    else None
                ),
                "unit_prefilter_selected_unit_id": str(
                    r.get("unit_prefilter_selected_unit_id", "__none__") or "__none__"
                ),
                "unit_prefilter_constrained_count": (
                    int(r.get("unit_prefilter_constrained_count", 0) or 0)
                    if r.get("unit_prefilter_constrained_count", None) is not None
                    else None
                ),
                "unit_prefilter_global_count": (
                    int(r.get("unit_prefilter_global_count", 0) or 0)
                    if r.get("unit_prefilter_global_count", None) is not None
                    else None
                ),
                "unit_positions": list(r.get("unit_positions", []) or []),
                "unit_hp_map": dict(r.get("unit_hp_map", {}) or {}),
                "unit_alive_map": dict(r.get("unit_alive_map", {}) or {}),
                "vp_map": dict(r.get("vp_map", {}) or {}),
                "obs_enemy_vp_threat_map": dict(r.get("obs_enemy_vp_threat_map", {}) or {}),
                "obs_reachable_hex_mask_by_unit": dict(r.get("obs_reachable_hex_mask_by_unit", {}) or {}),
                "obs_attackable_hex_mask_by_unit": dict(r.get("obs_attackable_hex_mask_by_unit", {}) or {}),
                "obs_terrain_type_map": dict(r.get("obs_terrain_type_map", {}) or {}),
                "obs_terrain_cover_map": dict(r.get("obs_terrain_cover_map", {}) or {}),
                "obs_terrain_los_block_map": dict(r.get("obs_terrain_los_block_map", {}) or {}),
                "obs_terrain_move_cost_map": dict(r.get("obs_terrain_move_cost_map", {}) or {}),
                "obs_fortification_type_map": dict(r.get("obs_fortification_type_map", {}) or {}),
                "obs_fortification_edge_map": dict(r.get("obs_fortification_edge_map", {}) or {}),
                "obs_enemy_reaction_fire_risk": (
                    float(r.get("obs_enemy_reaction_fire_risk", 0.0))
                    if r.get("obs_enemy_reaction_fire_risk", None) is not None
                    else None
                ),
                "obs_vp_ownership_ttl": dict(r.get("obs_vp_ownership_ttl", {}) or {}),
                "objective_soft_reward_component": (
                    float(r.get("objective_soft_reward_component", 0.0))
                    if r.get("objective_soft_reward_component", None) is not None
                    else None
                ),
                "global_strategy_soft_reward_component": (
                    float(r.get("global_strategy_soft_reward_component", 0.0))
                    if r.get("global_strategy_soft_reward_component", None) is not None
                    else None
                ),
                "reaction_fire_soft_reward_component": (
                    float(r.get("reaction_fire_soft_reward_component", 0.0))
                    if r.get("reaction_fire_soft_reward_component", None) is not None
                    else None
                ),
                "reaction_fire_soft_reward_component_source": str(
                    r.get("reaction_fire_soft_reward_component_source", "missing") or "missing"
                ),
                "reaction_fire_soft_reward_component_available": bool(
                    r.get("reaction_fire_soft_reward_component_available", None)
                ),
                "reaction_exposure_component": (
                    float(r.get("reaction_exposure_component", 0.0))
                    if r.get("reaction_exposure_component", None) is not None
                    else None
                ),
                "reaction_exposure_component_source": str(
                    r.get("reaction_exposure_component_source", "missing") or "missing"
                ),
                "reaction_exposure_component_available": bool(
                    r.get("reaction_exposure_component_available", None)
                ),
                "mcts_prior": (
                    float(r.get("mcts_prior", 0.0))
                    if r.get("mcts_prior", None) is not None
                    else None
                ),
                "mcts_prior_source": str(r.get("mcts_prior_source", "missing") or "missing"),
                "mcts_prior_available": bool(r.get("mcts_prior_available", None)),
                "mcts_q_value": (
                    float(r.get("mcts_q_value", 0.0))
                    if r.get("mcts_q_value", None) is not None
                    else None
                ),
                "mcts_q_value_source": str(r.get("mcts_q_value_source", "missing") or "missing"),
                "mcts_q_value_available": bool(r.get("mcts_q_value_available", None)),
                "mcts_u_value": (
                    float(r.get("mcts_u_value", 0.0))
                    if r.get("mcts_u_value", None) is not None
                    else None
                ),
                "mcts_u_value_source": str(r.get("mcts_u_value_source", "missing") or "missing"),
                "mcts_u_value_available": bool(r.get("mcts_u_value_available", None)),
                "mcts_success_prob_proxy": (
                    float(r.get("mcts_success_prob_proxy", 0.0))
                    if r.get("mcts_success_prob_proxy", None) is not None
                    else None
                ),
                "mcts_success_prob_proxy_source": str(
                    r.get("mcts_success_prob_proxy_source", "missing") or "missing"
                ),
                "mcts_success_prob_proxy_available": bool(
                    r.get("mcts_success_prob_proxy_available", None)
                ),
                "mcts_success_component": (
                    float(r.get("mcts_success_component", 0.0))
                    if r.get("mcts_success_component", None) is not None
                    else None
                ),
                "mcts_success_component_source": str(
                    r.get("mcts_success_component_source", "missing") or "missing"
                ),
                "mcts_success_component_available": bool(
                    r.get("mcts_success_component_available", None)
                ),
                "vp_horizon_steps": (
                    float(r.get("vp_horizon_steps", 0.0))
                    if r.get("vp_horizon_steps", None) is not None
                    else None
                ),
                "vp_horizon_signal": (
                    float(r.get("vp_horizon_signal", 0.0))
                    if r.get("vp_horizon_signal", None) is not None
                    else None
                ),
                "vp_horizon_decision_component": (
                    float(r.get("vp_horizon_decision_component", 0.0))
                    if r.get("vp_horizon_decision_component", None) is not None
                    else None
                ),
                "vp_horizon_component": (
                    float(r.get("vp_horizon_component", 0.0))
                    if r.get("vp_horizon_component", None) is not None
                    else None
                ),
                "vp_horizon_source": str(r.get("vp_horizon_source", "missing") or "missing"),
                "vp_horizon_available": bool(r.get("vp_horizon_available", None)),
                "vp_progress_observed": (
                    float(r.get("vp_progress_observed", 0.0))
                    if r.get("vp_progress_observed", None) is not None
                    else None
                ),
                "vp_progress_estimated_selected": (
                    float(r.get("vp_progress_estimated_selected", 0.0))
                    if r.get("vp_progress_estimated_selected", None) is not None
                    else None
                ),
                "vp_progress_source": str(r.get("vp_progress_source", "missing") or "missing"),
                "vp_progress_available": bool(r.get("vp_progress_available", None)),
                "why_action_vs_vp_text": str(r.get("why_action_vs_vp_text", "") or ""),
                "mcts_action_candidates": normalized_candidates,
                "why_action_vs_vp": why,
            }
        )
    return out


def _outcome_bucket_from_class(outcome_class: str) -> str:
    cls = str(outcome_class or "").strip().lower()
    if cls in {"total_victory", "victory"}:
        return "win"
    if cls == "draw":
        return "draw"
    if cls in {"defeat", "total_defeat"}:
        return "loss"
    return "unknown"


def _build_eval_decision_summary(trace_rows: List[Dict[str, object]]) -> tuple[Dict[str, object], List[Dict[str, object]]]:
    rows = [dict(r or {}) for r in list(trace_rows or [])]
    if not rows:
        return {
            "total_decisions": 0,
            "by_action_kind": {},
            "by_action_kind_and_side": {},
        }, []
    by_kind: Dict[str, Dict[str, float]] = {}
    by_kind_side: Dict[str, Dict[str, float]] = {}
    by_action_id: Dict[str, Dict[str, float]] = {}
    ownership_by_side: Dict[str, Dict[str, float]] = {}
    mismatch_by_side: Dict[str, Dict[str, float]] = {}
    attack_effectiveness_groups: Dict[str, Dict[str, float]] = {}
    attack_effectiveness_bins: Dict[str, Dict[str, float]] = {}

    def _distance_bucket(raw: object) -> str:
        try:
            v = float(raw)
        except Exception:
            return "unknown"
        if v < 0.0:
            return "unknown"
        if v < 1.5:
            return "0-1"
        if v < 3.5:
            return "2-3"
        if v < 6.5:
            return "4-6"
        return "7+"

    def _cover_bucket(raw: object) -> str:
        try:
            v = float(raw)
        except Exception:
            return "unknown"
        if v < 0.0:
            return "unknown"
        if v < 0.25:
            return "low"
        if v < 0.60:
            return "medium"
        return "high"

    def _bucketize_prob(raw: object) -> str:
        try:
            p = float(raw)
        except Exception:
            p = 0.0
        p = min(1.0, max(0.0, p))
        lo = int(p * 5.0) / 5.0
        hi = min(1.0, lo + 0.2)
        return f"[{lo:.1f},{hi:.1f})"

    def _is_attack_like(kind: str) -> bool:
        k = str(kind or "").strip().upper()
        return k not in {"", "MOVE", "WAIT", "TIMEOUT", "OPPORTUNITY_SKIP"}

    def _acc_attack_group(group_key: str, dmg: float, kills: float, p_good: float, y_good: float) -> None:
        g = attack_effectiveness_groups.setdefault(
            str(group_key),
            {
                "count": 0.0,
                "damage_sum": 0.0,
                "damage_sq_sum": 0.0,
                "exchange_win_sum": 0.0,
                "attack_good_label_sum": 0.0,
                "attack_good_prob_sum": 0.0,
                "brier_sum": 0.0,
            },
        )
        g["count"] += 1.0
        g["damage_sum"] += float(dmg)
        g["damage_sq_sum"] += float(dmg) * float(dmg)
        g["exchange_win_sum"] += float(1.0 if (float(dmg) > 0.0 or float(kills) > 0.0) else 0.0)
        g["attack_good_label_sum"] += float(y_good)
        g["attack_good_prob_sum"] += float(p_good)
        g["brier_sum"] += float((float(p_good) - float(y_good)) ** 2)

    def _acc_attack_bin(bin_key: str, p_good: float, y_good: float) -> None:
        b = attack_effectiveness_bins.setdefault(
            str(bin_key),
            {"count": 0.0, "prob_sum": 0.0, "label_sum": 0.0, "brier_sum": 0.0},
        )
        b["count"] += 1.0
        b["prob_sum"] += float(p_good)
        b["label_sum"] += float(y_good)
        b["brier_sum"] += float((float(p_good) - float(y_good)) ** 2)

    def _to_binary_int_or_none(value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            try:
                return 1 if int(value) == 1 else 0
            except Exception:
                return None
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return 1
        if text in {"0", "false", "no", "n"}:
            return 0
        return None
    def _accumulate_dims(dst: Dict[str, float], row: Dict[str, object]) -> None:
        target_q = row.get("target_q", None)
        target_r = row.get("target_r", None)
        attack_distance = row.get("attack_distance_mean", None)
        target_cover = row.get("attack_target_cover_mean", None)
        target_los = row.get("attack_target_los_block_mean", None)
        if isinstance(target_q, (int, float)):
            dst["target_q_sum"] = float(dst.get("target_q_sum", 0.0)) + float(target_q)
            dst["target_q_n"] = float(dst.get("target_q_n", 0.0)) + 1.0
        if isinstance(target_r, (int, float)):
            dst["target_r_sum"] = float(dst.get("target_r_sum", 0.0)) + float(target_r)
            dst["target_r_n"] = float(dst.get("target_r_n", 0.0)) + 1.0
        if isinstance(attack_distance, (int, float)) and float(attack_distance) >= 0.0:
            dst["distance_sum"] = float(dst.get("distance_sum", 0.0)) + float(attack_distance)
            dst["distance_n"] = float(dst.get("distance_n", 0.0)) + 1.0
        if isinstance(target_cover, (int, float)) and float(target_cover) >= 0.0:
            dst["cover_sum"] = float(dst.get("cover_sum", 0.0)) + float(target_cover)
            dst["cover_n"] = float(dst.get("cover_n", 0.0)) + 1.0
        if isinstance(target_los, (int, float)) and float(target_los) >= 0.0:
            dst["los_sum"] = float(dst.get("los_sum", 0.0)) + float(target_los)
            dst["los_n"] = float(dst.get("los_n", 0.0)) + 1.0
        latent_dims = str(row.get("latent_top_dims", "") or "").strip()
        if latent_dims:
            votes = dst.get("_latent_dims_votes", {})
            if not isinstance(votes, dict):
                votes = {}
            votes[latent_dims] = float(votes.get(latent_dims, 0.0)) + 1.0
            dst["_latent_dims_votes"] = votes

    def _metric_from_row(
        row: Dict[str, object], *keys: str, default: float = 0.0
    ) -> float:
        for key in keys:
            if key not in row:
                continue
            raw = row.get(key, None)
            if raw is None:
                continue
            try:
                return float(raw)
            except Exception:
                continue
        return float(default)

    for r in rows:
        kind = str(r.get("action_kind", "") or "").strip().upper() or "UNKNOWN"
        side = _normalize_side_key(r.get("unit_side", "")) or "UNKNOWN"
        action_id = str(r.get("action_id", "") or "").strip() or "UNKNOWN_ACTION"
        requested_action_id = str(r.get("requested_action_id", "") or "").strip() or action_id
        action_mismatch = bool(r.get("action_mismatch", False))
        execution_mismatch = action_mismatch or (requested_action_id != action_id)
        policy_override = _to_binary_int_or_none(r.get("policy_overridden_by_mcts", None))
        has_override_signal = policy_override is not None
        kept = bool(policy_override == 0) if has_override_signal else False
        own = ownership_by_side.setdefault(
            side,
            {
                "rows": 0.0,
                "policy_kept": 0.0,
                "overwritten": 0.0,
                "override_signal_rows": 0.0,
                "unknown_override_rows": 0.0,
            },
        )
        own["rows"] += 1.0
        if not has_override_signal:
            own["unknown_override_rows"] += 1.0
        elif kept:
            own["policy_kept"] += 1.0
        else:
            own["overwritten"] += 1.0
        if has_override_signal:
            own["override_signal_rows"] += 1.0
        mm = mismatch_by_side.setdefault(side, {"rows": 0.0, "execution_mismatch": 0.0, "execution_match": 0.0})
        mm["rows"] += 1.0
        if execution_mismatch:
            mm["execution_mismatch"] += 1.0
        else:
            mm["execution_match"] += 1.0
        # Keep dashboard decision tables compatible with legacy trace schemas
        # where step outcomes were emitted as damage/kills instead of *_dealt.
        dmg = _metric_from_row(
            r,
            "damage_dealt",
            "enemy_damage",
            "damage",
            "damage_sum",
            default=0.0,
        )
        kills = _metric_from_row(
            r,
            "kills_dealt",
            "enemy_kills",
            "kills",
            "kills_sum",
            default=0.0,
        )
        k = by_kind.setdefault(kind, {"count": 0.0, "damage_sum": 0.0, "kills_sum": 0.0})
        k["count"] += 1.0
        k["damage_sum"] += dmg
        k["kills_sum"] += kills
        _accumulate_dims(k, r)
        ks_key = f"{kind}|{side}"
        ks = by_kind_side.setdefault(ks_key, {"action_kind": kind, "unit_side": side, "count": 0.0, "damage_sum": 0.0, "kills_sum": 0.0})
        ks["count"] += 1.0
        ks["damage_sum"] += dmg
        ks["kills_sum"] += kills
        _accumulate_dims(ks, r)
        aid = by_action_id.setdefault(action_id, {"action_id": action_id, "action_kind": kind, "unit_side": side, "count": 0.0, "damage_sum": 0.0, "kills_sum": 0.0})
        aid["count"] += 1.0
        aid["damage_sum"] += dmg
        aid["kills_sum"] += kills
        _accumulate_dims(aid, r)
        if _is_attack_like(kind):
            p_good = _metric_from_row(r, "chosen_action_prob", "policy_prior", default=0.0)
            p_good = min(1.0, max(0.0, float(p_good)))
            y_good = 1.0 if (float(dmg) > 0.0 or float(kills) > 0.0) else 0.0
            dist_bucket = _distance_bucket(r.get("attack_distance_mean", None))
            cover_bucket = _cover_bucket(r.get("attack_target_cover_mean", None))
            unit_key = str(r.get("unit_label", "") or r.get("unit_id", "") or "UNKNOWN")
            _acc_attack_group("global", dmg, kills, p_good, y_good)
            _acc_attack_group(f"kind::{kind}", dmg, kills, p_good, y_good)
            _acc_attack_group(f"unit::{unit_key}", dmg, kills, p_good, y_good)
            _acc_attack_group(f"distance::{dist_bucket}", dmg, kills, p_good, y_good)
            _acc_attack_group(f"cover::{cover_bucket}", dmg, kills, p_good, y_good)
            _acc_attack_bin(_bucketize_prob(p_good), p_good, y_good)

    def _enrich(v: Dict[str, float]) -> Dict[str, float]:
        c = float(v.get("count", 0.0))
        tqn = float(v.get("target_q_n", 0.0))
        trn = float(v.get("target_r_n", 0.0))
        dn = float(v.get("distance_n", 0.0))
        cn = float(v.get("cover_n", 0.0))
        ln = float(v.get("los_n", 0.0))
        latent_votes = v.get("_latent_dims_votes", {})
        if not isinstance(latent_votes, dict):
            latent_votes = {}
        latent_mode = ""
        latent_mode_count = 0.0
        if latent_votes:
            latent_mode, latent_mode_count = max(
                ((str(k), float(val)) for k, val in latent_votes.items()),
                key=lambda kv: kv[1],
            )
        base = {k: val for k, val in v.items() if not str(k).startswith("_")}
        return {
            **base,
            "damage_per_action": (float(v.get("damage_sum", 0.0)) / float(c)) if c > 0 else 0.0,
            "kills_per_action": (float(v.get("kills_sum", 0.0)) / float(c)) if c > 0 else 0.0,
            "target_q_avg": (float(v.get("target_q_sum", 0.0)) / float(tqn)) if tqn > 0 else -1.0,
            "target_r_avg": (float(v.get("target_r_sum", 0.0)) / float(trn)) if trn > 0 else -1.0,
            "attack_distance_avg": (float(v.get("distance_sum", 0.0)) / float(dn)) if dn > 0 else -1.0,
            "attack_target_cover_avg": (float(v.get("cover_sum", 0.0)) / float(cn)) if cn > 0 else -1.0,
            "attack_target_los_block_avg": (float(v.get("los_sum", 0.0)) / float(ln)) if ln > 0 else -1.0,
            "latent_top_dims": latent_mode,
            "latent_top_dims_mode_count": float(latent_mode_count),
        }

    by_kind_out = {k: _enrich(v) for k, v in sorted(by_kind.items(), key=lambda kv: (-float(kv[1].get("count", 0.0)), kv[0]))}
    by_kind_side_out = {k: _enrich(v) for k, v in sorted(by_kind_side.items(), key=lambda kv: (-float(kv[1].get("count", 0.0)), kv[0]))}
    top_actions = [_enrich(v) for _, v in sorted(by_action_id.items(), key=lambda kv: (-float(kv[1].get("count", 0.0)), kv[0]))[:40]]
    ownership_out: Dict[str, Dict[str, object]] = {}
    total_rows = 0.0
    total_kept = 0.0
    total_overwritten = 0.0
    total_override_signal_rows = 0.0
    total_unknown_override_rows = 0.0
    for side, row in sorted(ownership_by_side.items(), key=lambda kv: kv[0]):
        rows_n = float(row.get("rows", 0.0))
        kept_n = float(row.get("policy_kept", 0.0))
        over_n = float(row.get("overwritten", 0.0))
        override_signal_n = float(row.get("override_signal_rows", 0.0))
        unknown_override_n = float(row.get("unknown_override_rows", 0.0))
        total_rows += rows_n
        total_kept += kept_n
        total_overwritten += over_n
        total_override_signal_rows += override_signal_n
        total_unknown_override_rows += unknown_override_n
        ownership_out[str(side)] = {
            "side": str(side),
            "rows": int(rows_n),
            "policy_kept": int(kept_n),
            "overwritten": int(over_n),
            "override_signal_rows": int(override_signal_n),
            "unknown_override_rows": int(unknown_override_n),
            "policy_kept_rate": (kept_n / rows_n) if rows_n > 0 else 0.0,
            "overwritten_rate": (over_n / rows_n) if rows_n > 0 else 0.0,
        }
    mismatch_out: Dict[str, Dict[str, object]] = {}
    total_mismatch_rows = 0.0
    total_execution_mismatch = 0.0
    total_execution_match = 0.0
    for side, row in sorted(mismatch_by_side.items(), key=lambda kv: kv[0]):
        rows_n = float(row.get("rows", 0.0))
        mismatch_n = float(row.get("execution_mismatch", 0.0))
        match_n = float(row.get("execution_match", 0.0))
        total_mismatch_rows += rows_n
        total_execution_mismatch += mismatch_n
        total_execution_match += match_n
        mismatch_out[str(side)] = {
            "side": str(side),
            "rows": int(rows_n),
            "execution_mismatch": int(mismatch_n),
            "execution_match": int(match_n),
            "execution_mismatch_rate": (mismatch_n / rows_n) if rows_n > 0 else 0.0,
        }
    def _finalize_attack_group(src: Dict[str, float]) -> Dict[str, float]:
        n = float(src.get("count", 0.0))
        if n <= 0.0:
            return {
                "count": 0,
                "empirical_expected_damage": 0.0,
                "damage_variance": 0.0,
                "exchange_win_rate": 0.0,
                "attack_good_rate": 0.0,
                "attack_good_prob_mean": 0.0,
                "attack_good_brier": 0.0,
            }
        mean_d = float(src.get("damage_sum", 0.0)) / n
        ex2 = float(src.get("damage_sq_sum", 0.0)) / n
        var_d = max(0.0, ex2 - (mean_d * mean_d))
        return {
            "count": int(n),
            "empirical_expected_damage": float(mean_d),
            "damage_variance": float(var_d),
            "exchange_win_rate": float(src.get("exchange_win_sum", 0.0)) / n,
            "attack_good_rate": float(src.get("attack_good_label_sum", 0.0)) / n,
            "attack_good_prob_mean": float(src.get("attack_good_prob_sum", 0.0)) / n,
            "attack_good_brier": float(src.get("brier_sum", 0.0)) / n,
        }

    attack_effectiveness = {
        "global": _finalize_attack_group(attack_effectiveness_groups.get("global", {})),
        "by_action_kind": {},
        "by_unit": {},
        "by_distance_bucket": {},
        "by_cover_bucket": {},
        "calibration_bins": {},
    }
    for key, row in attack_effectiveness_groups.items():
        if str(key).startswith("kind::"):
            attack_effectiveness["by_action_kind"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
        elif str(key).startswith("unit::"):
            attack_effectiveness["by_unit"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
        elif str(key).startswith("distance::"):
            attack_effectiveness["by_distance_bucket"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
        elif str(key).startswith("cover::"):
            attack_effectiveness["by_cover_bucket"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
    for bin_key, row in sorted(attack_effectiveness_bins.items(), key=lambda kv: kv[0]):
        n = float(row.get("count", 0.0))
        attack_effectiveness["calibration_bins"][str(bin_key)] = {
            "count": int(n),
            "predicted_prob_mean": (float(row.get("prob_sum", 0.0)) / n) if n > 0.0 else 0.0,
            "empirical_attack_good_rate": (float(row.get("label_sum", 0.0)) / n) if n > 0.0 else 0.0,
            "brier": (float(row.get("brier_sum", 0.0)) / n) if n > 0.0 else 0.0,
        }

    return {
        "total_decisions": int(len(rows)),
        "decision_ownership_by_side": ownership_out,
        "decision_ownership_source": {
            "primary_signal": "policy_overridden_by_mcts",
            "override_signal_rows": int(total_override_signal_rows),
            "unknown_override_rows": int(total_unknown_override_rows),
        },
        "decision_ownership_total": {
            "rows": int(total_rows),
            "policy_kept": int(total_kept),
            "overwritten": int(total_overwritten),
            "override_signal_rows": int(total_override_signal_rows),
            "unknown_override_rows": int(total_unknown_override_rows),
            "policy_kept_rate": (total_kept / total_rows) if total_rows > 0 else 0.0,
            "overwritten_rate": (total_overwritten / total_rows) if total_rows > 0 else 0.0,
        },
        "execution_mismatch_by_side": mismatch_out,
        "execution_mismatch_total": {
            "rows": int(total_mismatch_rows),
            "execution_mismatch": int(total_execution_mismatch),
            "execution_match": int(total_execution_match),
            "execution_mismatch_rate": (
                (total_execution_mismatch / total_mismatch_rows)
                if total_mismatch_rows > 0
                else 0.0
            ),
        },
        "by_action_kind": by_kind_out,
        "by_action_kind_and_side": by_kind_side_out,
        "attack_effectiveness": attack_effectiveness,
    }, top_actions


def _safe_percentile(values: List[float], q: float) -> Optional[float]:
    vals = [float(v) for v in list(values or []) if math.isfinite(float(v))]
    if not vals:
        return None
    vals.sort()
    if len(vals) == 1:
        return float(vals[0])
    qq = min(1.0, max(0.0, float(q)))
    pos = qq * float(len(vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(vals[lo])
    w = float(pos - lo)
    return float(vals[lo] * (1.0 - w) + vals[hi] * w)


def _turn_bucket(turn: object) -> str:
    try:
        t = int(turn)
    except Exception:
        t = 0
    if t <= 3:
        return "early"
    if t <= 7:
        return "mid"
    return "late"


def _compute_decision_diagnostics_kpis(trace_rows: List[Dict[str, object]]) -> Dict[str, object]:
    rows = [dict(r or {}) for r in list(trace_rows or [])]
    eligible_steps = 0
    vp_approach_steps = 0
    regret_deltas: List[float] = []
    candidate_count = 0
    q_sat_count = 0
    step_spreads: List[float] = []
    turn_bins: Dict[str, Dict[str, int]] = {
        "early": {"opportunity_steps": 0, "converted_steps": 0},
        "mid": {"opportunity_steps": 0, "converted_steps": 0},
        "late": {"opportunity_steps": 0, "converted_steps": 0},
    }
    first_immediate_opp_step = None
    first_immediate_capture_step = None
    path_len_episode = None
    q_clip_tol = 1e-3
    for row in rows:
        candidates = [dict(c or {}) for c in list(row.get("mcts_action_candidates", []) or [])]
        chosen_action = str(row.get("action_id", "") or "")
        chosen = next((c for c in candidates if str(c.get("action_id", "")) == chosen_action), None)
        if chosen is not None:
            eligible_steps += 1
            chosen_vp_delta = float(chosen.get("vp_progress_delta", 0.0) or 0.0)
            if chosen_vp_delta > 0.0:
                vp_approach_steps += 1
            chosen_score = float(chosen.get("real_decision_score", chosen.get("final_score", 0.0)) or 0.0)
            best_score = max(
                (
                    float(c.get("real_decision_score", c.get("final_score", 0.0)) or 0.0)
                    for c in candidates
                ),
                default=chosen_score,
            )
            regret_deltas.append(float(best_score - chosen_score))
        score_values: List[float] = []
        for c in candidates:
            q_val = float(c.get("mcts_q_value", 0.0) or 0.0)
            clip_limit_raw = c.get("q_clip_limit", row.get("mcts_q_guardrail_clip_limit", None))
            clip_limit = None
            try:
                if clip_limit_raw is not None:
                    clip_limit = abs(float(clip_limit_raw))
            except Exception:
                clip_limit = None
            if clip_limit is not None and clip_limit > 0.0:
                candidate_count += 1
                if abs(abs(q_val) - clip_limit) <= q_clip_tol:
                    q_sat_count += 1
            score_values.append(float(c.get("real_decision_score", c.get("final_score", 0.0)) or 0.0))
        p95 = _safe_percentile(score_values, 0.95)
        p5 = _safe_percentile(score_values, 0.05)
        if p95 is not None and p5 is not None:
            step_spreads.append(float(p95 - p5))
        immediate_opp = int(row.get("legal_capture_options", 0) or 0) > 0
        immediate_taken = bool(row.get("capture_like_taken", False))
        if immediate_opp and first_immediate_opp_step is None:
            first_immediate_opp_step = int(row.get("step", 0) or 0)
        if (
            first_immediate_opp_step is not None
            and first_immediate_capture_step is None
            and immediate_taken
        ):
            first_immediate_capture_step = int(row.get("step", 0) or 0)
        bin_name = _turn_bucket(row.get("game_turn", row.get("turn", 0)))
        if immediate_opp:
            turn_bins[bin_name]["opportunity_steps"] += 1
            if immediate_taken:
                turn_bins[bin_name]["converted_steps"] += 1
    if first_immediate_opp_step is not None and first_immediate_capture_step is not None:
        path_len_episode = max(0, int(first_immediate_capture_step - first_immediate_opp_step))
    spread_mean = (
        float(sum(step_spreads) / float(len(step_spreads)))
        if step_spreads
        else None
    )
    return {
        "vp_approach_rate_eligible_steps": int(eligible_steps),
        "vp_approach_rate_positive_steps": int(vp_approach_steps),
        "vp_approach_rate": (
            float(vp_approach_steps) / float(eligible_steps)
            if eligible_steps > 0
            else None
        ),
        "vp_regret_delta_count": int(len(regret_deltas)),
        "vp_regret_delta_mean": (
            float(sum(regret_deltas) / float(len(regret_deltas)))
            if regret_deltas
            else None
        ),
        "vp_regret_delta_p95": _safe_percentile(regret_deltas, 0.95),
        "q_saturation_candidate_rows": int(candidate_count),
        "q_saturation_hits": int(q_sat_count),
        "q_saturation_rate": (
            float(q_sat_count) / float(candidate_count)
            if candidate_count > 0
            else None
        ),
        "decision_spread_step_count": int(len(step_spreads)),
        "decision_spread_mean": spread_mean,
        "decision_spread_p50": _safe_percentile(step_spreads, 0.50),
        "decision_spread_p95": _safe_percentile(step_spreads, 0.95),
        "path_to_capture_length_episode": (
            int(path_len_episode) if path_len_episode is not None else None
        ),
        "path_to_capture_length_count": (1 if path_len_episode is not None else 0),
        "path_to_capture_length_mean": (
            float(path_len_episode) if path_len_episode is not None else None
        ),
        "path_to_capture_length_p95": (
            float(path_len_episode) if path_len_episode is not None else None
        ),
        "opportunity_conversion_by_turn": {
            b: {
                "opportunity_steps": int(v["opportunity_steps"]),
                "converted_steps": int(v["converted_steps"]),
                "conversion_rate": (
                    float(v["converted_steps"]) / float(v["opportunity_steps"])
                    if int(v["opportunity_steps"]) > 0
                    else None
                ),
            }
            for b, v in turn_bins.items()
        },
        "opportunity_conversion_early_opportunity_steps": int(
            turn_bins["early"]["opportunity_steps"]
        ),
        "opportunity_conversion_early_converted_steps": int(
            turn_bins["early"]["converted_steps"]
        ),
        "opportunity_conversion_early_rate": (
            float(turn_bins["early"]["converted_steps"])
            / float(turn_bins["early"]["opportunity_steps"])
            if int(turn_bins["early"]["opportunity_steps"]) > 0
            else None
        ),
        "opportunity_conversion_mid_opportunity_steps": int(
            turn_bins["mid"]["opportunity_steps"]
        ),
        "opportunity_conversion_mid_converted_steps": int(
            turn_bins["mid"]["converted_steps"]
        ),
        "opportunity_conversion_mid_rate": (
            float(turn_bins["mid"]["converted_steps"])
            / float(turn_bins["mid"]["opportunity_steps"])
            if int(turn_bins["mid"]["opportunity_steps"]) > 0
            else None
        ),
        "opportunity_conversion_late_opportunity_steps": int(
            turn_bins["late"]["opportunity_steps"]
        ),
        "opportunity_conversion_late_converted_steps": int(
            turn_bins["late"]["converted_steps"]
        ),
        "opportunity_conversion_late_rate": (
            float(turn_bins["late"]["converted_steps"])
            / float(turn_bins["late"]["opportunity_steps"])
            if int(turn_bins["late"]["opportunity_steps"]) > 0
            else None
        ),
        "opportunity_conversion_turn_buckets_definition": "early: turn<=3, mid: turn 4-7, late: turn>=8",
    }


def _side_hp_snapshot(units) -> Dict[str, float]:
    hp: Dict[str, float] = {}
    for u in list(units or []):
        if isinstance(u, dict):
            side_raw = u.get("side", "")
            hp_raw = u.get("hp", 0.0)
        else:
            side_raw = getattr(u, "side", "")
            hp_raw = getattr(u, "hp", 0.0)
        side = _normalize_side_key(side_raw)
        if not side:
            continue
        hp[side] = hp.get(side, 0.0) + float(max(0.0, float(hp_raw or 0.0)))
    return hp


def _side_alive_snapshot(units) -> Dict[str, int]:
    alive: Dict[str, int] = {}
    for u in list(units or []):
        if isinstance(u, dict):
            side_raw = u.get("side", "")
            alive_raw = u.get("alive", False)
        else:
            side_raw = getattr(u, "side", "")
            alive_raw = getattr(u, "alive", False)
        side = _normalize_side_key(side_raw)
        if not side:
            continue
        if bool(alive_raw):
            alive[side] = alive.get(side, 0) + 1
    return alive


def _normalize_side_key(side: object) -> str:
    raw = getattr(side, "value", side)
    return str(raw or "").strip().upper()


def _unit_suppressed_state_from_raw(unit_obj: object) -> Optional[bool]:
    if isinstance(unit_obj, dict):
        getter = lambda key: unit_obj.get(key, None)
    else:
        getter = lambda key: getattr(unit_obj, key, None)
    for key in ("suppressed", "is_suppressed", "pinned", "is_pinned"):
        raw = getter(key)
        if raw is None:
            continue
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        txt = str(raw).strip().lower()
        if txt in {"1", "true", "yes", "y", "on"}:
            return True
        if txt in {"0", "false", "no", "n", "off"}:
            return False
    return None


def _unit_snapshot_dict(u) -> Dict[str, object]:
    if isinstance(u, dict):
        getter = lambda key, default: u.get(key, default)
    else:
        getter = lambda key, default: getattr(u, key, default)
    suppressed_state = _unit_suppressed_state_from_raw(u)
    return {
        "unit_id": str(getter("unit_id", "") or ""),
        "unit_key": str(getter("unit_key", "") or ""),
        "unit_label": str(getter("unit_label", "") or ""),
        "side": str(getter("side", "") or ""),
        "q": int(getter("q", 0) or 0),
        "r": int(getter("r", 0) or 0),
        "hp": float(getter("hp", 0.0) or 0.0),
        "alive": bool(getter("alive", False)),
        "suppressed": (
            bool(suppressed_state)
            if suppressed_state is not None
            else None
        ),
    }


def _units_snapshot(units) -> List[Dict[str, object]]:
    return [_unit_snapshot_dict(u) for u in list(units or [])]


def _assault_advantage_bucket(chosen_prob: float, margin: float, legal_count: int) -> str:
    score = 0
    if float(chosen_prob) >= 0.55:
        score += 1
    if float(margin) >= 0.20:
        score += 1
    if int(legal_count) >= 6:
        score += 1
    return "favorable" if score >= 2 else "unfavorable"


def _benchmark_seed_task(payload: dict):
    from voec_sim.assets_bridge.importers import AssetPaths

    assets = AssetPaths(
        root=Path(payload["assets"]["root"]),
        unit_catalog=Path(payload["assets"]["unit_catalog"]),
        map_piece_catalog=Path(payload["assets"]["map_piece_catalog"]),
        scenarios_dir=Path(payload["assets"]["scenarios_dir"]),
    )
    sim = VOECSimulator(assets=assets)
    adapter = MuZeroVOECAdapter(sim)
    model = None
    bench_device = str(payload.get("bench_device", "cpu")).strip().lower()
    if payload.get("checkpoint_path"):
        model_kind = str(payload.get("model_kind", "muzero")).strip().lower()
        model_cls = EfficientZeroV2Network if model_kind == "efficientzero_v2" else MuZeroNetwork
        model = model_cls(
            observation_dim=int(payload["model"]["observation_dim"]),
            hidden_dim=int(payload["model"]["hidden_dim"]),
            action_dim=int(payload["model"]["action_dim"]),
            encoder_type=str(payload["model"].get("encoder_type", "mlp")),
            observation_channels=int(payload["model"].get("observation_channels", 8)),
            observation_height=int(payload["model"].get("observation_height", 16)),
            observation_width=int(payload["model"].get("observation_width", 16)),
            dynamics_blocks=int(payload["model"].get("dynamics_blocks", 1)),
            prediction_blocks=int(payload["model"].get("prediction_blocks", 1)),
        )
        state_dict = _load_state_dict(payload["checkpoint_path"], bench_device)
        model.load_state_dict(state_dict)
        if bench_device == "cuda":
            model = model.to("cuda")
        model.eval()
    return _run_episode_with_policy(
        adapter=adapter,
        scenario_id=payload["scenario_id"],
        seed=payload["seed"],
        policy_name=payload["policy_name"],
        policy_by_side=dict(payload.get("policy_by_side", {}) or {}),
        max_steps=payload["max_steps"],
        max_steps_override=int(payload.get("max_steps_override", 0)),
        mcts_simulations=payload["mcts_simulations"],
        mcts_c_puct=payload["mcts_c_puct"],
        mcts_temperature=payload["mcts_temperature"],
        mcts_dirichlet_alpha=float(payload.get("mcts_dirichlet_alpha", 0.3)),
        mcts_dirichlet_epsilon=float(payload.get("mcts_dirichlet_epsilon", 0.0)),
        mcts_q_clip_abs=float(payload.get("mcts_q_clip_abs", 10.0)),
        mcts_min_root_visits_per_action=int(payload.get("mcts_min_root_visits_per_action", 0)),
        mcts_min_root_visits_top_n=int(payload.get("mcts_min_root_visits_top_n", 0)),
        model=model,
        action_dim=int(payload.get("action_dim", 32)),
        mcts_unroll_steps=int(payload.get("mcts_unroll_steps", 1)),
        mcts_discount=float(payload.get("mcts_discount", 0.997)),
        collect_flow_metrics=bool(payload.get("collect_flow_metrics", True)),
        decision_top_k=payload.get("decision_top_k", None),
        unit_prefilter_enabled=bool(payload.get("unit_prefilter_enabled", False)),
        unit_prefilter_replan_enabled=bool(payload.get("unit_prefilter_replan_enabled", False)),
        unit_prefilter_top_k=int(payload.get("unit_prefilter_top_k", 1)),
        unit_prefilter_vp_progress_weight=float(payload.get("unit_prefilter_vp_progress_weight", 1.0)),
        unit_prefilter_capture_opportunity_weight=float(payload.get("unit_prefilter_capture_opportunity_weight", 2.0)),
        unit_prefilter_threat_weight=float(payload.get("unit_prefilter_threat_weight", 0.25)),
    )


def _run_episode_with_policy(
    adapter: MuZeroVOECAdapter,
    scenario_id: str,
    seed: int,
    policy_name: str,
    policy_by_side: Dict[str, str],
    max_steps: int,
    max_steps_override: int,
    mcts_simulations: int,
    mcts_c_puct: float,
    mcts_temperature: float,
    mcts_dirichlet_alpha: float = 0.3,
    mcts_dirichlet_epsilon: float = 0.0,
    mcts_q_clip_abs: float = 10.0,
    mcts_min_root_visits_per_action: int = 0,
    mcts_min_root_visits_top_n: int = 0,
    model=None,
    action_dim: int = 32,
    mcts_unroll_steps: int = 1,
    mcts_discount: float = 0.997,
    collect_flow_metrics: bool = True,
    decision_top_k: Optional[int] = None,
    unit_prefilter_enabled: bool = False,
    unit_prefilter_replan_enabled: bool = False,
    unit_prefilter_top_k: int = 1,
    unit_prefilter_vp_progress_weight: float = 1.0,
    unit_prefilter_capture_opportunity_weight: float = 2.0,
    unit_prefilter_threat_weight: float = 0.25,
):
    HEAD_NAMES = ("policy", "value", "reward", "objective", "consistency", "mcts")

    def _head_state(status: str, reason: str = "") -> Dict[str, str]:
        return {"status": str(status), "reason": str(reason or "")}

    def _compute_coverage_status(heads: Dict[str, Dict[str, str]]) -> tuple[str, str]:
        statuses = [str((heads.get(h, {}) or {}).get("status", "none")) for h in HEAD_NAMES]
        if statuses and all(s == "complete" for s in statuses):
            return "complete", ""
        if statuses and all(s == "none" for s in statuses):
            return "none", "no_head_signals_available"
        return "partial", "some_heads_missing_or_not_applicable"

    def _to_int_or_none(v):
        try:
            if v is None:
                return None
            return int(v)
        except Exception:
            return None

    def _field(obj, name: str, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    model_kind_local = (
        "efficientzero_v2"
        if model is not None and str(type(model).__name__) == "EfficientZeroV2Network"
        else "muzero"
    )

    def _run_policy_mcts(**kwargs):
        if model_kind_local == "efficientzero_v2":
            return run_mcts_puct_ezv2(**kwargs)
        return run_mcts_puct_muzero(**kwargs)

    def _new_phase29_bucket() -> Dict[str, float]:
        return {
            "reaction_window_count": 0,
            "reaction_fire_count": 0,
            "reaction_fire_skipped_count": 0,
            "reaction_fire_kill_conversions": 0,
            "reaction_fire_damage_sum": 0.0,
            "melee_attempts": 0,
            "melee_success_count": 0,
            "melee_kills_sum": 0.0,
            "melee_damage_sum": 0.0,
            "assault_favorable_count": 0,
            "assault_unfavorable_count": 0,
            "converted_from_progress_rate": 0.0,
            "converted_rate_near_vp": 0.0,
            "conversion_within_2_turns_after_progress": 0.0,
            "xai_decision_steps": 0,
            "xai_policy_confidence_sum": 0.0,
            "xai_policy_margin_sum": 0.0,
            "xai_latent_signal_steps": 0,
            "xai_vp_capture_opportunity_steps": 0,
            "xai_vp_capture_taken_steps": 0,
            "xai_vp_immediate_capture_opportunity_steps": 0,
            "xai_vp_immediate_capture_taken_steps": 0,
        }

    def _finalize_phase29(bucket: Dict[str, float]) -> Dict[str, float]:
        reaction_den = max(1, int(bucket["reaction_fire_count"] + bucket["reaction_fire_skipped_count"]))
        melee_den = max(1, int(bucket["melee_attempts"]))
        xai_den = max(1, int(bucket["xai_decision_steps"]))
        xai_cap_den = max(1, int(bucket["xai_vp_capture_opportunity_steps"]))
        xai_immediate_cap_den = max(
            1, int(bucket["xai_vp_immediate_capture_opportunity_steps"])
        )
        return {
            "reaction_window_count": int(bucket["reaction_window_count"]),
            "reaction_fire_count": int(bucket["reaction_fire_count"]),
            "reaction_fire_skipped_count": int(bucket["reaction_fire_skipped_count"]),
            "reaction_fire_kill_conversions": int(bucket["reaction_fire_kill_conversions"]),
            "reaction_fire_damage_sum": float(bucket["reaction_fire_damage_sum"]),
            "reaction_fire_activation_rate": (
                float(bucket["reaction_fire_count"]) / float(reaction_den)
            ),
            "reaction_fire_kill_conversion_rate": (
                float(bucket["reaction_fire_kill_conversions"])
                / float(max(1, int(bucket["reaction_fire_count"])))
            ),
            "reaction_fire_damage_induced_proxy": (
                float(bucket["reaction_fire_damage_sum"])
                / float(max(1, int(bucket["reaction_fire_count"])))
            ),
            "reaction_fire_damage_prevented_proxy": (
                float(bucket["reaction_fire_kill_conversions"])
                / float(max(1, int(bucket["reaction_fire_count"])))
            ),
            "assault_melee_action_family_count": int(bucket["melee_attempts"]),
            "melee_attempts": int(bucket["melee_attempts"]),
            "melee_success_count": int(bucket["melee_success_count"]),
            "melee_kills_sum": float(bucket["melee_kills_sum"]),
            "melee_damage_sum": float(bucket["melee_damage_sum"]),
            "melee_success_rate": (
                float(bucket["melee_success_count"]) / float(melee_den)
            ),
            "melee_kills_per_attempt": (
                float(bucket["melee_kills_sum"]) / float(melee_den)
            ),
            "melee_damage_per_attempt": (
                float(bucket["melee_damage_sum"]) / float(melee_den)
            ),
            "assault_favorable_count": int(bucket["assault_favorable_count"]),
            "assault_unfavorable_count": int(bucket["assault_unfavorable_count"]),
            "converted_from_progress_rate": float(bucket["converted_from_progress_rate"]),
            "converted_rate_near_vp": float(bucket["converted_rate_near_vp"]),
            "conversion_within_2_turns_after_progress": float(
                bucket["conversion_within_2_turns_after_progress"]
            ),
            "xai_decision_steps": int(bucket["xai_decision_steps"]),
            "xai_policy_confidence_mean": (
                float(bucket["xai_policy_confidence_sum"]) / float(xai_den)
            ),
            "xai_policy_margin_mean": (
                float(bucket["xai_policy_margin_sum"]) / float(xai_den)
            ),
            "xai_latent_signal_coverage": (
                float(bucket["xai_latent_signal_steps"]) / float(xai_den)
            ),
            "xai_vp_capture_opportunity_steps": int(bucket["xai_vp_capture_opportunity_steps"]),
            "xai_vp_capture_taken_steps": int(bucket["xai_vp_capture_taken_steps"]),
            "xai_vp_capture_take_rate": (
                float(bucket["xai_vp_capture_taken_steps"]) / float(xai_cap_den)
            ),
            "xai_vp_immediate_capture_opportunity_steps": int(
                bucket["xai_vp_immediate_capture_opportunity_steps"]
            ),
            "xai_vp_immediate_capture_taken_steps": int(
                bucket["xai_vp_immediate_capture_taken_steps"]
            ),
            "xai_vp_immediate_capture_take_rate": (
                float(bucket["xai_vp_immediate_capture_taken_steps"])
                / float(xai_immediate_cap_den)
            ),
        }

    def _scenario_outcome_from_final_vp(final_vp_by_side: Dict[str, int]) -> Dict[str, object]:
        runtime = getattr(adapter.sim, "_runtime", None)
        scenario = getattr(runtime, "scenario", None) if runtime is not None else None
        vo = dict(getattr(scenario, "victory_outcomes", {}) or {})
        tracked_side = str(vo.get("tracked_side", "")).strip()
        metric = str(vo.get("metric", "")).strip()
        table = list(vo.get("table", []) or [])
        captured = int(final_vp_by_side.get(tracked_side, 0)) if tracked_side else 0
        matched = None
        for row in table:
            cap = dict(row.get("captured", {}) or {})
            lo = int(cap.get("min", -10**9))
            hi = int(cap.get("max", 10**9))
            if lo <= captured <= hi:
                matched = row
                break
        if matched is None and table:
            matched = dict(table[-1])
        return {
            "tracked_side": tracked_side,
            "metric": metric,
            "captured": int(captured),
            "result": str((matched or {}).get("result", "")).strip(),
            "outcome_class": str((matched or {}).get("outcome_class", "")).strip(),
            "next_scenario": str((matched or {}).get("next_scenario", "")).strip(),
            "next_page": int((matched or {}).get("next_page", 0) or 0),
        }

    def _vp_control_counts() -> Dict[str, int]:
        state = getattr(adapter.sim, "_state", None)
        if state is None:
            return {}
        counts: Dict[str, int] = {}
        side_to_ownership = dict(getattr(state, "side_to_ownership", {}) or {})
        for side in side_to_ownership.keys():
            counts[str(side)] = 0
        victory = getattr(state, "victory", None)
        if victory is None:
            return counts
        for vp in getattr(victory, "points", []) or []:
            hs = state.hex_states.get(vp.hex_coords) if getattr(state, "hex_states", None) else None
            if hs is None:
                continue
            owner = getattr(hs, "ownership", None)
            for side, side_owner in side_to_ownership.items():
                if owner == side_owner:
                    side_s = str(side)
                    counts[side_s] = counts.get(side_s, 0) + 1
                    break
        return counts

    obs = adapter.initial_state(scenario_id=scenario_id, seed=seed)
    initial_vp_by_side = _vp_control_counts()
    eval_side = str(obs.to_play) if obs.to_play is not None else ""
    scenario_turn_limit = None
    if hasattr(adapter.sim, "scenario_max_turns"):
        try:
            scenario_turn_limit = adapter.sim.scenario_max_turns()
        except Exception:
            scenario_turn_limit = None
    effective_max_steps = int(max_steps)
    unit_count = len(getattr(obs, "units", []) or [])
    if int(max_steps_override) > 0:
        effective_max_steps = int(max_steps_override)
    elif scenario_turn_limit is not None and int(scenario_turn_limit) > 0 and unit_count > 0:
        effective_max_steps = int(scenario_turn_limit) * int(unit_count)
    total_reward = 0.0
    steps = 0
    terminal = False
    timeout = False
    win = False
    terminal_reason = ""
    winner_side = ""
    timeout_reason = "turn_unit_budget"
    phase29 = _new_phase29_bucket()
    phase29_by_side: Dict[str, Dict[str, float]] = {}
    trace_rows: List[Dict[str, object]] = []
    policy_by_side_norm = {
        _normalize_side_key(side): str(policy_name_for_side or "")
        for side, policy_name_for_side in dict(policy_by_side or {}).items()
        if _normalize_side_key(side)
    }
    for _ in range(effective_max_steps):
        if adapter.sim.reached_turn_limit() and not adapter.terminal():
            timeout_reason = "scenario_turn_limit"
            break
        legal = adapter.legal_actions()
        if not legal:
            break
        legal_for_step = list(legal or [])
        legal_actions_list = [str(a or "") for a in legal_for_step]
        obs_units = list(getattr(obs, "units", []) or [])
        obs_vp_hexes = list(getattr(obs, "vp_hexes", []) or [])
        active_side = _normalize_side_key(obs.to_play) if obs.to_play is not None else ""
        side_hp_before = _side_hp_snapshot(obs_units)
        side_alive_before = _side_alive_snapshot(obs_units)
        active_policy = str(policy_by_side_norm.get(active_side, policy_name)).strip().lower() or str(policy_name)
        collect_this_step = bool(collect_flow_metrics and active_policy != "random")
        capture_legal_count = _count_capture_like_actions(legal_for_step)
        reaction_opts = [a for a in legal_actions_list if _action_kind_from_id(a).startswith("OPPORTUNITY_")]
        if collect_this_step and reaction_opts:
            phase29["reaction_window_count"] += 1
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["reaction_window_count"] += 1
        chosen_prob = 0.0
        margin = 0.0
        latent_top_dims = ""
        mcts_entropy = 0.0
        mcts_total_visits = 0
        mcts_active_actions = 0
        mcts_out = None
        policy_top_action = ""
        policy_overridden_by_mcts = None
        predicted_value_root = None
        dynamics_pred_reward = None
        dynamics_next_latent_l2 = None
        dynamics_delta_l2 = None
        policy_top_actions: List[str] = []
        policy_top_probs: List[float] = []
        latent_top_indices: List[int] = []
        latent_top_values: List[float] = []
        latent_l2_norm = None
        decision_top_k_effective = int(decision_top_k or 0)
        if decision_top_k_effective < 0:
            decision_top_k_effective = 0
        why_action_vs_vp: Dict[str, object] = {
            "top_k": int(decision_top_k_effective),
            "chosen_action_id": "",
            "vp_best_action_id": "",
            "delta_score": None,
            "score_components_priority": [],
            "explanation": "N/A (legacy telemetry)",
            "candidate_actions": [],
        }
        mcts_action_candidates: List[Dict[str, object]] = []
        head_states = {h: _head_state("none", "missing") for h in HEAD_NAMES}
        if active_policy == "random":
            action = random.choice(legal)
            head_states = {h: _head_state("none", "random_policy_no_model") for h in HEAD_NAMES}
        else:
            priors = None
            values = None
            signs = value_signs_from_to_play(obs, legal)
            xai_root = {}
            if model is not None:
                if str(getattr(model, "encoder_type", "mlp")) == "cnn":
                    obs_vector = observation_to_tensor(
                        obs,
                        channels=int(getattr(model, "observation_channels", 8)),
                        height=int(getattr(model, "observation_height", 16)),
                        width=int(getattr(model, "observation_width", 16)),
                    )
                else:
                    obs_vector = observation_to_vector(obs)
                priors, values = priors_and_values_from_model(
                    model=model,
                    observation=obs_vector,
                    legal_actions=legal,
                    action_dim=action_dim,
                    unroll_steps=mcts_unroll_steps,
                    discount=mcts_discount,
                )
                try:
                    xai_root = xai_root_signals_from_model(
                        model=model,
                        observation=obs_vector,
                        legal_actions=legal,
                        action_dim=action_dim,
                        topk=5,
                    )
                    idxs = list(xai_root.get("latent_top_indices", []) or [])
                    latent_top_dims = ",".join(f"d{int(i)}" for i in idxs[:5])
                except Exception:
                    latent_top_dims = ""
                    xai_root = {}
            unit_prefilter_requested = bool(unit_prefilter_enabled) or bool(unit_prefilter_replan_enabled)
            mcts_out = None
            action = ""
            if unit_prefilter_requested and bool(unit_prefilter_replan_enabled):
                terrain_cover_for_rank = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
                terrain_los_for_rank = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
                selected_unit_id, _selected_actions, ranking_rows = ezv2_unit_prefilter_ranking(
                    legal_actions=[str(a) for a in list(legal_for_step or [])],
                    units=[dict(u or {}) for u in list(obs_units or []) if isinstance(u, dict)],
                    vp_hexes=[dict(v or {}) for v in list(obs_vp_hexes or []) if isinstance(v, dict)],
                    vp_owner_by_hex=dict(getattr(obs, "vp_owner_by_hex", {}) or {}),
                    to_play=str(active_side),
                    terrain_cover_by_hex=dict(terrain_cover_for_rank),
                    terrain_los_block_by_hex=dict(terrain_los_for_rank),
                    top_k=max(1, int(unit_prefilter_top_k)),
                    vp_progress_weight=float(unit_prefilter_vp_progress_weight),
                    capture_opportunity_weight=float(unit_prefilter_capture_opportunity_weight),
                    threat_weight=float(unit_prefilter_threat_weight),
                )
                ranked_unit_ids = [str((r or {}).get("unit_id", "")).strip() for r in list(ranking_rows or [])]
                ranked_unit_ids = [u for u in ranked_unit_ids if u]
                if selected_unit_id and selected_unit_id not in ranked_unit_ids:
                    ranked_unit_ids.insert(0, str(selected_unit_id))
                if not ranked_unit_ids:
                    ranked_unit_ids = sorted(
                        list(
                            {
                                str(a).split(":")[1]
                                for a in list(legal_for_step or [])
                                if len(str(a).split(":")) > 1 and str(a).split(":")[1]
                            }
                        )
                    )
                best_plan = None
                for unit_id in ranked_unit_ids[: max(1, int(unit_prefilter_top_k))]:
                    unit_actions = [
                        str(a)
                        for a in list(legal_for_step or [])
                        if len(str(a).split(":")) > 1 and str(a).split(":")[1] == str(unit_id)
                    ]
                    if not unit_actions:
                        continue
                    priors_u = {str(a): float(priors.get(str(a), 0.0)) for a in unit_actions} if isinstance(priors, dict) else None
                    values_u = {str(a): float(values.get(str(a), 0.0)) for a in unit_actions} if isinstance(values, dict) else None
                    signs_u = {str(a): int(signs.get(str(a), 1)) for a in unit_actions} if isinstance(signs, dict) else None
                    mcts_u = _run_policy_mcts(
                        legal_actions=unit_actions,
                        num_simulations=mcts_simulations,
                        c_puct=mcts_c_puct,
                        temperature=mcts_temperature,
                        dirichlet_alpha=float(mcts_dirichlet_alpha),
                        dirichlet_epsilon=float(mcts_dirichlet_epsilon),
                        priors_by_action=priors_u,
                        values_by_action=values_u,
                        value_sign_by_action=signs_u,
                        q_clip_abs=float(mcts_q_clip_abs),
                        min_root_visits_per_action=int(mcts_min_root_visits_per_action),
                        min_root_visits_top_n=int(mcts_min_root_visits_top_n),
                    )
                    chosen_u = str(getattr(mcts_u, "chosen_action", "") or "")
                    probs_u = [float(x) for x in list(getattr(mcts_u, "probs", []) or [])]
                    actions_u = [str(x) for x in list(getattr(mcts_u, "actions", []) or [])]
                    chosen_prob_u = 0.0
                    for aid_u, p_u in zip(actions_u, probs_u):
                        if str(aid_u) == str(chosen_u):
                            chosen_prob_u = float(p_u)
                            break
                    if chosen_prob_u <= 0.0 and probs_u:
                        chosen_prob_u = float(max(probs_u))
                    visits_u = [int(v) for v in list(getattr(mcts_u, "visits", []) or [])]
                    chosen_visits_u = 0
                    for aid_u, v_u in zip(actions_u, visits_u):
                        if str(aid_u) == str(chosen_u):
                            chosen_visits_u = int(v_u)
                            break
                    plan = {
                        "unit_id": str(unit_id),
                        "mcts": mcts_u,
                        "chosen_action": chosen_u,
                        "chosen_prob": float(chosen_prob_u),
                        "chosen_visits": int(chosen_visits_u),
                    }
                    if best_plan is None:
                        best_plan = plan
                    else:
                        if (
                            float(plan["chosen_prob"]) > float(best_plan["chosen_prob"])
                            or (
                                abs(float(plan["chosen_prob"]) - float(best_plan["chosen_prob"])) <= 1e-12
                                and int(plan["chosen_visits"]) > int(best_plan["chosen_visits"])
                            )
                        ):
                            best_plan = plan
                if best_plan is not None:
                    mcts_out = best_plan["mcts"]
                    action = str(best_plan["chosen_action"] or "")
            if mcts_out is None:
                mcts_out = _run_policy_mcts(
                    legal_actions=legal,
                    num_simulations=mcts_simulations,
                    c_puct=mcts_c_puct,
                    temperature=mcts_temperature,
                    dirichlet_alpha=float(mcts_dirichlet_alpha),
                    dirichlet_epsilon=float(mcts_dirichlet_epsilon),
                    priors_by_action=priors,
                    values_by_action=values,
                    value_sign_by_action=signs,
                    q_clip_abs=float(mcts_q_clip_abs),
                    min_root_visits_per_action=int(mcts_min_root_visits_per_action),
                    min_root_visits_top_n=int(mcts_min_root_visits_top_n),
                )
                action = mcts_out.chosen_action
            probs = [float(x) for x in (mcts_out.probs or [])]
            visit_counts = [int(v) for v in (mcts_out.visits or [])]
            visit_total = int(sum(visit_counts))
            if probs:
                chosen_prob = 0.0
                for a_id, p in zip(list(mcts_out.actions or []), probs):
                    if str(a_id) == str(action):
                        chosen_prob = float(p)
                        break
                if chosen_prob <= 0.0:
                    chosen_prob = float(max(probs))
                top2 = sorted(probs, reverse=True)[:2]
                margin = float(top2[0] - top2[1]) if len(top2) > 1 else float(top2[0])
                # Entropy should describe root search spread, not temperature-shaped
                # decision probabilities used to pick the final action.
                entropy_probs = (
                    [float(max(0.0, v)) / float(visit_total) for v in visit_counts]
                    if visit_total > 0
                    else list(probs)
                )
                for p in entropy_probs:
                    pp = float(max(1e-12, p))
                    mcts_entropy += -pp * math.log(pp)
            mcts_total_visits = int(visit_total)
            mcts_active_actions = int(sum(1 for v in (mcts_out.visits or []) if int(v) > 0))
            visits_by_action = {
                str(a): int(v)
                for a, v in zip(list(mcts_out.actions or []), list(mcts_out.visits or []))
            }
            mcts_breakdown_by_action = {}
            for b in list(getattr(mcts_out, "root_candidate_breakdown", []) or []):
                if not isinstance(b, dict):
                    continue
                aid_b = str(b.get("action_id", "") or "")
                if aid_b:
                    mcts_breakdown_by_action[aid_b] = dict(b)
            acting_unit_id_probe = str(action or "").split(":")
            acting_unit_id_probe = acting_unit_id_probe[1] if len(acting_unit_id_probe) > 1 else ""
            acting_unit_probe = next(
                (
                    u
                    for u in obs_units
                    if str(getattr(u, "unit_id", "") or "") == str(acting_unit_id_probe)
                ),
                None,
            )
            acting_q_probe = (
                _to_int_or_none(_field(acting_unit_probe, "q", None))
                if acting_unit_probe is not None
                else None
            )
            acting_r_probe = (
                _to_int_or_none(_field(acting_unit_probe, "r", None))
                if acting_unit_probe is not None
                else None
            )
            why_action_vs_vp = _build_why_action_vs_vp(
                legal_actions=legal_for_step,
                chosen_action=str(action),
                priors_by_action=priors if isinstance(priors, dict) else None,
                values_by_action=values if isinstance(values, dict) else None,
                value_sign_by_action=signs if isinstance(signs, dict) else None,
                visits_by_action=visits_by_action,
                c_puct=float(mcts_c_puct),
                dynamics_pred_reward=None,
                acting_unit_q=acting_q_probe,
                acting_unit_r=acting_r_probe,
                step_units_snapshot=obs_units,
                vp_hexes=obs_vp_hexes,
                active_side=str(active_side),
                vp_owner_by_hex=dict(getattr(obs, "vp_owner_by_hex", {}) or {}),
                top_k=decision_top_k_effective,
                q_clip_abs=float(mcts_q_clip_abs),
            )
            mcts_action_candidates = list(
                why_action_vs_vp.get("candidate_actions", []) or []
            )
            # Emit explicit producer-only replay fields for chosen probability
            # and visit-share diagnostics per candidate action.
            probs_by_action = {
                str(a): float(p)
                for a, p in zip(list(mcts_out.actions or []), list(mcts_out.probs or []))
            }
            total_visits_f = float(max(0, int(visit_total)))
            chosen_action_text = str(action or "")
            enriched_candidates: List[Dict[str, object]] = []
            for c in list(mcts_action_candidates or []):
                c_out = dict(c or {})
                aid = str(c_out.get("action_id", "") or "")
                breakdown_row = dict(mcts_breakdown_by_action.get(aid, {}) or {})
                if aid and breakdown_row:
                    if c_out.get("mcts_q_value", None) is None and breakdown_row.get("q_value", None) is not None:
                        c_out["mcts_q_value"] = float(breakdown_row.get("q_value"))
                    if c_out.get("mcts_u_value", None) is None and breakdown_row.get("u_value", None) is not None:
                        c_out["mcts_u_value"] = float(breakdown_row.get("u_value"))
                    c_out["mcts_q_unclipped"] = (
                        float(breakdown_row.get("q_unclipped"))
                        if breakdown_row.get("q_unclipped", None) is not None
                        else None
                    )
                    c_out["mcts_q_clipped"] = (
                        float(breakdown_row.get("q_clipped"))
                        if breakdown_row.get("q_clipped", None) is not None
                        else None
                    )
                    c_out["mcts_q_norm_applied"] = bool(
                        breakdown_row.get(
                            "q_norm_applied",
                            getattr(mcts_out, "q_root_normalization_applied", False),
                        )
                    )
                vc = int(max(0, int(c_out.get("visit_count", 0) or 0)))
                dc_raw = c_out.get("decision_components", {})
                dc = dict(dc_raw) if isinstance(dc_raw, dict) else {}
                c_out["visit_share"] = (
                    float(vc) / total_visits_f if total_visits_f > 0.0 else None
                )
                # Emit per-candidate probability and selection source for every row
                # so replay tables do not show N/A for non-selected candidates.
                c_out["chosen_action_prob"] = (
                    float(probs_by_action.get(aid, 0.0))
                    if aid in probs_by_action
                    else 0.0
                )
                c_out["selection_source"] = (
                    "mcts_prob_sample" if aid == chosen_action_text else "mcts_prob_non_selected"
                )
                c_out["policy_prior_source"] = (
                    "producer_policy_head_prior"
                    if c_out.get("policy_prior", None) is not None
                    else "missing"
                )
                c_out["policy_prior_available"] = bool(c_out.get("policy_prior", None) is not None)
                c_out["mcts_q_value_source"] = (
                    "producer_mcts_breakdown"
                    if c_out.get("mcts_q_value", None) is not None
                    else "missing"
                )
                c_out["mcts_q_value_available"] = bool(c_out.get("mcts_q_value", None) is not None)
                c_out["mcts_u_value_source"] = (
                    "producer_mcts_breakdown"
                    if c_out.get("mcts_u_value", None) is not None
                    else "missing"
                )
                c_out["mcts_u_value_available"] = bool(c_out.get("mcts_u_value", None) is not None)
                c_out["mcts_success_prob_proxy_source"] = (
                    "decision_components"
                    if dc.get("mcts_success_prob_proxy", dc.get("success_prob_proxy", None)) is not None
                    else "missing"
                )
                c_out["mcts_success_prob_proxy_available"] = bool(
                    dc.get("mcts_success_prob_proxy", dc.get("success_prob_proxy", None)) is not None
                )
                c_out["mcts_success_component_source"] = (
                    "decision_components"
                    if dc.get("mcts_success_component", dc.get("success_component", None)) is not None
                    else "missing"
                )
                c_out["mcts_success_component_available"] = bool(
                    dc.get("mcts_success_component", dc.get("success_component", None)) is not None
                )
                c_out["vp_horizon_steps_available"] = bool(c_out.get("vp_horizon_steps", None) is not None)
                c_out["vp_horizon_signal_available"] = bool(c_out.get("vp_horizon_signal", None) is not None)
                c_out["vp_horizon_decision_component_available"] = bool(
                    c_out.get("vp_horizon_decision_component", c_out.get("vp_horizon_component", None)) is not None
                )
                enriched_candidates.append(c_out)
            if not enriched_candidates:
                # Keep producer telemetry complete even in degenerate roots with
                # no candidate rows emitted from upstream MCTS.
                enriched_candidates.append(
                    {
                        "action_id": chosen_action_text,
                        "selected_action": True,
                        "visit_count": 0,
                        "visit_share": 0.0,
                        "chosen_action_prob": float(chosen_prob),
                        "selection_source": "fallback_no_candidates",
                        "policy_prior": None,
                        "mcts_q_value": None,
                        "mcts_u_value": None,
                        "decision_rank": 1,
                        "real_decision_score": float(chosen_prob),
                        "policy_prior_source": "fallback_missing",
                        "policy_prior_available": False,
                        "mcts_q_value_source": "fallback_missing",
                        "mcts_q_value_available": False,
                        "mcts_u_value_source": "fallback_missing",
                        "mcts_u_value_available": False,
                        "mcts_success_prob_proxy_source": "fallback_missing",
                        "mcts_success_prob_proxy_available": False,
                        "mcts_success_component_source": "fallback_missing",
                        "mcts_success_component_available": False,
                        "vp_horizon_steps_available": False,
                        "vp_horizon_signal_available": False,
                        "vp_horizon_decision_component_available": False,
                        "decision_components": {
                            "mcts_success_component": None,
                            "success_component": None,
                            "mcts_success_prob_proxy": None,
                            "success_prob_proxy": None,
                            "vp_horizon_steps": None,
                            "vp_horizon_signal": None,
                            "vp_horizon_component": None,
                            "vp_horizon_decision_component": None,
                            "objective_soft_reward_component": None,
                            "global_strategy_soft_reward_component": None,
                            "reaction_fire_soft_reward_component": None,
                            "tie_break_term": None,
                        },
                    }
                )
            mcts_action_candidates = list(enriched_candidates)
            if isinstance(why_action_vs_vp, dict):
                why_action_vs_vp["candidate_actions"] = list(mcts_action_candidates)
            if model is not None:
                policy_top_actions = [str(a) for a in (xai_root.get("policy_top_actions", []) or [])]
                policy_top_probs = [float(v) for v in (xai_root.get("policy_top_probs", []) or [])]
                policy_top_action = str(policy_top_actions[0]) if policy_top_actions else ""
                policy_overridden_by_mcts = (
                    int(policy_top_action != str(action))
                    if policy_top_action
                    else None
                )
                latent_top_indices = [int(v) for v in (xai_root.get("latent_top_indices", []) or [])]
                latent_top_values = [float(v) for v in (xai_root.get("latent_top_values", []) or [])]
                latent_l2_norm = (
                    float(xai_root.get("latent_l2_norm", 0.0))
                    if xai_root.get("latent_l2_norm", None) is not None
                    else None
                )
                predicted_value_root = (
                    float(xai_root.get("predicted_value_root", 0.0))
                    if xai_root.get("predicted_value_root", None) is not None
                    else None
                )
                try:
                    xai_dyn = xai_dynamics_signals_for_action(
                        model=model,
                        observation=obs_vector,
                        chosen_action_id=action,
                        action_dim=action_dim,
                    )
                except Exception:
                    xai_dyn = {}
                dynamics_pred_reward = (
                    float(xai_dyn.get("dynamics_pred_reward", 0.0))
                    if xai_dyn.get("dynamics_pred_reward", None) is not None
                    else None
                )
                dynamics_next_latent_l2 = (
                    float(xai_dyn.get("dynamics_next_latent_l2", 0.0))
                    if xai_dyn.get("dynamics_next_latent_l2", None) is not None
                    else None
                )
                dynamics_delta_l2 = (
                    float(xai_dyn.get("dynamics_delta_l2", 0.0))
                    if xai_dyn.get("dynamics_delta_l2", None) is not None
                    else None
                )
                if isinstance(why_action_vs_vp, dict):
                    why_action_vs_vp["candidate_actions"] = list(mcts_action_candidates or [])
                head_states = {
                    "policy": _head_state(
                        "complete" if policy_top_actions and policy_top_probs else "partial",
                        "" if policy_top_actions and policy_top_probs else "policy_topk_missing",
                    ),
                    "value": _head_state(
                        "complete" if predicted_value_root is not None else "none",
                        "" if predicted_value_root is not None else "value_root_missing",
                    ),
                    "reward": _head_state(
                        "complete" if dynamics_pred_reward is not None else "none",
                        "" if dynamics_pred_reward is not None else "dynamics_reward_missing",
                    ),
                    "objective": _head_state("partial", "objective_signal_not_computed"),
                    "consistency": _head_state(
                        "complete" if (latent_top_indices and latent_top_values) else "partial",
                        "" if (latent_top_indices and latent_top_values) else "latent_topk_missing",
                    ),
                    "mcts": _head_state("complete", ""),
                }
            else:
                head_states = {h: _head_state("none", "model_not_loaded") for h in HEAD_NAMES}
        action_kind = _action_kind_from_id(action)
        capture_taken = _is_capture_like_action_kind(action_kind)
        objective_signal = None
        objective_had_opportunity = 0
        objective_progress_delta = None
        objective_converted = 0
        objective_min_dist_before = -1.0
        objective_min_dist_after = -1.0
        objective_best_vp_id = ""
        vp_distance_vector = {}
        before_vp_owner = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
        telemetry_coverage_status, telemetry_coverage_reason = _compute_coverage_status(head_states)
        if collect_this_step:
            phase29["xai_decision_steps"] += 1
            phase29["xai_policy_confidence_sum"] += float(chosen_prob)
            phase29["xai_policy_margin_sum"] += float(margin)
            if str(latent_top_dims).strip():
                phase29["xai_latent_signal_steps"] += 1
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["xai_decision_steps"] += 1
            side_bucket["xai_policy_confidence_sum"] += float(chosen_prob)
            side_bucket["xai_policy_margin_sum"] += float(margin)
            if str(latent_top_dims).strip():
                side_bucket["xai_latent_signal_steps"] += 1
        action_parts = str(action or "").split(":")
        acting_unit_id = action_parts[1] if len(action_parts) > 1 else ""
        acting_unit = next((u for u in obs_units if str(getattr(u, "unit_id", "") or "") == str(acting_unit_id)), None)
        transition = adapter.apply(action)
        transition_info = getattr(transition, "info", None)
        (
            attack_dice_rolls,
            defense_dice_rolls,
            attack_components_by_die,
            defense_components_by_die,
            runtime_events,
        ) = _extract_actor_combat_dice_signals(
            transition_info=transition_info,
            acting_unit_id=str(acting_unit_id),
        )
        post_units = getattr(transition.state, "units", []) or []
        post_obs = adapter.observation()
        after_vp_owner = dict(getattr(post_obs, "vp_owner_by_hex", {}) or {})
        vp_captures_eval = 0
        for key, owner_before in before_vp_owner.items():
            owner_after = str(after_vp_owner.get(key, ""))
            if str(owner_before) != owner_after and owner_after == str(active_side):
                vp_captures_eval += 1
        immediate_capture_legal_count = _count_immediate_vp_capture_move_options(
            side=str(active_side),
            legal_actions=legal_for_step,
            vp_hexes=obs_vp_hexes,
            vp_owner_by_hex=before_vp_owner,
        )
        immediate_capture_taken = _is_immediate_vp_capture_move_taken(
            side=str(active_side),
            chosen_action_id=str(action),
            vp_hexes=obs_vp_hexes,
            before_vp_owner_by_hex=before_vp_owner,
            after_vp_owner_by_hex=after_vp_owner,
        )
        objective_signal = objective_step_signal(
            side=str(active_side),
            vp_hexes=obs_vp_hexes,
            legal_actions=legal_for_step,
            before_units=_units_snapshot(obs_units),
            before_vp_owner_by_hex=before_vp_owner,
            after_units=_units_snapshot(getattr(post_obs, "units", []) or []),
            after_vp_owner_by_hex=after_vp_owner,
            legal_capture_options=int(immediate_capture_legal_count),
            capture_taken=bool(immediate_capture_taken),
            vp_captures=int(vp_captures_eval),
            vp_gain_for_side=int(vp_captures_eval),
        )
        objective_had_opportunity = int(objective_signal.objective_had_opportunity)
        objective_progress_delta = float(objective_signal.objective_progress_delta)
        objective_converted = int(objective_signal.objective_converted)
        objective_min_dist_before = float(objective_signal.objective_min_dist_before)
        objective_min_dist_after = float(objective_signal.objective_min_dist_after)
        objective_best_vp_id = str(objective_signal.objective_best_vp_id)
        vp_distance_vector = dict(objective_signal.vp_distance_vector)
        why_action_vs_vp = _backfill_why_action_vs_vp_from_observed_transition(
            why_action_vs_vp=why_action_vs_vp,
            chosen_action=str(action),
            objective_progress_delta=objective_progress_delta,
            objective_best_vp_id=objective_best_vp_id,
            legal_actions=legal_actions_list,
        )
        mcts_action_candidates = list(why_action_vs_vp.get("candidate_actions", []) or [])
        selected_candidate = next(
            (
                c
                for c in list(mcts_action_candidates or [])
                if str((c or {}).get("action_id", "")) == str(action)
            ),
            None,
        )
        selected_candidate_dc = (
            dict((selected_candidate or {}).get("decision_components", {}) or {})
            if isinstance((selected_candidate or {}).get("decision_components", None), dict)
            else {}
        )
        strategy_label = str(
            selected_candidate_dc.get("tie_break_source", "")
            or why_action_vs_vp.get("explanation", "")
            or ""
        )
        if collect_this_step:
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            if int(objective_had_opportunity) > 0:
                phase29["xai_vp_capture_opportunity_steps"] += 1
                side_bucket["xai_vp_capture_opportunity_steps"] += 1
                if capture_taken:
                    phase29["xai_vp_capture_taken_steps"] += 1
                    side_bucket["xai_vp_capture_taken_steps"] += 1
            if int(immediate_capture_legal_count) > 0:
                phase29["xai_vp_immediate_capture_opportunity_steps"] += 1
                side_bucket["xai_vp_immediate_capture_opportunity_steps"] += 1
                if immediate_capture_taken:
                    phase29["xai_vp_immediate_capture_taken_steps"] += 1
                    side_bucket["xai_vp_immediate_capture_taken_steps"] += 1
        if isinstance(head_states, dict):
            if objective_min_dist_before >= 0.0 and objective_min_dist_after >= 0.0:
                head_states["objective"] = _head_state("complete", "")
            else:
                head_states["objective"] = _head_state("partial", "objective_signal_missing_vp_context")
            telemetry_coverage_status, telemetry_coverage_reason = _compute_coverage_status(head_states)
        side_hp_after = _side_hp_snapshot(post_units)
        side_alive_after = _side_alive_snapshot(post_units)
        enemy_damage = 0.0
        enemy_kills = 0
        for side_k, hp_before in side_hp_before.items():
            if _normalize_side_key(side_k) == _normalize_side_key(active_side):
                continue
            enemy_damage += max(0.0, float(hp_before - float(side_hp_after.get(side_k, hp_before))))
            enemy_kills += max(0, int(side_alive_before.get(side_k, 0) - side_alive_after.get(side_k, 0)))
        runtime_damage_actor, runtime_kills_actor = _extract_actor_damage_kills_from_runtime_events(
            runtime_events=runtime_events,
            acting_unit_id=str(acting_unit_id),
        )
        # Runtime ACTION_EFFECT payloads are authoritative for actor attribution
        # and remain valid even when obs snapshots hide enemy units.
        enemy_damage = max(float(enemy_damage), float(runtime_damage_actor))
        enemy_kills = max(int(enemy_kills), int(runtime_kills_actor))
        # Prefer explicit env telemetry when available; hp/alive deltas remain
        # as a fallback for older adapters that do not emit step-level info.
        if isinstance(transition_info, dict):
            info_damage_actor = _metric_from_row(
                transition_info,
                "damage_dealt",
                "damage",
                "enemy_damage",
                default=float(enemy_damage),
            )
            info_kills_actor = _metric_from_row(
                transition_info,
                "kills_dealt",
                "kills",
                "enemy_kills",
                default=float(enemy_kills),
            )
            # Keep legacy compatibility while avoiding stale zero clobbering.
            # Prefer explicit telemetry when positive or when no stronger
            # fallback signal is available from runtime events/snapshot deltas.
            if float(info_damage_actor) > 0.0 or float(enemy_damage) <= 0.0:
                enemy_damage = float(info_damage_actor)
            if (
                int(round(float(info_kills_actor))) > 0
                or int(enemy_kills) <= 0
            ):
                enemy_kills = int(round(float(info_kills_actor)))
        prefilter_info = dict(transition_info or {}) if isinstance(transition_info, dict) else {}
        raw_unit_prefilter_enabled = prefilter_info.get("unit_prefilter_enabled", None)
        unit_prefilter_enabled = (
            bool(raw_unit_prefilter_enabled)
            if raw_unit_prefilter_enabled is not None
            else False
        )
        unit_prefilter_selected_unit_id = str(
            prefilter_info.get(
                "unit_prefilter_selected_unit_id",
                "",
            )
            or ""
        )
        if not unit_prefilter_selected_unit_id.strip():
            unit_prefilter_selected_unit_id = "__none__"
        unit_prefilter_constrained_count = (
            _to_int_or_none(
                prefilter_info.get(
                    "unit_prefilter_constrained_count",
                    None,
                )
            )
        )
        if unit_prefilter_constrained_count is None:
            unit_prefilter_constrained_count = 0
        unit_prefilter_global_count = (
            _to_int_or_none(
                prefilter_info.get(
                    "unit_prefilter_global_count",
                    None,
                )
            )
        )
        if unit_prefilter_global_count is None:
            unit_prefilter_global_count = 0
        if collect_this_step and action_kind == "OPPORTUNITY_FIRE":
            phase29["reaction_fire_count"] += 1
            phase29["reaction_fire_damage_sum"] += float(enemy_damage)
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["reaction_fire_count"] += 1
            side_bucket["reaction_fire_damage_sum"] += float(enemy_damage)
            if int(enemy_kills) > 0:
                phase29["reaction_fire_kill_conversions"] += 1
                side_bucket["reaction_fire_kill_conversions"] += 1
        elif collect_this_step and action_kind == "OPPORTUNITY_SKIP":
            phase29["reaction_fire_skipped_count"] += 1
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["reaction_fire_skipped_count"] += 1
        if collect_this_step and ("ASSAULT" in action_kind or action_kind in {"MELEE", "ASSAULT_MELEE"}):
            phase29["melee_attempts"] += 1
            phase29["melee_damage_sum"] += float(enemy_damage)
            phase29["melee_kills_sum"] += float(enemy_kills)
            side_bucket = phase29_by_side.setdefault(active_side, _new_phase29_bucket())
            side_bucket["melee_attempts"] += 1
            side_bucket["melee_damage_sum"] += float(enemy_damage)
            side_bucket["melee_kills_sum"] += float(enemy_kills)
            if float(enemy_damage) > 0.0 or int(enemy_kills) > 0:
                phase29["melee_success_count"] += 1
                side_bucket["melee_success_count"] += 1
            bucket = _assault_advantage_bucket(chosen_prob=float(chosen_prob), margin=float(margin), legal_count=len(legal_for_step))
            phase29[f"assault_{bucket}_count"] += 1
            side_bucket[f"assault_{bucket}_count"] += 1
        if transition.done:
            terminal_reason = str(transition.state.end_reason or "natural_terminal")
            winner = transition.state.winner
            winner_side = str(winner) if winner is not None else ""
            if winner is None:
                total_reward += 0.0
                win = False
            else:
                won = str(winner) == eval_side
                total_reward += 1.0 if won else -1.0
                win = won
        # Target coordinates/dimensions (explicitly parsed from action id if available).
        target_q = _to_int_or_none(action_parts[-2]) if len(action_parts) >= 4 else None
        target_r = _to_int_or_none(action_parts[-1]) if len(action_parts) >= 4 else None
        acting_q = _to_int_or_none(_field(acting_unit, "q", None)) if acting_unit is not None else None
        acting_r = _to_int_or_none(_field(acting_unit, "r", None)) if acting_unit is not None else None
        attack_distance = -1.0
        if isinstance(acting_q, int) and isinstance(acting_r, int) and isinstance(target_q, int) and isinstance(target_r, int):
            attack_distance = float(max(abs(int(acting_q) - int(target_q)), abs(int(acting_r) - int(target_r))))
        cover_map = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
        los_map = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
        key_qr = f"{int(target_q)},{int(target_r)}" if isinstance(target_q, int) and isinstance(target_r, int) else ""
        target_cover = float(cover_map.get(key_qr, -1.0)) if key_qr else -1.0
        target_los = float(los_map.get(key_qr, -1.0)) if key_qr else -1.0

        legal_actions_decoded_target_qr = []
        acting_unit_action_catalog = []
        for idx, action_id_item in enumerate(legal_actions_list):
            parsed_target = _parse_action_target_hex(action_id=action_id_item)
            legal_actions_decoded_target_qr.append(
                {
                    "catalog_index": int(idx),
                    "action_id": str(action_id_item),
                    "target_q": int(parsed_target[0]) if parsed_target is not None else None,
                    "target_r": int(parsed_target[1]) if parsed_target is not None else None,
                }
            )
            parts = str(action_id_item).split(":")
            action_unit_id = parts[1] if len(parts) > 1 else ""
            if str(action_unit_id) == str(acting_unit_id):
                acting_unit_action_catalog.append(
                    {
                        "catalog_index": int(idx),
                        "action_id": str(action_id_item),
                    }
                )

        selected_candidate = next(
            (
                dict(c or {})
                for c in list(mcts_action_candidates or [])
                if str(c.get("action_id", "")) == str(action)
            ),
            {},
        )
        if not selected_candidate and list(mcts_action_candidates or []):
            selected_candidate = dict((mcts_action_candidates or [])[0] or {})
        info_vp_horizon_steps = _field(transition_info, "vp_horizon_steps", None)
        info_vp_horizon_signal = _field(transition_info, "vp_horizon_signal", None)
        info_vp_horizon_component = _field(
            transition_info, "vp_horizon_decision_component", None
        )
        if info_vp_horizon_component is None:
            info_vp_horizon_component = _field(
                transition_info, "vp_horizon_component", None
            )
        raw_selected_vp_horizon_steps = selected_candidate.get(
            "vp_horizon_steps",
            info_vp_horizon_steps,
        )
        raw_selected_vp_horizon_signal = selected_candidate.get(
            "vp_horizon_signal",
            info_vp_horizon_signal,
        )
        raw_selected_vp_horizon_component = selected_candidate.get(
            "vp_horizon_decision_component",
            selected_candidate.get(
                "vp_horizon_component",
                info_vp_horizon_component,
            ),
        )
        try:
            selected_vp_horizon_steps = (
                float(raw_selected_vp_horizon_steps)
                if raw_selected_vp_horizon_steps is not None
                else None
            )
        except Exception:
            selected_vp_horizon_steps = None
        try:
            selected_vp_horizon_signal = (
                float(raw_selected_vp_horizon_signal)
                if raw_selected_vp_horizon_signal is not None
                else None
            )
        except Exception:
            selected_vp_horizon_signal = None
        try:
            selected_vp_horizon_component = (
                float(raw_selected_vp_horizon_component)
                if raw_selected_vp_horizon_component is not None
                else None
            )
        except Exception:
            selected_vp_horizon_component = None
        selected_components = (
            dict(selected_candidate.get("decision_components", {}) or {})
            if isinstance(selected_candidate.get("decision_components", None), dict)
            else {}
        )
        raw_tie_break_term = (
            selected_components.get("tie_break_term", None)
            if isinstance(selected_components, dict)
            else None
        )
        if raw_tie_break_term is None:
            raw_tie_break_term = _field(transition_info, "tie_break_term", None)
        try:
            selected_tie_break_term = float(raw_tie_break_term) if raw_tie_break_term is not None else None
        except Exception:
            selected_tie_break_term = None
        unit_positions_snapshot: List[Dict[str, object]] = []
        unit_hp_snapshot: Dict[str, float] = {}
        unit_alive_snapshot: Dict[str, bool] = {}
        unit_suppressed_snapshot: Dict[str, bool] = {}
        for u in list(obs_units or []):
            try:
                u_q = _to_int_or_none(_field(u, "q", None))
                u_r = _to_int_or_none(_field(u, "r", None))
                u_id = str(_field(u, "unit_id", "") or "")
                if u_id:
                    hp_raw = _field(u, "hp", None)
                    if hp_raw is not None:
                        try:
                            unit_hp_snapshot[u_id] = float(hp_raw)
                        except Exception:
                            pass
                    alive_raw = _field(u, "alive", None)
                    if alive_raw is not None:
                        unit_alive_snapshot[u_id] = bool(alive_raw)
                    suppressed_raw = _unit_suppressed_state_from_raw(u)
                    if suppressed_raw is not None:
                        unit_suppressed_snapshot[u_id] = bool(suppressed_raw)
                if u_q is None or u_r is None:
                    continue
                unit_positions_snapshot.append(
                    {
                        "unit_id": str(_field(u, "unit_id", "") or ""),
                        "side": str(_field(u, "side", "") or ""),
                        "q": int(u_q),
                        "r": int(u_r),
                    }
                )
            except Exception:
                continue

        entropy_collapse = bool(
            int(len(legal_for_step)) > 1
            and int(mcts_total_visits) > 0
            and float(mcts_entropy) <= 1e-6
        )
        raw_mcts_prior = selected_candidate.get("policy_prior", None)
        raw_mcts_q = selected_candidate.get("mcts_q_value", None)
        raw_mcts_u = selected_candidate.get("mcts_u_value", None)
        raw_decision_score = next(
            (
                c.get("real_decision_score", c.get("final_score", None))
                for c in list(mcts_action_candidates or [])
                if str(c.get("action_id", "")) == str(action)
            ),
            None,
        )
        raw_selected_success_proxy = selected_components.get(
            "mcts_success_prob_proxy",
            selected_components.get("success_prob_proxy", None),
        )
        raw_selected_success_component = selected_components.get(
            "mcts_success_component",
            selected_components.get("success_component", None),
        )
        def _safe_float_or_none(v):
            if v is None:
                return None
            try:
                out = float(v)
            except Exception:
                return None
            return out if math.isfinite(out) else None
        mcts_prior_value = _safe_float_or_none(raw_mcts_prior)
        mcts_q_value = _safe_float_or_none(raw_mcts_q)
        mcts_u_value = _safe_float_or_none(raw_mcts_u)
        decision_score_value = _safe_float_or_none(raw_decision_score)
        selected_success_proxy = _safe_float_or_none(raw_selected_success_proxy)
        selected_success_component = _safe_float_or_none(raw_selected_success_component)
        trace_rows.append(
            {
                "step": int(steps),
                "game_turn": int(getattr(obs, "turn", 0) or 0),
                "turn": int(getattr(transition.state, "turn", 0) or 0),
                "to_play": str(active_side),
                "action_id": str(action),
                "mcts_chosen_action": str(action),
                "requested_action_id": str(action),
                "action_kind": str(action_kind),
                "legal_capture_like_options": int(capture_legal_count),
                "capture_like_taken": bool(capture_taken),
                "chosen_prob": float(chosen_prob),
                "policy_margin": float(margin),
                "chosen_action_prob": float(chosen_prob),
                "mcts_prior": mcts_prior_value,
                "mcts_prior_source": str(
                    selected_candidate.get("policy_prior_source", "missing")
                    if mcts_prior_value is not None
                    else "missing"
                ),
                "mcts_prior_available": bool(mcts_prior_value is not None),
                "mcts_q_value": mcts_q_value,
                "mcts_q_value_source": str(
                    selected_candidate.get("mcts_q_value_source", "missing")
                    if mcts_q_value is not None
                    else "missing"
                ),
                "mcts_q_value_available": bool(mcts_q_value is not None),
                "mcts_u_value": mcts_u_value,
                "mcts_u_value_source": str(
                    selected_candidate.get("mcts_u_value_source", "missing")
                    if mcts_u_value is not None
                    else "missing"
                ),
                "mcts_u_value_available": bool(mcts_u_value is not None),
                "mcts_margin": float(margin),
                "mcts_entropy": float(mcts_entropy),
                "mcts_total_visits": int(mcts_total_visits),
                "mcts_active_actions": int(mcts_active_actions),
                "mcts_entropy_source": "root_visit_distribution",
                "mcts_entropy_collapse": bool(entropy_collapse),
                "mcts_entropy_collapse_label": (
                    "collapsed_root_distribution" if entropy_collapse else "ok"
                ),
                "mcts_q_guardrail_clipped_count": int(
                    getattr(mcts_out, "q_guardrail_clipped_count", 0)
                ),
                "mcts_q_guardrail_clip_limit": (
                    float(getattr(mcts_out, "q_guardrail_clip_limit", 0.0))
                    if getattr(mcts_out, "q_guardrail_clip_limit", None) is not None
                    else None
                ),
                "legal_actions": list(legal_actions_list),
                "legal_actions_decoded_target_qr": list(legal_actions_decoded_target_qr),
                "acting_unit_action_catalog": list(acting_unit_action_catalog),
                "unit_id": str(acting_unit_id),
                "unit_side": str(active_side),
                "unit_label": (
                    str(getattr(acting_unit, "unit_label", "") or "")
                    if acting_unit is not None
                    else str(acting_unit_id)
                ),
                "reward": float(transition.reward),
                "done": bool(transition.done),
                "damage_dealt": float(enemy_damage),
                "kills_dealt": int(enemy_kills),
                "enemy_damage": float(enemy_damage),
                "enemy_kills": int(enemy_kills),
                "attack_target_unit_id": (
                    str(action_parts[2]) if len(action_parts) > 2 else ""
                ),
                "target_q": int(target_q) if isinstance(target_q, int) else None,
                "target_r": int(target_r) if isinstance(target_r, int) else None,
                "attack_distance_mean": float(attack_distance),
                "attack_target_cover_mean": float(target_cover),
                "attack_target_los_block_mean": float(target_los),
                "latent_top_dims": str(latent_top_dims),
                "policy_top_actions": list(policy_top_actions),
                "policy_top_probs": list(policy_top_probs),
                "mcts_action_candidates": list(mcts_action_candidates),
                "why_action_vs_vp": dict(why_action_vs_vp),
                "why_action_vs_vp_text": str(why_action_vs_vp.get("explanation", "")),
                "vp_horizon_steps": (
                    float(selected_vp_horizon_steps)
                    if selected_vp_horizon_steps is not None
                    else None
                ),
                "vp_horizon_signal": (
                    float(selected_vp_horizon_signal)
                    if selected_vp_horizon_signal is not None
                    else None
                ),
                "vp_horizon_decision_component": (
                    float(selected_vp_horizon_component)
                    if selected_vp_horizon_component is not None
                    else None
                ),
                "vp_horizon_component": (
                    float(selected_vp_horizon_component)
                    if selected_vp_horizon_component is not None
                    else None
                ),
                "vp_horizon_source": (
                    str(selected_candidate.get("vp_horizon_source", "missing"))
                    if selected_vp_horizon_steps is not None
                    else "missing"
                ),
                "vp_horizon_available": bool(selected_vp_horizon_steps is not None),
                "real_decision_score": decision_score_value,
                "decision_score_selected_source": (
                    "mcts_action_candidates"
                    if decision_score_value is not None
                    else "missing"
                ),
                "decision_score_selected_available": bool(decision_score_value is not None),
                "decision_rank": int(
                    next(
                        (
                            int(c.get("decision_rank", 0) or 0)
                            for c in list(mcts_action_candidates or [])
                            if str(c.get("action_id", "")) == str(action)
                        ),
                        0,
                    )
                ),
                "decision_win_basis": (
                    "mcts_puct"
                    if list(mcts_action_candidates or [])
                    else "policy_or_random"
                ),
                "policy_top_action": str(policy_top_action),
                "policy_overridden_by_mcts": policy_overridden_by_mcts,
                "override_sanity_consistent": (
                    None
                    if policy_overridden_by_mcts is None
                    else int(int(policy_overridden_by_mcts) == int(str(policy_top_action) != str(action)))
                ),
                "latent_top_indices": list(latent_top_indices),
                "latent_top_values": list(latent_top_values),
                "latent_l2_norm": latent_l2_norm,
                "predicted_value_root": predicted_value_root,
                "dynamics_pred_reward": dynamics_pred_reward,
                "dynamics_next_latent_l2": dynamics_next_latent_l2,
                "dynamics_delta_l2": dynamics_delta_l2,
                "objective_soft_reward_component": (
                    float(_field(transition_info, "objective_soft_reward_component", 0.0))
                    if _field(transition_info, "objective_soft_reward_component", None) is not None
                    else None
                ),
                "global_strategy_soft_reward_component": (
                    float(_field(transition_info, "global_strategy_soft_reward_component", 0.0))
                    if _field(transition_info, "global_strategy_soft_reward_component", None) is not None
                    else None
                ),
                "reaction_fire_soft_reward_component": (
                    float(_field(transition_info, "reaction_fire_soft_reward_component", 0.0))
                    if _field(transition_info, "reaction_fire_soft_reward_component", None) is not None
                    else None
                ),
                "reaction_fire_soft_reward_component_source": (
                    "transition_info"
                    if _field(transition_info, "reaction_fire_soft_reward_component", None) is not None
                    else "missing"
                ),
                "reaction_fire_soft_reward_component_available": bool(
                    _field(transition_info, "reaction_fire_soft_reward_component", None) is not None
                ),
                "reaction_exposure_component": (
                    float(_field(transition_info, "reaction_exposure_component", 0.0))
                    if _field(transition_info, "reaction_exposure_component", None) is not None
                    else None
                ),
                "reaction_exposure_component_source": (
                    "transition_info"
                    if _field(transition_info, "reaction_exposure_component", None) is not None
                    else "missing"
                ),
                "reaction_exposure_component_available": bool(
                    _field(transition_info, "reaction_exposure_component", None) is not None
                ),
                "mcts_success_prob_proxy": selected_success_proxy,
                "mcts_success_prob_proxy_source": (
                    "decision_components"
                    if selected_success_proxy is not None
                    else "missing"
                ),
                "mcts_success_prob_proxy_available": bool(selected_success_proxy is not None),
                "mcts_success_component": selected_success_component,
                "mcts_success_component_source": (
                    "decision_components"
                    if selected_success_component is not None
                    else "missing"
                ),
                "mcts_success_component_available": bool(selected_success_component is not None),
                "legal_capture_options": int(immediate_capture_legal_count),
                "objective_had_opportunity": int(objective_had_opportunity),
                "objective_distance_before": float(objective_min_dist_before),
                "objective_distance_after": float(objective_min_dist_after),
                "objective_min_dist_before": float(objective_min_dist_before),
                "objective_min_dist_after": float(objective_min_dist_after),
                "objective_progress_delta": objective_progress_delta,
                "vp_progress_observed": (
                    float(objective_progress_delta)
                    if objective_progress_delta is not None
                    else None
                ),
                "vp_progress_estimated_selected": (
                    float(selected_tie_break_term)
                    if selected_tie_break_term is not None
                    else None
                ),
                "vp_progress": (
                    float(objective_progress_delta)
                    if objective_progress_delta is not None
                    else None
                ),
                "vp_progress_source": (
                    "objective_progress_delta"
                    if objective_progress_delta is not None
                    else "missing"
                ),
                "vp_progress_available": bool(objective_progress_delta is not None),
                "objective_converted": int(objective_converted),
                "objective_best_vp_id": str(objective_best_vp_id),
                "strategy_label": str(strategy_label),
                "tie_break_term": (
                    float(selected_tie_break_term)
                    if selected_tie_break_term is not None
                    else None
                ),
                "vp_distance_vector": dict(vp_distance_vector),
                "vp_distance_vector_size": int(len(vp_distance_vector)),
                "unit_prefilter_enabled": (
                    bool(unit_prefilter_enabled)
                    if unit_prefilter_enabled is not None
                    else False
                ),
                "unit_prefilter_selected_unit_id": str(unit_prefilter_selected_unit_id),
                "unit_prefilter_constrained_count": (
                    int(unit_prefilter_constrained_count)
                    if unit_prefilter_constrained_count is not None
                    else None
                ),
                "unit_prefilter_global_count": (
                    int(unit_prefilter_global_count)
                    if unit_prefilter_global_count is not None
                    else None
                ),
                "unit_positions": list(unit_positions_snapshot),
                "unit_hp_map": dict(unit_hp_snapshot),
                "unit_alive_map": dict(unit_alive_snapshot),
                "unit_suppressed_map": dict(unit_suppressed_snapshot),
                "vp_map": dict(before_vp_owner),
                "obs_enemy_vp_threat_map": (
                    dict(_field(transition_info, "obs_enemy_vp_threat_map", {}) or {})
                    if _field(transition_info, "obs_enemy_vp_threat_map", None) is not None
                    else {}
                ),
                "obs_terrain_type_map": (
                    dict(getattr(obs, "terrain_type_by_hex", {}) or {})
                    if getattr(obs, "terrain_type_by_hex", None) is not None
                    else {}
                ),
                "obs_terrain_cover_map": dict(getattr(obs, "terrain_cover_by_hex", {}) or {}),
                "obs_terrain_los_block_map": dict(
                    getattr(obs, "terrain_los_block_by_hex", {}) or {}
                ),
                "obs_terrain_move_cost_map": dict(
                    getattr(obs, "terrain_move_cost_by_hex", {}) or {}
                ),
                "obs_fortification_type_map": (
                    dict(getattr(obs, "fortification_type_by_hex", {}) or {})
                    if getattr(obs, "fortification_type_by_hex", None) is not None
                    else {}
                ),
                "obs_fortification_edge_map": (
                    dict(getattr(obs, "fortification_edge_by_hex", {}) or {})
                    if getattr(obs, "fortification_edge_by_hex", None) is not None
                    else {}
                ),
                "obs_reachable_hex_mask_by_unit": (
                    dict(_field(transition_info, "obs_reachable_hex_mask_by_unit", {}) or {})
                    if _field(transition_info, "obs_reachable_hex_mask_by_unit", None) is not None
                    else {}
                ),
                "obs_attackable_hex_mask_by_unit": (
                    dict(_field(transition_info, "obs_attackable_hex_mask_by_unit", {}) or {})
                    if _field(transition_info, "obs_attackable_hex_mask_by_unit", None) is not None
                    else {}
                ),
                "obs_enemy_reaction_fire_risk": (
                    float(_field(transition_info, "obs_enemy_reaction_fire_risk", 0.0))
                    if _field(transition_info, "obs_enemy_reaction_fire_risk", None) is not None
                    else 0.0
                ),
                "obs_vp_ownership_ttl": (
                    dict(_field(transition_info, "obs_vp_ownership_ttl", {}) or {})
                    if _field(transition_info, "obs_vp_ownership_ttl", None) is not None
                    else {}
                ),
                "objective_signal_definition_version": "vp_objective_v2",
                "telemetry_schema_version": "head_telemetry_v1",
                "telemetry_heads": dict(head_states),
                "telemetry_coverage_status": str(telemetry_coverage_status),
                "telemetry_coverage_reason": str(telemetry_coverage_reason),
                "dice_rolls": [*list(attack_dice_rolls), *list(defense_dice_rolls)],
                "attack_dice_rolls": list(attack_dice_rolls),
                "defense_dice_rolls": list(defense_dice_rolls),
                "attack_components_by_die": dict(attack_components_by_die),
                "defense_components_by_die": dict(defense_components_by_die),
                "runtime_events": list(runtime_events),
                "action_mismatch": False,
                "units": _units_snapshot(post_units),
            }
        )
        steps += 1
        obs = post_obs
        if transition.done:
            terminal = True
            break
    if not terminal:
        timeout_transition = adapter.sim.resolve_timeout(
            action_id="TIMEOUT",
            end_reason=timeout_reason,
        )
        winner = timeout_transition.state.winner
        winner_side = str(winner) if winner is not None else ""
        if winner is None:
            total_reward += 0.0
            win = False
        else:
            won = str(winner) == eval_side
            total_reward += 1.0 if won else -1.0
            win = won
        terminal = True
        timeout = True
        terminal_reason = str(timeout_transition.state.end_reason or timeout_reason)
    final_vp_by_side = _vp_control_counts()
    scenario_outcome = _scenario_outcome_from_final_vp(final_vp_by_side)
    phase29_summary = _finalize_phase29(phase29)
    phase29_summary.update(_compute_decision_diagnostics_kpis(trace_rows))
    phase29_summary["by_side"] = {
        str(side): {
            **_finalize_phase29(bucket),
            **_compute_decision_diagnostics_kpis(
                [
                    dict(r or {})
                    for r in trace_rows
                    if _normalize_side_key((r or {}).get("unit_side", ""))
                    == _normalize_side_key(side)
                ]
            ),
        }
        for side, bucket in phase29_by_side.items()
    }
    return (
        int(seed),
        total_reward,
        steps,
        terminal,
        timeout,
        win,
        terminal_reason,
        initial_vp_by_side,
        final_vp_by_side,
        winner_side,
        scenario_outcome,
        phase29_summary,
        trace_rows,
    )


def _load_train_phase29_from_checkpoint(checkpoint_path: str) -> Dict[str, float]:
    summary = _load_train_summary_from_checkpoint(checkpoint_path=checkpoint_path)
    section = summary.get("phase_2_9_train_kpis", {}) or {}
    return dict(section)


def _load_train_summary_from_checkpoint(checkpoint_path: str) -> Dict[str, object]:
    if not checkpoint_path:
        return {}
    ckpt = Path(checkpoint_path)
    if not ckpt.is_absolute():
        ckpt = (Path.cwd() / ckpt).resolve()
    run_dir = ckpt.parent.parent
    summary_path = run_dir / "metrics" / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload or {})


def _phase29_value(payload: Dict[str, object], key: str) -> float:
    if key in payload:
        return float(payload.get(key, 0.0) or 0.0)
    assault_quality = dict(payload.get("assault_quality", {}) or {})
    if key in assault_quality:
        return float(assault_quality.get(key, 0.0) or 0.0)
    return 0.0


def _build_phase29_train_eval(train_kpis: Dict[str, float], eval_kpis: Dict[str, float]) -> Dict[str, Dict]:
    keys = [
        "reaction_window_count",
        "reaction_fire_count",
        "reaction_fire_skipped_count",
        "reaction_fire_kill_conversions",
        "reaction_fire_damage_sum",
        "reaction_fire_activation_rate",
        "reaction_fire_kill_conversion_rate",
        "reaction_fire_damage_induced_proxy",
        "reaction_fire_damage_prevented_proxy",
        "assault_melee_action_family_count",
        "melee_attempts",
        "melee_success_count",
        "melee_kills_sum",
        "melee_damage_sum",
        "melee_success_rate",
        "melee_kills_per_attempt",
        "melee_damage_per_attempt",
        "converted_from_progress_rate",
        "converted_rate_near_vp",
        "conversion_within_2_turns_after_progress",
        "xai_decision_steps",
        "xai_policy_confidence_mean",
        "xai_policy_margin_mean",
        "xai_latent_signal_coverage",
        "xai_vp_capture_opportunity_steps",
        "xai_vp_capture_taken_steps",
        "xai_vp_capture_take_rate",
        "xai_vp_immediate_capture_opportunity_steps",
        "xai_vp_immediate_capture_taken_steps",
        "xai_vp_immediate_capture_take_rate",
        "vp_approach_rate_eligible_steps",
        "vp_approach_rate_positive_steps",
        "vp_approach_rate",
        "vp_regret_delta_count",
        "vp_regret_delta_mean",
        "vp_regret_delta_p95",
        "q_saturation_candidate_rows",
        "q_saturation_hits",
        "q_saturation_rate",
        "decision_spread_step_count",
        "decision_spread_mean",
        "decision_spread_p50",
        "decision_spread_p95",
        "path_to_capture_length_count",
        "path_to_capture_length_mean",
        "path_to_capture_length_p95",
        "opportunity_conversion_early_opportunity_steps",
        "opportunity_conversion_early_converted_steps",
        "opportunity_conversion_early_rate",
        "opportunity_conversion_mid_opportunity_steps",
        "opportunity_conversion_mid_converted_steps",
        "opportunity_conversion_mid_rate",
        "opportunity_conversion_late_opportunity_steps",
        "opportunity_conversion_late_converted_steps",
        "opportunity_conversion_late_rate",
    ]
    return {
        "train": {k: _phase29_value(train_kpis, k) for k in keys},
        "eval": {k: float(eval_kpis.get(k, 0.0)) for k in keys},
        "delta_eval_minus_train": {
            k: float(eval_kpis.get(k, 0.0)) - _phase29_value(train_kpis, k)
            for k in keys
        },
    }


def _aggregate_muzero_eval_kpis(result_rows: List[Dict]) -> Dict[str, float]:
    muzero_rows = [
        dict(r)
        for r in list(result_rows or [])
        if str(r.get("agent_name", "")).startswith("muzero")
    ]
    if not muzero_rows:
        return {}
    total_episodes = int(sum(int(r.get("episodes", 0)) for r in muzero_rows))
    denom = float(max(1, total_episodes))
    count_keys = [
        "reaction_window_count",
        "reaction_fire_count",
        "reaction_fire_skipped_count",
        "reaction_fire_kill_conversions",
        "reaction_fire_damage_sum",
        "assault_melee_action_family_count",
        "melee_attempts",
        "melee_success_count",
        "melee_kills_sum",
        "melee_damage_sum",
        "assault_favorable_count",
        "assault_unfavorable_count",
        "xai_decision_steps",
        "xai_vp_capture_opportunity_steps",
        "xai_vp_capture_taken_steps",
        "xai_vp_immediate_capture_opportunity_steps",
        "xai_vp_immediate_capture_taken_steps",
        "vp_approach_rate_eligible_steps",
        "vp_approach_rate_positive_steps",
        "vp_regret_delta_count",
        "q_saturation_candidate_rows",
        "q_saturation_hits",
        "decision_spread_step_count",
        "path_to_capture_length_count",
        "opportunity_conversion_early_opportunity_steps",
        "opportunity_conversion_early_converted_steps",
        "opportunity_conversion_mid_opportunity_steps",
        "opportunity_conversion_mid_converted_steps",
        "opportunity_conversion_late_opportunity_steps",
        "opportunity_conversion_late_converted_steps",
    ]
    rate_keys = [
        "reaction_fire_activation_rate",
        "reaction_fire_kill_conversion_rate",
        "reaction_fire_damage_induced_proxy",
        "reaction_fire_damage_prevented_proxy",
        "melee_success_rate",
        "melee_kills_per_attempt",
        "melee_damage_per_attempt",
        "converted_from_progress_rate",
        "converted_rate_near_vp",
        "conversion_within_2_turns_after_progress",
        "xai_policy_confidence_mean",
        "xai_policy_margin_mean",
        "xai_latent_signal_coverage",
        "xai_vp_capture_take_rate",
        "xai_vp_immediate_capture_take_rate",
        "vp_approach_rate",
        "vp_regret_delta_mean",
        "vp_regret_delta_p95",
        "q_saturation_rate",
        "decision_spread_mean",
        "decision_spread_p50",
        "decision_spread_p95",
        "path_to_capture_length_mean",
        "path_to_capture_length_p95",
        "opportunity_conversion_early_rate",
        "opportunity_conversion_mid_rate",
        "opportunity_conversion_late_rate",
    ]
    out: Dict[str, float] = {}
    for key in count_keys:
        total = 0.0
        for row in muzero_rows:
            row_kpis = dict(row.get("phase_2_9_eval_kpis", {}) or {})
            total += float(row_kpis.get(key, 0.0))
        out[key] = float(total)
    for key in rate_keys:
        weighted = 0.0
        for row in muzero_rows:
            row_kpis = dict(row.get("phase_2_9_eval_kpis", {}) or {})
            episodes = float(max(1, int(row.get("episodes", 0))))
            weighted += float(row_kpis.get(key, 0.0)) * episodes
        out[key] = float(weighted / denom)
    return out


def _build_eval_diagnostics_summary(eval_kpis: Dict[str, float], tracked_side: str) -> Dict[str, Dict]:
    opportunities = float(max(0.0, float(eval_kpis.get("reaction_window_count", 0.0))))
    progress_actions = float(max(0.0, float(eval_kpis.get("melee_attempts", 0.0))))
    stalls = float(max(0.0, opportunities - progress_actions))
    converted_rate_near_vp = float(eval_kpis.get("converted_rate_near_vp", 0.0))
    conversions = float(max(0.0, min(progress_actions, progress_actions * converted_rate_near_vp)))
    converted_after_progress = float(
        max(
            0.0,
            min(
                conversions,
                conversions * float(eval_kpis.get("converted_from_progress_rate", 0.0)),
            ),
        )
    )
    converted_without_progress = float(max(0.0, conversions - converted_after_progress))
    progressed_but_not_converted = float(max(0.0, progress_actions - conversions))
    stalled_and_not_converted = float(stalls)

    reaction_fire_count = float(max(0.0, float(eval_kpis.get("reaction_fire_count", 0.0))))
    reaction_fire_skipped_count = float(
        max(0.0, float(eval_kpis.get("reaction_fire_skipped_count", 0.0)))
    )
    non_progress_actions = float(max(0.0, stalls - reaction_fire_skipped_count))

    global_funnel = {
        "opportunities": opportunities,
        "progress_actions": progress_actions,
        "conversions": conversions,
        "stalls": stalls,
    }
    global_explain = {
        "conversion_path_counts": {
            "converted_after_progress": converted_after_progress,
            "converted_without_progress": converted_without_progress,
            "progressed_but_not_converted": progressed_but_not_converted,
            "stalled_and_not_converted": stalled_and_not_converted,
        },
        "no_progress_reason_counts": {
            "reaction_fire": reaction_fire_count,
            "reaction_skip": reaction_fire_skipped_count,
            "non_progress_actions": non_progress_actions,
        },
        "no_progress_reason_l2_counts": {},
    }
    tracked_side_s = str(tracked_side or "").strip()
    by_side_funnel = {tracked_side_s: dict(global_funnel)} if tracked_side_s else {}
    by_side_explain = {tracked_side_s: dict(global_explain)} if tracked_side_s else {}
    return {
        "objective_progress_funnel": {
            "global": global_funnel,
            "by_side": by_side_funnel,
        },
        "objective_progress_explain": {
            "global": global_explain,
            "by_side": by_side_explain,
        },
        "source": "eval.phase_2_9_eval_kpis",
    }


def _build_head_diagnostics_eval(
    *,
    train_summary: Dict[str, object],
    eval_kpis: Dict[str, float],
    muzero_row: Dict,
) -> Dict[str, object]:
    decision_steps = float(max(1.0, float(eval_kpis.get("xai_decision_steps", 0.0))))
    cap_taken = float(max(0.0, float(eval_kpis.get("xai_vp_capture_taken_steps", 0.0))))
    cap_opp = float(max(1.0, float(eval_kpis.get("xai_vp_capture_opportunity_steps", 0.0))))
    immediate_cap_taken = float(
        max(0.0, float(eval_kpis.get("xai_vp_immediate_capture_taken_steps", 0.0)))
    )
    immediate_cap_opp = float(
        max(1.0, float(eval_kpis.get("xai_vp_immediate_capture_opportunity_steps", 0.0)))
    )
    return {
        "policy": {
            "eval_decision_steps": float(eval_kpis.get("xai_decision_steps", 0.0)),
            "eval_confidence_mean": float(eval_kpis.get("xai_policy_confidence_mean", 0.0)),
            "eval_margin_mean": float(eval_kpis.get("xai_policy_margin_mean", 0.0)),
            "eval_latent_signal_coverage": float(eval_kpis.get("xai_latent_signal_coverage", 0.0)),
            "train_policy_loss": float(train_summary.get("policy_loss", 0.0) or 0.0),
        },
        "value": {
            "train_value_loss": float(train_summary.get("value_loss", 0.0) or 0.0),
            "eval_win_rate_proxy": float(muzero_row.get("win_rate", 0.0) or 0.0),
            "eval_avg_return_proxy": float(muzero_row.get("avg_return", 0.0) or 0.0),
        },
        "reward": {
            "train_reward_loss": float(train_summary.get("reward_loss", 0.0) or 0.0),
            "eval_avg_return_proxy": float(muzero_row.get("avg_return", 0.0) or 0.0),
            "eval_avg_steps_proxy": float(muzero_row.get("avg_steps", 0.0) or 0.0),
        },
        "objective": {
            "train_objective_loss": float(train_summary.get("objective_loss", 0.0) or 0.0),
            "eval_vp_capture_opportunity_steps": float(eval_kpis.get("xai_vp_capture_opportunity_steps", 0.0)),
            "eval_vp_immediate_capture_opportunity_steps": float(
                eval_kpis.get("xai_vp_immediate_capture_opportunity_steps", 0.0)
            ),
            "eval_vp_capture_taken_steps": float(eval_kpis.get("xai_vp_capture_taken_steps", 0.0)),
            "eval_vp_immediate_capture_taken_steps": float(
                eval_kpis.get("xai_vp_immediate_capture_taken_steps", 0.0)
            ),
            "eval_vp_capture_take_rate": float(cap_taken / cap_opp),
            "eval_vp_immediate_capture_take_rate": float(immediate_cap_taken / immediate_cap_opp),
            "eval_vp_conversion_efficiency": float(cap_taken / decision_steps),
            "eval_vp_immediate_conversion_efficiency": float(
                immediate_cap_taken / decision_steps
            ),
            "eval_vp_capture_take_rate_denominator_steps": float(cap_opp),
            "eval_vp_conversion_efficiency_denominator_steps": float(decision_steps),
            "eval_tracked_captured_avg": float(muzero_row.get("tracked_captured_avg", 0.0) or 0.0),
        },
        "consistency": {
            "train_consistency_loss": float(train_summary.get("consistency_loss", 0.0) or 0.0),
            "train_consistency_pairs": float(train_summary.get("consistency_pairs", 0.0) or 0.0),
            "train_reanalysis_coverage": float(train_summary.get("reanalysis_coverage", 0.0) or 0.0),
            "train_reanalysis_target_drift": float(
                train_summary.get("reanalysis_target_drift", 0.0) or 0.0
            ),
            "train_reanalysis_policy_drift": float(
                train_summary.get("reanalysis_policy_drift", 0.0) or 0.0
            ),
        },
        "mcts": {
            "eval_decision_steps": float(eval_kpis.get("xai_decision_steps", 0.0)),
            "eval_policy_confidence_mean": float(eval_kpis.get("xai_policy_confidence_mean", 0.0)),
            "eval_policy_margin_mean": float(eval_kpis.get("xai_policy_margin_mean", 0.0)),
            "eval_latent_signal_coverage": float(eval_kpis.get("xai_latent_signal_coverage", 0.0)),
            "eval_reaction_window_count": float(eval_kpis.get("reaction_window_count", 0.0)),
            "eval_melee_attempts": float(eval_kpis.get("melee_attempts", 0.0)),
        },
        "source": {
            "train": "metrics/summary.json",
            "eval": "bench.phase_2_9_eval_kpis + benchmark results",
        },
    }


def _build_phase29_promotion_gate(
    *,
    train_kpis: Dict[str, float],
    eval_kpis: Dict[str, float],
    muzero_row: Dict,
    baseline_row: Dict,
) -> Dict[str, object]:
    def _tracked_capture_direction(metric_name: str) -> str:
        # Objective captures are defined from tracked-side perspective:
        # more captured objectives is always better for that side.
        metric = str(metric_name or "").strip().lower()
        if metric in {"objectives_captured", "vp_captured", "captured"}:
            return "higher_is_better"
        return "higher_is_better"

    eval_reaction_windows = float(eval_kpis.get("reaction_window_count", 0.0))
    eval_reaction_events = float(eval_kpis.get("reaction_fire_count", 0.0)) + float(
        eval_kpis.get("reaction_fire_skipped_count", 0.0)
    )
    reaction_contract_pass = (
        (eval_reaction_events <= eval_reaction_windows)
        if eval_reaction_windows > 0.0
        else (eval_reaction_events == 0.0)
    )
    assault_usage_non_zero = float(eval_kpis.get("melee_attempts", 0.0)) > 0.0
    tracked_side = str(muzero_row.get("tracked_side", "") or "").strip()
    tracked_metric = str(muzero_row.get("tracked_metric", "") or "").strip()
    winner_counts = dict(muzero_row.get("winner_side_counts", {}) or {})
    dominant_winner_side = ""
    if winner_counts:
        dominant_winner_side = str(max(winner_counts.items(), key=lambda kv: int(kv[1]))[0])
    muzero_captured = float(muzero_row.get("tracked_captured_avg", 0.0))
    baseline_captured = float(baseline_row.get("tracked_captured_avg", 0.0))
    tracked_capture_direction = _tracked_capture_direction(tracked_metric)
    # Compare tracked objective capture with a stable direction from scenario metric.
    if tracked_capture_direction == "higher_is_better":
        capture_conversion_no_regression = muzero_captured >= baseline_captured
    else:
        capture_conversion_no_regression = muzero_captured <= baseline_captured
    eval_loss_rate = 1.0 - float(muzero_row.get("win_rate", 0.0))
    baseline_loss_rate = 1.0 - float(baseline_row.get("win_rate", 0.0))
    loss_rate_no_regression = eval_loss_rate <= baseline_loss_rate + 1e-9
    melee_attempt_rate = float(eval_kpis.get("melee_attempts", 0.0)) / float(
        max(1.0, float(eval_reaction_windows) + float(eval_kpis.get("melee_attempts", 0.0)))
    )
    melee_success_rate = float(eval_kpis.get("melee_success_rate", 0.0))
    assault_misuse_block = bool(melee_attempt_rate > 0.15 and melee_success_rate < 0.20)
    reaction_failfast_block = bool(
        float(eval_kpis.get("reaction_fire_activation_rate", 0.0))
        > _phase29_value(train_kpis, "reaction_fire_activation_rate")
        and float(muzero_row.get("win_rate", 0.0)) < float(baseline_row.get("win_rate", 0.0))
    )
    checks = {
        "reaction_contract_pass": bool(reaction_contract_pass),
        "capture_conversion_after_contact_no_regression": bool(capture_conversion_no_regression),
        "loss_rate_no_regression": bool(loss_rate_no_regression),
        "reaction_failfast_block": bool(not reaction_failfast_block),
    }
    return {
        "status": "PASS" if all(bool(v) for v in checks.values()) else "FAIL",
        "checks": checks,
        "advisory": {
            "assault_usage_non_zero": bool(assault_usage_non_zero),
            "assault_misuse_block": bool(not assault_misuse_block),
        },
        "promotion_mode": "vp_first",
        "tracked_capture_direction": tracked_capture_direction,
        "tracked_side": tracked_side,
        "tracked_metric": tracked_metric,
        "dominant_winner_side": dominant_winner_side,
        "muzero_tracked_captured_avg": float(muzero_captured),
        "baseline_tracked_captured_avg": float(baseline_captured),
        "eval_loss_rate": float(eval_loss_rate),
        "baseline_loss_rate": float(baseline_loss_rate),
        "melee_attempt_rate_proxy": float(melee_attempt_rate),
    }


def _iter_index_from_checkpoint_name(name: str) -> int:
    m = re.search(r"iter_(\d+)\.pt$", str(name))
    return int(m.group(1)) if m else -1


def _resolve_checkpoint_path(checkpoint_path: str, run_root: Path) -> str:
    raw = str(checkpoint_path or "").strip()
    if raw and raw.lower() != "latest":
        return raw
    ckpts = list(run_root.glob("muzero_*/checkpoints/iter_*.pt"))
    ckpts.extend(list(run_root.glob("efficientzero_v2_*/checkpoints/iter_*.pt")))
    ckpts.extend(list(run_root.glob("efficientzero_v2_*/checkpoints/final.pt")))
    if not ckpts:
        return ""
    best = sorted(
        ckpts,
        key=lambda p: (p.stat().st_mtime, _iter_index_from_checkpoint_name(p.name)),
        reverse=True,
    )[0]
    return str(best)


def _engine_kind_from_checkpoint_path(checkpoint_path: str) -> str:
    raw = str(checkpoint_path or "").strip().replace("\\", "/")
    if not raw:
        return "muzero"
    parts = [p for p in raw.split("/") if p]
    for part in parts:
        if str(part).startswith("efficientzero_v2_"):
            return "efficientzero_v2"
        if str(part).startswith("muzero_"):
            return "muzero"
    return "muzero"


def run_benchmark(
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    checkpoint_path: str = "",
    muzero_config_path: str = "",
    mlflow_experiment: str = "assault_bench",
    mlflow_run_name: str = "",
    device: str = "",
) -> Dict:
    cfg = load_benchmark_config(Path(config_path))
    voec_cfg = load_voec_config(Path(cfg.paths["voec_config"]))
    scenario_id = str(cfg.benchmark["scenario_id"])
    seeds = list(cfg.benchmark["seeds"])
    max_steps = int(cfg.benchmark["max_steps"])
    max_steps_override = int(cfg.benchmark.get("max_steps_override", 0))
    mcts_simulations = int(cfg.benchmark["mcts_simulations"])
    mcts_c_puct = float(cfg.benchmark["mcts_c_puct"])
    mcts_temperature = float(cfg.benchmark.get("mcts_temperature", 1.0))
    mcts_dirichlet_alpha = float(cfg.benchmark.get("mcts_dirichlet_alpha", 0.3))
    mcts_dirichlet_epsilon = float(cfg.benchmark.get("mcts_dirichlet_epsilon", 0.0))
    mcts_q_clip_abs = float(cfg.benchmark.get("mcts_q_clip_abs", 10.0))
    mcts_min_root_visits_per_action = int(
        cfg.benchmark.get("mcts_min_root_visits_per_action", 0) or 0
    )
    mcts_min_root_visits_top_n = int(
        cfg.benchmark.get("mcts_min_root_visits_top_n", 0) or 0
    )
    unit_prefilter_enabled = bool(cfg.benchmark.get("unit_prefilter_enabled", False))
    unit_prefilter_replan_enabled = bool(cfg.benchmark.get("unit_prefilter_replan_enabled", False))
    unit_prefilter_top_k = int(cfg.benchmark.get("unit_prefilter_top_k", 1) or 1)
    unit_prefilter_vp_progress_weight = float(
        cfg.benchmark.get("unit_prefilter_vp_progress_weight", 1.0)
    )
    unit_prefilter_capture_opportunity_weight = float(
        cfg.benchmark.get("unit_prefilter_capture_opportunity_weight", 2.0)
    )
    unit_prefilter_threat_weight = float(
        cfg.benchmark.get("unit_prefilter_threat_weight", 0.25)
    )
    num_workers = int(cfg.benchmark.get("num_workers", 1))
    bench_device_cfg = str(cfg.benchmark.get("device", "cuda"))
    bench_device = _resolve_bench_device_choice(bench_device_cfg, device)
    if bench_device == "cuda" and num_workers > 1:
        print(
            f"[Bench] CUDA eval with num_workers={num_workers} can oversubscribe GPU. "
            "Forcing workers=1.",
            flush=True,
        )
        num_workers = 1
    run_root = Path(str(cfg.paths["run_root"]))
    checkpoint_path = _resolve_checkpoint_path(checkpoint_path=checkpoint_path, run_root=run_root)
    model_kind_hint = _engine_kind_from_checkpoint_path(checkpoint_path=checkpoint_path)
    if muzero_config_path:
        cfg_muzero_path = str(muzero_config_path)
    else:
        if model_kind_hint == "efficientzero_v2":
            cfg_muzero_path = "agents/efficientzero_v2/configs/efficientzero_v2_config.yaml"
        else:
            cfg_muzero_path = str(
                cfg.paths.get("muzero_config", "agents/muzero/configs/muzero_config.yaml")
            )
    mlflow_mod, _mlflow_ctx = _start_mlflow_run(
        experiment_name=str(mlflow_experiment),
        run_name=(str(mlflow_run_name).strip() or f"bench_{scenario_id}"),
    )

    model = None
    action_dim = 32
    mcts_unroll_steps = 1
    mcts_discount = 0.997
    if checkpoint_path:
        ckpt_run_id = ""
        try:
            ckpt_tmp = Path(checkpoint_path)
            if not ckpt_tmp.is_absolute():
                ckpt_tmp = (Path.cwd() / ckpt_tmp).resolve()
            ckpt_run_id = str(ckpt_tmp.parent.parent.name)
        except Exception:
            ckpt_run_id = ""
        model_kind = (
            "efficientzero_v2" if ckpt_run_id.startswith("efficientzero_v2_") else model_kind_hint
        )
        muz_cfg = load_muzero_config(Path(cfg_muzero_path))
        action_dim = int(muz_cfg.model["action_dim"])
        mcts_unroll_steps = int(muz_cfg.selfplay.get("mcts_unroll_steps", 1))
        mcts_discount = float(muz_cfg.selfplay.get("mcts_discount", 0.997))
        if "mcts_q_clip_abs" not in dict(cfg.benchmark):
            mcts_q_clip_abs = float(muz_cfg.selfplay.get("mcts_q_clip_abs", mcts_q_clip_abs))
        if "mcts_dirichlet_alpha" not in dict(cfg.benchmark):
            mcts_dirichlet_alpha = float(
                muz_cfg.selfplay.get("mcts_dirichlet_alpha", mcts_dirichlet_alpha)
            )
        if "mcts_dirichlet_epsilon" not in dict(cfg.benchmark):
            mcts_dirichlet_epsilon = float(
                muz_cfg.selfplay.get("mcts_dirichlet_epsilon", mcts_dirichlet_epsilon)
            )
        if "mcts_min_root_visits_per_action" not in dict(cfg.benchmark):
            mcts_min_root_visits_per_action = int(
                muz_cfg.selfplay.get(
                    "mcts_min_root_visits_per_action",
                    mcts_min_root_visits_per_action,
                )
                or mcts_min_root_visits_per_action
            )
        if "mcts_min_root_visits_top_n" not in dict(cfg.benchmark):
            mcts_min_root_visits_top_n = int(
                muz_cfg.selfplay.get(
                    "mcts_min_root_visits_top_n",
                    mcts_min_root_visits_top_n,
                )
                or mcts_min_root_visits_top_n
            )
        if "unit_prefilter_enabled" not in dict(cfg.benchmark):
            unit_prefilter_enabled = bool(muz_cfg.selfplay.get("unit_prefilter_enabled", unit_prefilter_enabled))
        if "unit_prefilter_replan_enabled" not in dict(cfg.benchmark):
            unit_prefilter_replan_enabled = bool(
                muz_cfg.selfplay.get("unit_prefilter_replan_enabled", unit_prefilter_replan_enabled)
            )
        if "unit_prefilter_top_k" not in dict(cfg.benchmark):
            unit_prefilter_top_k = int(
                muz_cfg.selfplay.get("unit_prefilter_top_k", unit_prefilter_top_k) or unit_prefilter_top_k
            )
        if "unit_prefilter_vp_progress_weight" not in dict(cfg.benchmark):
            unit_prefilter_vp_progress_weight = float(
                muz_cfg.selfplay.get(
                    "unit_prefilter_vp_progress_weight",
                    unit_prefilter_vp_progress_weight,
                )
            )
        if "unit_prefilter_capture_opportunity_weight" not in dict(cfg.benchmark):
            unit_prefilter_capture_opportunity_weight = float(
                muz_cfg.selfplay.get(
                    "unit_prefilter_capture_opportunity_weight",
                    unit_prefilter_capture_opportunity_weight,
                )
            )
        if "unit_prefilter_threat_weight" not in dict(cfg.benchmark):
            unit_prefilter_threat_weight = float(
                muz_cfg.selfplay.get("unit_prefilter_threat_weight", unit_prefilter_threat_weight)
            )
        model_cls = EfficientZeroV2Network if model_kind == "efficientzero_v2" else MuZeroNetwork
        model = model_cls(
            observation_dim=int(muz_cfg.model["observation_dim"]),
            hidden_dim=int(muz_cfg.model["hidden_dim"]),
            action_dim=action_dim,
            encoder_type=str(muz_cfg.model.get("encoder_type", "mlp")),
            observation_channels=int(muz_cfg.model.get("observation_channels", 8)),
            observation_height=int(muz_cfg.model.get("observation_height", 16)),
            observation_width=int(muz_cfg.model.get("observation_width", 16)),
            dynamics_blocks=int(muz_cfg.model.get("dynamics_blocks", 1)),
            prediction_blocks=int(muz_cfg.model.get("prediction_blocks", 1)),
        )
        ckpt = Path(checkpoint_path)
        if not ckpt.is_absolute():
            ckpt = (Path.cwd() / ckpt).resolve()
        state_dict = _load_state_dict(ckpt, bench_device)
        model.load_state_dict(state_dict)
        if bench_device == "cuda":
            model = model.to("cuda")
        model.eval()
        print(f"[Bench] loaded_checkpoint={ckpt}")
    else:
        print("[Bench] running without checkpoint (stub mode)")

    sim = VOECSimulator(assets=voec_cfg.assets)
    adapter = MuZeroVOECAdapter(sim)
    print(
        "[Bench] "
        f"scenario={scenario_id} seeds={len(seeds)} "
        f"workers={num_workers} max_steps={max_steps} device={bench_device}"
    )

    results: List[BenchmarkResult] = []
    bench_replay_episodes: List[Dict[str, object]] = []
    base_obs = adapter.initial_state(scenario_id=scenario_id, seed=int(seeds[0] if seeds else 0))
    sides = sorted(
        {
            str(u.get("side", "")).strip()
            for u in (getattr(base_obs, "units", []) or [])
            if str(u.get("side", "")).strip()
        }
    )
    if len(sides) < 2:
        active_side = str(getattr(base_obs, "to_play", "") or "").strip()
        if active_side:
            sides = [active_side]
    profile_defs: list[dict] = [
        {
            "profile": "muzero_selfplay",
            "agent_name": "muzero_stub",
            "policy": "mcts",
            "policy_by_side": {},
            "group": "selfplay",
            "goal": "MuZero mirror baseline",
        },
        {
            "profile": "random_selfplay",
            "agent_name": "baseline_random",
            "policy": "random",
            "policy_by_side": {},
            "group": "selfplay",
            "goal": "Random mirror sanity baseline",
        },
    ]
    if len(sides) >= 2:
        side_a, side_b = sides[0], sides[1]
        profile_defs.extend(
            [
                {
                    "profile": "muzero_vs_random_side_a",
                    "agent_name": f"muzero_vs_random_{side_a}",
                    "policy": "mcts",
                    "policy_by_side": {side_a: "mcts", side_b: "random"},
                    "group": "head_to_head_role",
                    "goal": f"MuZero as {side_a}, random as {side_b}",
                },
                {
                    "profile": "muzero_vs_random_side_b",
                    "agent_name": f"muzero_vs_random_{side_b}",
                    "policy": "mcts",
                    "policy_by_side": {side_a: "random", side_b: "mcts"},
                    "group": "head_to_head_role",
                    "goal": f"MuZero as {side_b}, random as {side_a}",
                },
            ]
        )
    enabled_profiles = _resolve_enabled_profiles(cfg.benchmark)
    matchup_specs = [p for p in profile_defs if str(p.get("profile", "")) in enabled_profiles]
    for spec in matchup_specs:
        profile = str(spec["profile"])
        agent_name = str(spec["agent_name"])
        policy = str(spec["policy"])
        policy_by_side = dict(spec.get("policy_by_side", {}) or {})
        if not policy_by_side and sides:
            # Reporting/controller filters must come from produced data, not UI inference.
            policy_by_side = {str(side): str(policy) for side in sides}
        group = str(spec.get("group", ""))
        goal = str(spec.get("goal", ""))
        collect_flow_metrics = bool("muzero" in agent_name.lower())
        print(
            f"[Bench] profile={profile} agent={agent_name} policy={policy} "
            f"policy_by_side={policy_by_side if policy_by_side else '{}'} start"
        , flush=True)
        returns = []
        steps = []
        terminals = []
        timeouts = []
        wins = []
        terminal_reason_counts: Dict[str, int] = {}
        vp_initial_counts_by_side: Dict[str, Dict[int, int]] = {}
        vp_final_counts_by_side: Dict[str, Dict[int, int]] = {}
        vp_initial_sum_by_side: Dict[str, float] = {}
        vp_final_sum_by_side: Dict[str, float] = {}
        vp_gained_sum_by_side: Dict[str, float] = {}
        vp_lost_sum_by_side: Dict[str, float] = {}
        winner_side_counts: Dict[str, int] = {}
        tracked_side = ""
        tracked_metric = ""
        tracked_captured_values: List[int] = []
        scenario_outcome_counts: Dict[str, int] = {}
        scenario_outcome_class_counts: Dict[str, int] = {}
        tracked_outcome_bucket_counts: Dict[str, int] = {}
        opponent_outcome_bucket_counts: Dict[str, int] = {}
        phase29_seed_rows: List[Dict[str, float]] = []
        phase29_seed_rows_by_side: List[Dict[str, Dict[str, float]]] = []
        decision_trace_rows_all: List[Dict[str, object]] = []
        if num_workers > 1:
            payloads = [
                {
                    "assets": {
                        "root": str(voec_cfg.assets.root),
                        "unit_catalog": str(voec_cfg.assets.unit_catalog),
                        "map_piece_catalog": str(voec_cfg.assets.map_piece_catalog),
                        "scenarios_dir": str(voec_cfg.assets.scenarios_dir),
                    },
                    "scenario_id": scenario_id,
                    "seed": s,
                    "policy_name": policy,
                    "policy_by_side": dict(policy_by_side),
                    "max_steps": max_steps,
                    "max_steps_override": max_steps_override,
                    "mcts_simulations": mcts_simulations,
                    "mcts_c_puct": mcts_c_puct,
                    "mcts_temperature": mcts_temperature,
                    "mcts_dirichlet_alpha": mcts_dirichlet_alpha,
                    "mcts_dirichlet_epsilon": mcts_dirichlet_epsilon,
                    "mcts_q_clip_abs": mcts_q_clip_abs,
                    "mcts_min_root_visits_per_action": mcts_min_root_visits_per_action,
                    "mcts_min_root_visits_top_n": mcts_min_root_visits_top_n,
                    "checkpoint_path": str(ckpt) if checkpoint_path else "",
                    "action_dim": action_dim,
                    "mcts_unroll_steps": mcts_unroll_steps,
                    "mcts_discount": mcts_discount,
                    "decision_top_k": None,
                    "collect_flow_metrics": collect_flow_metrics,
                    "bench_device": bench_device,
                    "model_kind": model_kind,
                    "model": {
                        "observation_dim": int(muz_cfg.model["observation_dim"])
                        if checkpoint_path
                        else 4,
                        "hidden_dim": int(muz_cfg.model["hidden_dim"])
                        if checkpoint_path
                        else 64,
                        "action_dim": action_dim,
                        "encoder_type": str(muz_cfg.model.get("encoder_type", "mlp"))
                        if checkpoint_path
                        else "mlp",
                        "observation_channels": int(muz_cfg.model.get("observation_channels", 8))
                        if checkpoint_path
                        else 8,
                        "observation_height": int(muz_cfg.model.get("observation_height", 16))
                        if checkpoint_path
                        else 16,
                        "observation_width": int(muz_cfg.model.get("observation_width", 16))
                        if checkpoint_path
                        else 16,
                        "dynamics_blocks": int(muz_cfg.model.get("dynamics_blocks", 1))
                        if checkpoint_path
                        else 1,
                        "prediction_blocks": int(muz_cfg.model.get("prediction_blocks", 1))
                        if checkpoint_path
                        else 1,
                    },
                }
                for s in seeds
            ]
            with ProcessPoolExecutor(max_workers=num_workers) as ex:
                futures = [ex.submit(_benchmark_seed_task, p) for p in payloads]
                for fut in as_completed(futures):
                    (
                        seed_used,
                        ret,
                        step_count,
                        terminal,
                        timeout,
                        win,
                        terminal_reason,
                        initial_vp_by_side,
                        final_vp_by_side,
                        winner_side,
                        scenario_outcome,
                        phase29_summary,
                        trace_rows,
                    ) = fut.result()
                    returns.append(ret)
                    steps.append(step_count)
                    terminals.append(terminal)
                    timeouts.append(timeout)
                    wins.append(win)
                    for side, vp_count in (initial_vp_by_side or {}).items():
                        side_s = str(side)
                        vp_i = int(vp_count or 0)
                        if side_s not in vp_initial_counts_by_side:
                            vp_initial_counts_by_side[side_s] = {}
                        vp_initial_counts_by_side[side_s][vp_i] = (
                            vp_initial_counts_by_side[side_s].get(vp_i, 0) + 1
                        )
                        vp_initial_sum_by_side[side_s] = vp_initial_sum_by_side.get(side_s, 0.0) + float(vp_i)
                    for side, vp_count in (final_vp_by_side or {}).items():
                        side_s = str(side)
                        vp_i = int(vp_count or 0)
                        if side_s not in vp_final_counts_by_side:
                            vp_final_counts_by_side[side_s] = {}
                        vp_final_counts_by_side[side_s][vp_i] = (
                            vp_final_counts_by_side[side_s].get(vp_i, 0) + 1
                        )
                        vp_final_sum_by_side[side_s] = vp_final_sum_by_side.get(side_s, 0.0) + float(vp_i)
                    all_sides = set((initial_vp_by_side or {}).keys()) | set((final_vp_by_side or {}).keys())
                    for side in all_sides:
                        s = str(side)
                        vi = float((initial_vp_by_side or {}).get(side, 0) or 0)
                        vf = float((final_vp_by_side or {}).get(side, 0) or 0)
                        vp_gained_sum_by_side[s] = vp_gained_sum_by_side.get(s, 0.0) + max(0.0, vf - vi)
                        vp_lost_sum_by_side[s] = vp_lost_sum_by_side.get(s, 0.0) + max(0.0, vi - vf)
                    winner_key = str(winner_side or "").strip()
                    if winner_key:
                        winner_side_counts[winner_key] = winner_side_counts.get(winner_key, 0) + 1
                    tracked_side = tracked_side or str(scenario_outcome.get("tracked_side", "")).strip()
                    tracked_metric = tracked_metric or str(scenario_outcome.get("metric", "")).strip()
                    tracked_captured_values.append(int(scenario_outcome.get("captured", 0) or 0))
                    outcome_label = str(scenario_outcome.get("result", "")).strip() or "unknown"
                    scenario_outcome_counts[outcome_label] = scenario_outcome_counts.get(outcome_label, 0) + 1
                    outcome_class = str(scenario_outcome.get("outcome_class", "")).strip() or "unknown"
                    scenario_outcome_class_counts[outcome_class] = (
                        scenario_outcome_class_counts.get(outcome_class, 0) + 1
                    )
                    tracked_bucket = _outcome_bucket_from_class(outcome_class)
                    tracked_outcome_bucket_counts[tracked_bucket] = (
                        tracked_outcome_bucket_counts.get(tracked_bucket, 0) + 1
                    )
                    if tracked_bucket == "win":
                        opponent_bucket = "loss"
                    elif tracked_bucket == "loss":
                        opponent_bucket = "win"
                    else:
                        opponent_bucket = tracked_bucket
                    opponent_outcome_bucket_counts[opponent_bucket] = (
                        opponent_outcome_bucket_counts.get(opponent_bucket, 0) + 1
                    )
                    if collect_flow_metrics:
                        phase29_seed_rows.append(dict(phase29_summary or {}))
                        phase29_seed_rows_by_side.append(
                            dict((phase29_summary or {}).get("by_side", {}) or {})
                        )
                    # Bench replay trace from this evaluated episode.
                    decision_trace_rows_all.extend(list(trace_rows or []))
                    bench_replay_episodes.append(
                        {
                            "agent_name": str(agent_name),
                            "seed": int(seed_used),
                            "episode_index": int(len(phase29_seed_rows) - 1),
                            "transitions": list(trace_rows or []),
                        }
                    )
                    key = terminal_reason or "unknown"
                    terminal_reason_counts[key] = terminal_reason_counts.get(key, 0) + 1
                    print(
                        f"[Bench]   seed_done return={ret:.3f} "
                        f"steps={step_count} terminal={terminal} timeout={timeout} "
                        f"reason={key}"
                    , flush=True)
        else:
            for idx, s in enumerate(seeds, start=1):
                print(
                    f"[Bench]   seed {idx}/{len(seeds)}={s} start",
                    flush=True,
                )
                (
                    seed_used,
                    ret,
                    step_count,
                    terminal,
                    timeout,
                    win,
                    terminal_reason,
                    initial_vp_by_side,
                    final_vp_by_side,
                    winner_side,
                    scenario_outcome,
                    phase29_summary,
                    trace_rows,
                ) = _run_episode_with_policy(
                    adapter=adapter,
                    scenario_id=scenario_id,
                    seed=s,
                    policy_name=policy,
                    policy_by_side=dict(policy_by_side),
                    max_steps=max_steps,
                    max_steps_override=max_steps_override,
                    mcts_simulations=mcts_simulations,
                    mcts_c_puct=mcts_c_puct,
                    mcts_temperature=mcts_temperature,
                    mcts_dirichlet_alpha=mcts_dirichlet_alpha,
                    mcts_dirichlet_epsilon=mcts_dirichlet_epsilon,
                    mcts_q_clip_abs=mcts_q_clip_abs,
                    mcts_min_root_visits_per_action=mcts_min_root_visits_per_action,
                    mcts_min_root_visits_top_n=mcts_min_root_visits_top_n,
                    model=model if policy != "random" else None,
                    action_dim=action_dim,
                    mcts_unroll_steps=mcts_unroll_steps,
                    mcts_discount=mcts_discount,
                    collect_flow_metrics=collect_flow_metrics,
                    decision_top_k=None,
                )
                returns.append(ret)
                steps.append(step_count)
                terminals.append(terminal)
                timeouts.append(timeout)
                wins.append(win)
                for side, vp_count in (initial_vp_by_side or {}).items():
                    side_s = str(side)
                    vp_i = int(vp_count or 0)
                    if side_s not in vp_initial_counts_by_side:
                        vp_initial_counts_by_side[side_s] = {}
                    vp_initial_counts_by_side[side_s][vp_i] = (
                        vp_initial_counts_by_side[side_s].get(vp_i, 0) + 1
                    )
                    vp_initial_sum_by_side[side_s] = vp_initial_sum_by_side.get(side_s, 0.0) + float(vp_i)
                for side, vp_count in (final_vp_by_side or {}).items():
                    side_s = str(side)
                    vp_i = int(vp_count or 0)
                    if side_s not in vp_final_counts_by_side:
                        vp_final_counts_by_side[side_s] = {}
                    vp_final_counts_by_side[side_s][vp_i] = (
                        vp_final_counts_by_side[side_s].get(vp_i, 0) + 1
                    )
                    vp_final_sum_by_side[side_s] = vp_final_sum_by_side.get(side_s, 0.0) + float(vp_i)
                all_sides = set((initial_vp_by_side or {}).keys()) | set((final_vp_by_side or {}).keys())
                for side in all_sides:
                    s = str(side)
                    vi = float((initial_vp_by_side or {}).get(side, 0) or 0)
                    vf = float((final_vp_by_side or {}).get(side, 0) or 0)
                    vp_gained_sum_by_side[s] = vp_gained_sum_by_side.get(s, 0.0) + max(0.0, vf - vi)
                    vp_lost_sum_by_side[s] = vp_lost_sum_by_side.get(s, 0.0) + max(0.0, vi - vf)
                winner_key = str(winner_side or "").strip()
                if winner_key:
                    winner_side_counts[winner_key] = winner_side_counts.get(winner_key, 0) + 1
                tracked_side = tracked_side or str(scenario_outcome.get("tracked_side", "")).strip()
                tracked_metric = tracked_metric or str(scenario_outcome.get("metric", "")).strip()
                tracked_captured_values.append(int(scenario_outcome.get("captured", 0) or 0))
                outcome_label = str(scenario_outcome.get("result", "")).strip() or "unknown"
                scenario_outcome_counts[outcome_label] = scenario_outcome_counts.get(outcome_label, 0) + 1
                outcome_class = str(scenario_outcome.get("outcome_class", "")).strip() or "unknown"
                scenario_outcome_class_counts[outcome_class] = (
                    scenario_outcome_class_counts.get(outcome_class, 0) + 1
                )
                tracked_bucket = _outcome_bucket_from_class(outcome_class)
                tracked_outcome_bucket_counts[tracked_bucket] = (
                    tracked_outcome_bucket_counts.get(tracked_bucket, 0) + 1
                )
                if tracked_bucket == "win":
                    opponent_bucket = "loss"
                elif tracked_bucket == "loss":
                    opponent_bucket = "win"
                else:
                    opponent_bucket = tracked_bucket
                opponent_outcome_bucket_counts[opponent_bucket] = (
                    opponent_outcome_bucket_counts.get(opponent_bucket, 0) + 1
                )
                if collect_flow_metrics:
                    phase29_seed_rows.append(dict(phase29_summary or {}))
                    phase29_seed_rows_by_side.append(
                        dict((phase29_summary or {}).get("by_side", {}) or {})
                    )
                bench_replay_episodes.append(
                    {
                        "agent_name": str(agent_name),
                        "seed": int(seed_used),
                        "episode_index": int(idx - 1),
                        "transitions": list(trace_rows or []),
                    }
                )
                decision_trace_rows_all.extend(list(trace_rows or []))
                key = terminal_reason or "unknown"
                terminal_reason_counts[key] = terminal_reason_counts.get(key, 0) + 1
                print(
                    f"[Bench]   seed {idx}/{len(seeds)}={s} "
                    f"return={ret:.3f} steps={step_count} "
                    f"terminal={terminal} timeout={timeout} reason={key}"
                , flush=True)
        eval_decision_summary, eval_decisions_top = _build_eval_decision_summary(
            trace_rows=decision_trace_rows_all
        )
        eval_decision_steps_top = _build_eval_decision_steps_top(
            trace_rows=decision_trace_rows_all,
            limit=40,
        )
        results.append(
            # Aggregate phase-2.9 eval KPIs across seeds.
            # Keep key naming aligned with training summary contract.
            BenchmarkResult(
                agent_name=agent_name,
                matchup_profile=profile,
                matchup_group=group,
                measurement_goal=goal,
                policy_name=policy,
                policy_by_side=dict(policy_by_side),
                episodes=len(seeds),
                avg_return=sum(returns) / len(returns),
                avg_steps=sum(steps) / len(steps),
                terminal_rate=sum(1 for x in terminals if x) / len(terminals),
                timeout_rate=sum(1 for x in timeouts if x) / len(timeouts),
                win_rate=sum(1 for x in wins if x) / len(wins),
                terminal_reasons={
                    reason: count / len(seeds) for reason, count in terminal_reason_counts.items()
                },
                vp_initial_avg_by_side={
                    side: (float(v) / float(max(1, len(seeds))))
                    for side, v in vp_initial_sum_by_side.items()
                },
                vp_final_avg_by_side={
                    side: (float(v) / float(max(1, len(seeds))))
                    for side, v in vp_final_sum_by_side.items()
                },
                vp_net_avg_by_side={
                    side: (
                        float(vp_final_sum_by_side.get(side, 0.0) - vp_initial_sum_by_side.get(side, 0.0))
                        / float(max(1, len(seeds)))
                    )
                    for side in sorted(set(vp_initial_counts_by_side.keys()) | set(vp_final_counts_by_side.keys()))
                },
                vp_gained_avg_by_side={
                    side: (float(vp_gained_sum_by_side.get(side, 0.0)) / float(max(1, len(seeds))))
                    for side in sorted(set(vp_initial_counts_by_side.keys()) | set(vp_final_counts_by_side.keys()))
                },
                vp_lost_avg_by_side={
                    side: (float(vp_lost_sum_by_side.get(side, 0.0)) / float(max(1, len(seeds))))
                    for side in sorted(set(vp_initial_counts_by_side.keys()) | set(vp_final_counts_by_side.keys()))
                },
                vp_final_distribution_by_side={
                    side: {
                        str(vp): (c / float(max(1, len(seeds))))
                        for vp, c in sorted(counts.items(), key=lambda kv: kv[0])
                    }
                    for side, counts in vp_final_counts_by_side.items()
                },
                winner_side_counts={
                    side: int(winner_side_counts.get(side, 0))
                    for side in sorted(
                        set(winner_side_counts.keys())
                        | set(vp_initial_counts_by_side.keys())
                        | set(vp_final_counts_by_side.keys())
                    )
                },
                winner_side_rates={
                    side: (
                        float(winner_side_counts.get(side, 0))
                        / float(max(1, len(seeds)))
                    )
                    for side in sorted(
                        set(winner_side_counts.keys())
                        | set(vp_initial_counts_by_side.keys())
                        | set(vp_final_counts_by_side.keys())
                    )
                },
                tracked_side=tracked_side,
                tracked_metric=tracked_metric,
                tracked_captured_avg=(
                    sum(float(x) for x in tracked_captured_values) / float(max(1, len(tracked_captured_values)))
                ),
                tracked_captured_distribution={
                    str(v): (
                        float(sum(1 for x in tracked_captured_values if int(x) == int(v)))
                        / float(max(1, len(tracked_captured_values)))
                    )
                    for v in sorted(set(int(x) for x in tracked_captured_values))
                },
                scenario_outcome_counts={
                    k: int(v) for k, v in sorted(scenario_outcome_counts.items(), key=lambda kv: kv[0])
                },
                scenario_outcome_rates={
                    k: (float(v) / float(max(1, len(seeds))))
                    for k, v in sorted(scenario_outcome_counts.items(), key=lambda kv: kv[0])
                },
                scenario_outcome_class_counts={
                    k: int(v) for k, v in sorted(scenario_outcome_class_counts.items(), key=lambda kv: kv[0])
                },
                scenario_outcome_class_rates={
                    k: (float(v) / float(max(1, len(seeds))))
                    for k, v in sorted(scenario_outcome_class_counts.items(), key=lambda kv: kv[0])
                },
                tracked_outcome_bucket_counts={
                    k: int(v) for k, v in sorted(tracked_outcome_bucket_counts.items(), key=lambda kv: kv[0])
                },
                tracked_outcome_bucket_rates={
                    k: (float(v) / float(max(1, len(seeds))))
                    for k, v in sorted(tracked_outcome_bucket_counts.items(), key=lambda kv: kv[0])
                },
                opponent_outcome_bucket_counts={
                    k: int(v) for k, v in sorted(opponent_outcome_bucket_counts.items(), key=lambda kv: kv[0])
                },
                opponent_outcome_bucket_rates={
                    k: (float(v) / float(max(1, len(seeds))))
                    for k, v in sorted(opponent_outcome_bucket_counts.items(), key=lambda kv: kv[0])
                },
                phase_2_9_eval_kpis={
                    "reaction_window_count": int(
                        sum(int(r.get("reaction_window_count", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_count": int(
                        sum(int(r.get("reaction_fire_count", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_skipped_count": int(
                        sum(int(r.get("reaction_fire_skipped_count", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_kill_conversions": int(
                        sum(int(r.get("reaction_fire_kill_conversions", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_damage_sum": float(
                        sum(float(r.get("reaction_fire_damage_sum", 0.0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_activation_rate": (
                        float(sum(float(r.get("reaction_fire_activation_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "reaction_fire_kill_conversion_rate": (
                        float(sum(float(r.get("reaction_fire_kill_conversion_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "reaction_fire_damage_induced_proxy": (
                        float(sum(float(r.get("reaction_fire_damage_induced_proxy", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "reaction_fire_damage_prevented_proxy": (
                        float(sum(float(r.get("reaction_fire_damage_prevented_proxy", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "assault_melee_action_family_count": int(
                        sum(int(r.get("assault_melee_action_family_count", 0)) for r in phase29_seed_rows)
                    ),
                    "melee_attempts": int(
                        sum(int(r.get("melee_attempts", 0)) for r in phase29_seed_rows)
                    ),
                    "melee_success_count": int(
                        sum(int(r.get("melee_success_count", 0)) for r in phase29_seed_rows)
                    ),
                    "melee_kills_sum": float(
                        sum(float(r.get("melee_kills_sum", 0.0)) for r in phase29_seed_rows)
                    ),
                    "melee_damage_sum": float(
                        sum(float(r.get("melee_damage_sum", 0.0)) for r in phase29_seed_rows)
                    ),
                    "melee_success_rate": (
                        float(sum(float(r.get("melee_success_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "melee_kills_per_attempt": (
                        float(sum(float(r.get("melee_kills_per_attempt", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "melee_damage_per_attempt": (
                        float(sum(float(r.get("melee_damage_per_attempt", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "assault_favorable_count": int(
                        sum(int(r.get("assault_favorable_count", 0)) for r in phase29_seed_rows)
                    ),
                    "assault_unfavorable_count": int(
                        sum(int(r.get("assault_unfavorable_count", 0)) for r in phase29_seed_rows)
                    ),
                    "xai_decision_steps": int(
                        sum(int(r.get("xai_decision_steps", 0)) for r in phase29_seed_rows)
                    ),
                    "xai_vp_capture_opportunity_steps": int(
                        sum(int(r.get("xai_vp_capture_opportunity_steps", 0)) for r in phase29_seed_rows)
                    ),
                    "xai_vp_capture_taken_steps": int(
                        sum(int(r.get("xai_vp_capture_taken_steps", 0)) for r in phase29_seed_rows)
                    ),
                    "xai_vp_immediate_capture_opportunity_steps": int(
                        sum(
                            int(r.get("xai_vp_immediate_capture_opportunity_steps", 0))
                            for r in phase29_seed_rows
                        )
                    ),
                    "xai_vp_immediate_capture_taken_steps": int(
                        sum(
                            int(r.get("xai_vp_immediate_capture_taken_steps", 0))
                            for r in phase29_seed_rows
                        )
                    ),
                    "xai_policy_confidence_mean": (
                        float(sum(float(r.get("xai_policy_confidence_mean", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "xai_policy_margin_mean": (
                        float(sum(float(r.get("xai_policy_margin_mean", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "xai_latent_signal_coverage": (
                        float(sum(float(r.get("xai_latent_signal_coverage", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "xai_vp_capture_take_rate": (
                        float(sum(float(r.get("xai_vp_capture_take_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "xai_vp_immediate_capture_take_rate": (
                        float(
                            sum(
                                float(r.get("xai_vp_immediate_capture_take_rate", 0.0))
                                for r in phase29_seed_rows
                            )
                        )
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                },
                phase_2_9_eval_kpis_by_side={
                    side: {
                        "reaction_window_count": int(
                            sum(int((r.get(side, {}) or {}).get("reaction_window_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "reaction_fire_count": int(
                            sum(int((r.get(side, {}) or {}).get("reaction_fire_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "reaction_fire_skipped_count": int(
                            sum(int((r.get(side, {}) or {}).get("reaction_fire_skipped_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "reaction_fire_kill_conversions": int(
                            sum(int((r.get(side, {}) or {}).get("reaction_fire_kill_conversions", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "reaction_fire_damage_sum": float(
                            sum(float((r.get(side, {}) or {}).get("reaction_fire_damage_sum", 0.0)) for r in phase29_seed_rows_by_side)
                        ),
                        "reaction_fire_activation_rate": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("reaction_fire_activation_rate", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "reaction_fire_kill_conversion_rate": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("reaction_fire_kill_conversion_rate", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "reaction_fire_damage_induced_proxy": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("reaction_fire_damage_induced_proxy", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "reaction_fire_damage_prevented_proxy": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("reaction_fire_damage_prevented_proxy", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "assault_melee_action_family_count": int(
                            sum(int((r.get(side, {}) or {}).get("assault_melee_action_family_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "melee_attempts": int(
                            sum(int((r.get(side, {}) or {}).get("melee_attempts", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "melee_success_count": int(
                            sum(int((r.get(side, {}) or {}).get("melee_success_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "melee_kills_sum": float(
                            sum(float((r.get(side, {}) or {}).get("melee_kills_sum", 0.0)) for r in phase29_seed_rows_by_side)
                        ),
                        "melee_damage_sum": float(
                            sum(float((r.get(side, {}) or {}).get("melee_damage_sum", 0.0)) for r in phase29_seed_rows_by_side)
                        ),
                        "melee_success_rate": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("melee_success_rate", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "melee_kills_per_attempt": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("melee_kills_per_attempt", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "melee_damage_per_attempt": (
                            float(
                                sum(float((r.get(side, {}) or {}).get("melee_damage_per_attempt", 0.0)) for r in phase29_seed_rows_by_side)
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "assault_favorable_count": int(
                            sum(int((r.get(side, {}) or {}).get("assault_favorable_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "assault_unfavorable_count": int(
                            sum(int((r.get(side, {}) or {}).get("assault_unfavorable_count", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "xai_decision_steps": int(
                            sum(int((r.get(side, {}) or {}).get("xai_decision_steps", 0)) for r in phase29_seed_rows_by_side)
                        ),
                        "xai_vp_capture_opportunity_steps": int(
                            sum(
                                int((r.get(side, {}) or {}).get("xai_vp_capture_opportunity_steps", 0))
                                for r in phase29_seed_rows_by_side
                            )
                        ),
                        "xai_vp_capture_taken_steps": int(
                            sum(
                                int((r.get(side, {}) or {}).get("xai_vp_capture_taken_steps", 0))
                                for r in phase29_seed_rows_by_side
                            )
                        ),
                        "xai_vp_immediate_capture_opportunity_steps": int(
                            sum(
                                int(
                                    (r.get(side, {}) or {}).get(
                                        "xai_vp_immediate_capture_opportunity_steps", 0
                                    )
                                )
                                for r in phase29_seed_rows_by_side
                            )
                        ),
                        "xai_vp_immediate_capture_taken_steps": int(
                            sum(
                                int(
                                    (r.get(side, {}) or {}).get(
                                        "xai_vp_immediate_capture_taken_steps", 0
                                    )
                                )
                                for r in phase29_seed_rows_by_side
                            )
                        ),
                        "xai_policy_confidence_mean": (
                            float(
                                sum(
                                    float((r.get(side, {}) or {}).get("xai_policy_confidence_mean", 0.0))
                                    for r in phase29_seed_rows_by_side
                                )
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "xai_policy_margin_mean": (
                            float(
                                sum(
                                    float((r.get(side, {}) or {}).get("xai_policy_margin_mean", 0.0))
                                    for r in phase29_seed_rows_by_side
                                )
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "xai_latent_signal_coverage": (
                            float(
                                sum(
                                    float((r.get(side, {}) or {}).get("xai_latent_signal_coverage", 0.0))
                                    for r in phase29_seed_rows_by_side
                                )
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "xai_vp_capture_take_rate": (
                            float(
                                sum(
                                    float((r.get(side, {}) or {}).get("xai_vp_capture_take_rate", 0.0))
                                    for r in phase29_seed_rows_by_side
                                )
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                        "xai_vp_immediate_capture_take_rate": (
                            float(
                                sum(
                                    float(
                                        (r.get(side, {}) or {}).get(
                                            "xai_vp_immediate_capture_take_rate", 0.0
                                        )
                                    )
                                    for r in phase29_seed_rows_by_side
                                )
                            )
                            / float(max(1, len(phase29_seed_rows_by_side)))
                        ),
                    }
                    for side in sorted(
                        {
                            str(side)
                            for r in phase29_seed_rows_by_side
                            for side in (r or {}).keys()
                        }
                    )
                },
                eval_decision_summary=eval_decision_summary,
                eval_decisions_top=eval_decisions_top,
                eval_decision_steps_top=eval_decision_steps_top,
            )
        )
        last = results[-1]
        print(
            f"[Bench] agent={agent_name} done "
            f"avg_return={last.avg_return:.3f} avg_steps={last.avg_steps:.1f} "
            f"terminal_rate={last.terminal_rate:.3f} timeout_rate={last.timeout_rate:.3f} "
            f"win_rate={last.win_rate:.3f}"
        , flush=True)

    run_id = ""
    if checkpoint_path:
        try:
            ckptp = Path(checkpoint_path)
            if not ckptp.is_absolute():
                ckptp = (Path.cwd() / ckptp).resolve()
            run_id = str(ckptp.parent.parent.name)
        except Exception:
            run_id = ""
    payload = {"scenario_id": scenario_id, "run_id": run_id, "results": [r.__dict__ for r in results]}
    muzero_row = next((r.__dict__ for r in results if r.agent_name == "muzero_stub"), {})
    baseline_row = next((r.__dict__ for r in results if r.agent_name == "baseline_random"), {})
    train_summary = _load_train_summary_from_checkpoint(checkpoint_path=checkpoint_path)
    train_phase29 = dict(train_summary.get("phase_2_9_train_kpis", {}) or {})
    eval_phase29 = _aggregate_muzero_eval_kpis(payload["results"]) or dict(
        muzero_row.get("phase_2_9_eval_kpis", {}) or {}
    )
    payload["phase_2_9_train_eval"] = _build_phase29_train_eval(
        train_kpis=train_phase29,
        eval_kpis=eval_phase29,
    )
    payload["phase_2_9_promotion_gate"] = _build_phase29_promotion_gate(
        train_kpis=train_phase29,
        eval_kpis=eval_phase29,
        muzero_row=muzero_row,
        baseline_row=baseline_row,
    )
    payload["diagnostics_summary_eval"] = _build_eval_diagnostics_summary(
        eval_kpis=eval_phase29,
        tracked_side=str(muzero_row.get("tracked_side", "") or ""),
    )
    payload["head_diagnostics_eval"] = _build_head_diagnostics_eval(
        train_summary=train_summary,
        eval_kpis=eval_phase29,
        muzero_row=muzero_row,
    )
    out = run_root / "bench_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_dumps(payload, indent=2), encoding="utf-8")
    if run_id:
        bench_stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        bench_replay_payload = {
            "schema_version": "bench_replay_v1",
            "run_id": str(run_id),
            "scenario_id": str(scenario_id),
            "bench_id": str(bench_stamp),
            "episodes": list(bench_replay_episodes),
        }
        run_xai_dir = run_root / str(run_id) / "xai"
        run_xai_dir.mkdir(parents=True, exist_ok=True)
        bench_replay_out = run_xai_dir / "bench_replay_latest.json"
        bench_replay_out.write_text(_json_dumps(bench_replay_payload, indent=2), encoding="utf-8")
        bench_replay_hist = run_xai_dir / f"bench_replay_{bench_stamp}.json"
        bench_replay_hist.write_text(_json_dumps(bench_replay_payload, indent=2), encoding="utf-8")
        bench_eval_hist = run_xai_dir / f"bench_eval_{bench_stamp}.json"
        bench_eval_hist.write_text(_json_dumps(payload, indent=2), encoding="utf-8")
    if mlflow_mod is not None:
        try:
            _mlflow_log_metrics(
                mlflow_mod,
                {
                    "phase29_gate_pass": 1.0
                    if str(payload.get("phase_2_9_promotion_gate", {}).get("status", "")).upper()
                    == "PASS"
                    else 0.0,
                    "phase29_eval_reaction_activation_rate": float(
                        payload.get("phase_2_9_train_eval", {})
                        .get("eval", {})
                        .get("reaction_fire_activation_rate", 0.0)
                    ),
                    "phase29_eval_melee_attempts": float(
                        payload.get("phase_2_9_train_eval", {})
                        .get("eval", {})
                        .get("melee_attempts", 0.0)
                    ),
                    "phase29_eval_converted_from_progress_rate": float(
                        payload.get("phase_2_9_train_eval", {})
                        .get("eval", {})
                        .get("converted_from_progress_rate", 0.0)
                    ),
                    "phase29_eval_converted_rate_near_vp": float(
                        payload.get("phase_2_9_train_eval", {})
                        .get("eval", {})
                        .get("converted_rate_near_vp", 0.0)
                    ),
                    "phase29_eval_conversion_within_2_turns_after_progress": float(
                        payload.get("phase_2_9_train_eval", {})
                        .get("eval", {})
                        .get("conversion_within_2_turns_after_progress", 0.0)
                    ),
                },
            )
            mlflow_mod.log_artifact(str(out))
            mlflow_mod.end_run()
        except Exception:
            pass
    return payload


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VOEC benchmark matrix.")
    parser.add_argument(
        "--config",
        default="assault_bench/configs/benchmark_config.yaml",
        help="Path to benchmark YAML config file.",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="Optional checkpoint path; empty or 'latest' auto-selects newest checkpoint under runs/muzero_* or runs/efficientzero_v2_*.",
    )
    parser.add_argument(
        "--muzero-config",
        default="",
        help="Optional model config path used to build network shape when --checkpoint is set. If omitted, inferred by checkpoint engine.",
    )
    parser.add_argument(
        "--mlflow-experiment",
        default="assault_bench",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--mlflow-run-name",
        default="",
        help="Optional MLflow run name.",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda", "auto"),
        default="",
        help="Optional benchmark device override; when unset, benchmark config device is used.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    print(
        _json_dumps(
            run_benchmark(
                config_path=args.config,
                checkpoint_path=args.checkpoint,
                muzero_config_path=args.muzero_config,
                mlflow_experiment=args.mlflow_experiment,
                mlflow_run_name=args.mlflow_run_name,
                device=args.device,
            )
        )
    )
