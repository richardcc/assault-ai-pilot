from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


def safe_float_or_none(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def safe_int_or_none(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def normalize_side_key(side: object) -> str:
    raw = getattr(side, "value", side)
    return str(raw or "").strip().upper()


def _parse_owner_key(raw_key: object) -> Optional[Tuple[int, int]]:
    text = str(raw_key or "").strip()
    if not text:
        return None
    if "," in text:
        parts = [p.strip() for p in text.split(",", 1)]
    elif ":" in text:
        parts = [p.strip() for p in text.split(":", 1)]
    else:
        return None
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


@dataclass(frozen=True)
class SignalValue:
    value: Optional[float]
    source: str
    available: bool
    reason: str = "missing"


@dataclass
class UnitSnapshotIndex:
    rows: List[Dict[str, object]]
    positions: List[Dict[str, object]]
    hp_by_id: Dict[str, float]
    alive_by_id: Dict[str, bool]
    suppressed_by_id: Dict[str, bool]

    @classmethod
    def from_units(cls, units: List[object]) -> "UnitSnapshotIndex":
        rows: List[Dict[str, object]] = []
        positions: List[Dict[str, object]] = []
        hp_by_id: Dict[str, float] = {}
        alive_by_id: Dict[str, bool] = {}
        suppressed_by_id: Dict[str, bool] = {}
        for unit in list(units or []):
            if isinstance(unit, dict):
                get = lambda k, d=None: unit.get(k, d)
            else:
                get = lambda k, d=None: getattr(unit, k, d)
            unit_id = str(get("unit_id", "") or "")
            side = str(get("side", "") or "")
            q = safe_int_or_none(get("q", None))
            r = safe_int_or_none(get("r", None))
            hp = safe_float_or_none(get("hp", None))
            alive_raw = get("alive", None)
            alive = bool(alive_raw) if alive_raw is not None else None
            suppressed = None
            for key in ("suppressed", "is_suppressed", "pinned", "is_pinned"):
                raw = get(key, None)
                if raw is None:
                    continue
                if isinstance(raw, bool):
                    suppressed = raw
                    break
                if isinstance(raw, (int, float)):
                    suppressed = bool(raw)
                    break
                txt = str(raw).strip().lower()
                if txt in {"1", "true", "yes", "y", "on"}:
                    suppressed = True
                    break
                if txt in {"0", "false", "no", "n", "off"}:
                    suppressed = False
                    break
            row = {
                "unit_id": unit_id,
                "side": side,
                "q": int(q) if q is not None else None,
                "r": int(r) if r is not None else None,
                "hp": hp,
                "alive": bool(alive) if alive is not None else None,
                "suppressed": bool(suppressed) if suppressed is not None else None,
            }
            rows.append(row)
            if unit_id:
                if hp is not None:
                    hp_by_id[unit_id] = float(hp)
                if alive is not None:
                    alive_by_id[unit_id] = bool(alive)
                if suppressed is not None:
                    suppressed_by_id[unit_id] = bool(suppressed)
            if q is not None and r is not None:
                positions.append(
                    {"unit_id": unit_id, "side": side, "q": int(q), "r": int(r)}
                )
        return cls(
            rows=rows,
            positions=positions,
            hp_by_id=hp_by_id,
            alive_by_id=alive_by_id,
            suppressed_by_id=suppressed_by_id,
        )


@dataclass(frozen=True)
class VPOwnershipSnapshot:
    owners_by_qr: Dict[Tuple[int, int], str]

    @classmethod
    def from_owner_map(cls, vp_owner_by_hex: Dict[str, str]) -> "VPOwnershipSnapshot":
        owners: Dict[Tuple[int, int], str] = {}
        for raw_key, owner in dict(vp_owner_by_hex or {}).items():
            parsed = _parse_owner_key(raw_key)
            if parsed is None:
                continue
            owners[(int(parsed[0]), int(parsed[1]))] = normalize_side_key(owner)
        return cls(owners_by_qr=owners)

    def counts_for_side(self, side: str) -> Tuple[int, int]:
        side_norm = normalize_side_key(side)
        friendly = 0
        enemy = 0
        for owner in self.owners_by_qr.values():
            own_norm = normalize_side_key(owner)
            if not own_norm:
                continue
            if own_norm == side_norm:
                friendly += 1
            else:
                enemy += 1
        return int(friendly), int(enemy)
