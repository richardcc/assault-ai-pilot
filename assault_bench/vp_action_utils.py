from __future__ import annotations

from functools import lru_cache
import re
from typing import Dict, List, Optional

from assault_bench.action_utils import action_kind_from_id
from assault_bench.telemetry_models import normalize_side_key


def _vp_hexes_cache_key(vp_hexes: List[object]) -> tuple[tuple[int, int, str], ...]:
    out: list[tuple[int, int, str]] = []
    for v in list(vp_hexes or []):
        if isinstance(v, dict):
            q, r = v.get("q", None), v.get("r", None)
            label = str(
                v.get("vp_id", "")
                or v.get("id", "")
                or v.get("label", "")
                or ""
            )
        else:
            q, r = getattr(v, "q", None), getattr(v, "r", None)
            label = str(
                getattr(v, "vp_id", "")
                or getattr(v, "id", "")
                or getattr(v, "label", "")
                or ""
            )
        if isinstance(q, int) and isinstance(r, int):
            if not str(label or "").strip():
                label = f"VP_{int(q)}_{int(r)}"
            out.append((int(q), int(r), str(label)))
    return tuple(out)


@lru_cache(maxsize=256)
def _extract_vp_hexes_cached(vp_key: tuple[tuple[int, int, str], ...]) -> tuple[tuple[int, int, str], ...]:
    return tuple(vp_key or ())


def _owner_cache_key(vp_owner_by_hex: Dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in dict(vp_owner_by_hex or {}).items()))


@lru_cache(maxsize=2048)
def _owner_by_qr_cached(owner_key: tuple[tuple[str, str], ...]) -> tuple[tuple[tuple[int, int], str], ...]:
    owners_by_qr: Dict[tuple[int, int], str] = {}
    for raw_key, owner in owner_key:
        parsed = parse_owner_hex_key(str(raw_key))
        if parsed is None:
            continue
        owners_by_qr[(int(parsed[0]), int(parsed[1]))] = normalize_side_key(owner)
    return tuple(owners_by_qr.items())


@lru_cache(maxsize=4096)
def _parse_action_target_hex_cached(raw: str) -> Optional[tuple[int, int]]:
    if not raw:
        return None
    # Structured payload format: "...target=q,r..."
    m = re.search(r"target=\(?\s*([-\d]+)\s*,\s*([-\d]+)\s*\)?", raw)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except Exception:
            return None
    # Canonical action-id format: "MOVE:UNIT:q:r"
    m = re.search(r":([-\d]+):([-\d]+)$", raw)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except Exception:
            return None
    # Compact/legacy format: "MOVE:UNIT:q,r" or "MOVE:UNIT:(q,r)"
    m = re.search(r":\(?\s*([-\d]+)\s*,\s*([-\d]+)\s*\)?$", raw)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except Exception:
            return None
    return None


@lru_cache(maxsize=1024)
def _capturable_vp_hexes_cached(
    side_norm: str,
    vp_key: tuple[tuple[int, int, str], ...],
    owner_key: tuple[tuple[str, str], ...],
) -> tuple[tuple[int, int], ...]:
    vp_qr = {(int(vq), int(vr)) for vq, vr, _ in vp_key}
    owners_by_qr = dict(_owner_by_qr_cached(owner_key))
    out = [
        (int(q), int(r))
        for q, r in vp_qr
        if normalize_side_key(owners_by_qr.get((int(q), int(r)), "")) != side_norm
    ]
    return tuple(out)


def parse_owner_hex_key(key: str) -> Optional[tuple[int, int]]:
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


def extract_vp_hexes(vp_hexes: List[object]) -> List[tuple[int, int, str]]:
    vp_key = _vp_hexes_cache_key(vp_hexes)
    return list(_extract_vp_hexes_cached(vp_key))


def capturable_vp_hexes_for_side(
    *,
    side: str,
    vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
) -> set[tuple[int, int]]:
    side_norm = normalize_side_key(side)
    vp_key = _vp_hexes_cache_key(vp_hexes)
    owner_key = _owner_cache_key(vp_owner_by_hex)
    return set(_capturable_vp_hexes_cached(side_norm, vp_key, owner_key))


def owner_by_qr(vp_owner_by_hex: Dict[str, str]) -> Dict[tuple[int, int], str]:
    owner_key = _owner_cache_key(vp_owner_by_hex)
    return dict(_owner_by_qr_cached(owner_key))


def parse_action_target_hex(action_id: str) -> Optional[tuple[int, int]]:
    raw = str(action_id or "").strip()
    return _parse_action_target_hex_cached(raw)


def is_move_action_kind(kind: str) -> bool:
    return str(kind or "").strip().upper() == "MOVE"


def count_immediate_vp_capture_move_options(
    *,
    side: str,
    legal_actions: List[str],
    vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
) -> int:
    capturable_hexes = capturable_vp_hexes_for_side(
        side=str(side),
        vp_hexes=list(vp_hexes or []),
        vp_owner_by_hex=dict(vp_owner_by_hex or {}),
    )
    if not capturable_hexes:
        return 0
    count = 0
    for raw_action in list(legal_actions or []):
        aid = str(raw_action or "")
        if not is_move_action_kind(action_kind_from_id(aid)):
            continue
        target = parse_action_target_hex(aid)
        if target is None:
            continue
        if (int(target[0]), int(target[1])) in capturable_hexes:
            count += 1
    return int(count)


def is_immediate_vp_capture_move_taken(
    *,
    side: str,
    chosen_action_id: str,
    vp_hexes: List[object],
    before_vp_owner_by_hex: Dict[str, str],
    after_vp_owner_by_hex: Dict[str, str],
) -> bool:
    chosen_kind = action_kind_from_id(str(chosen_action_id))
    if not is_move_action_kind(chosen_kind):
        return False
    chosen_target = parse_action_target_hex(str(chosen_action_id))
    if chosen_target is None:
        return False
    capturable_hexes_before = capturable_vp_hexes_for_side(
        side=str(side),
        vp_hexes=list(vp_hexes or []),
        vp_owner_by_hex=dict(before_vp_owner_by_hex or {}),
    )
    target_qr = (int(chosen_target[0]), int(chosen_target[1]))
    if target_qr not in capturable_hexes_before:
        return False
    side_norm = normalize_side_key(side)
    before_owner = normalize_side_key(owner_by_qr(dict(before_vp_owner_by_hex or {})).get(target_qr, ""))
    after_owner = normalize_side_key(owner_by_qr(dict(after_vp_owner_by_hex or {})).get(target_qr, ""))
    return bool(after_owner == side_norm and before_owner != side_norm)


def is_vp_capture_taken_for_metrics(
    *,
    vp_captures_eval: int,
    objective_converted: int,
    immediate_capture_taken: bool,
    capture_like_action_taken: bool,
) -> bool:
    if int(vp_captures_eval) > 0:
        return True
    if int(objective_converted) > 0:
        return True
    if bool(immediate_capture_taken):
        return True
    return bool(capture_like_action_taken)
