from typing import Tuple, Union
import os

from assault_model.combat.attack_sector import AttackSector
from assault_model.map.hex_coord import HexCoord


# -------------------------------------------------
# DEBUG TRACE (configurable by environment variable)
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# -------------------------------------------------
# INTERNAL HELPERS
# -------------------------------------------------
CoordLike = Union[Tuple[int, int], HexCoord]


def _as_axial(pos: CoordLike) -> Tuple[int, int]:
    """
    Normalize a coordinate input to axial (q, r).

    Accepts:
    - (q, r) tuple
    - HexCoord

    Returns:
    - (q, r)
    """
    if isinstance(pos, HexCoord):
        return pos.q, pos.r
    return pos


def _hex_direction(dq: int, dr: int) -> Tuple[int, int]:
    """
    Reduce a vector to its dominant hex direction.
    """
    if abs(dq) >= abs(dr):
        return (1 if dq > 0 else -1 if dq < 0 else 0, 0)
    else:
        return (0, 1 if dr > 0 else -1 if dr < 0 else 0)


# -------------------------------------------------
# MAIN API
# -------------------------------------------------
def calculate_facing_towards(origin: CoordLike, target: CoordLike, default_facing: str = "N") -> str:
    """
    Calculate the dominant hex cardinal facing direction ('N', 'S', 'E', 'W')
    from origin to target.
    """
    oq, or_ = _as_axial(origin)
    tq, tr = _as_axial(target)

    dq = tq - oq
    dr = tr - or_

    if dq == 0 and dr == 0:
        return default_facing

    if abs(dq) >= abs(dr):
        return "E" if dq > 0 else "W"
    else:
        return "S" if dr > 0 else "N"


def is_in_arc_of_fire(
    origin: CoordLike,
    origin_facing: str,
    target: CoordLike,
    has_pivot: bool = False,
    has_limited_pivot: bool = False,
) -> bool:
    """
    Check if target is within origin's arc of fire.
    - If unit has PIVOT trait (360-degree arc of fire), returns True regardless of facing.
    - If unit has LIMITED_PIVOT trait (240-degree arc of fire to flank and rear, Rule S43),
      returns True only if target is NOT in frontal arc (dot <= 0).
    - Otherwise, standard forward arc (dot >= 0) is required.
    """
    if has_pivot:
        return True

    oq, or_ = _as_axial(origin)
    tq, tr = _as_axial(target)

    vq = tq - oq
    vr = tr - or_
    dir_v = _hex_direction(vq, vr)

    facing_dirs = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
    }

    facing = facing_dirs.get(origin_facing, (0, -1))
    dot = dir_v[0] * facing[0] + dir_v[1] * facing[1]

    if has_limited_pivot:
        return dot <= 0

    return dot >= 0


def determine_attack_sector(
    attacker_pos: CoordLike,
    defender_pos: CoordLike,
    defender_facing: str,
) -> AttackSector:
    """
    Determine the attack sector based on hex-relative direction
    and defender facing.

    Facing values:
    - "N", "S", "E", "W"
    """

    aq, ar = _as_axial(attacker_pos)
    dq, dr = _as_axial(defender_pos)

    # Vector from defender to attacker
    vq = aq - dq
    vr = ar - dr

    dir_v = _hex_direction(vq, vr)

    facing_dirs = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
    }

    facing = facing_dirs[defender_facing]

    # Dot product in axial space (good enough for hex sectoring)
    dot = dir_v[0] * facing[0] + dir_v[1] * facing[1]

    if dot > 0:
        sector = AttackSector.FRONT
    elif dot < 0:
        sector = AttackSector.REAR
    else:
        # Left / right flank determined by perpendicularity sign
        cross = facing[0] * dir_v[1] - facing[1] * dir_v[0]
        sector = (
            AttackSector.FLANK_LEFT
            if cross > 0
            else AttackSector.FLANK_RIGHT
        )

    _trace(
        "ATTACK_SECTOR",
        attacker_pos=(aq, ar),
        defender_pos=(dq, dr),
        defender_facing=defender_facing,
        relative_dir=dir_v,
        sector=sector.name,
    )

    return sector
