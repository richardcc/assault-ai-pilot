# assault_model/map/combat_geometry.py

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


def _as_xy(pos: CoordLike) -> Tuple[int, int]:
    """
    Normalize a coordinate input to (x, y).

    Accepts:
    - (q, r) tuple              [legacy code]
    - HexCoord object           [new architecture]

    Returns:
    - (x, y) tuple

    Design note:
    - Domain code should always use HexCoord.
    - Geometry utilities remain permissive to avoid
      forcing conversions at call sites.
    """
    if isinstance(pos, HexCoord):
        return pos.q, pos.r
    return pos


# -------------------------------------------------
# MAIN API
# -------------------------------------------------
def determine_attack_sector(
    attacker_pos: CoordLike,
    defender_pos: CoordLike,
    defender_facing: str,
) -> AttackSector:
    """
    Determine the attack sector based on relative positions
    and defender facing.

    Parameters:
    - attacker_pos:
        HexCoord or (q, r)
    - defender_pos:
        HexCoord or (q, r)
    - defender_facing:
        Facing direction of the defender ("N", "S", "E", "W")

    Returns:
    - AttackSector enum value
    """

    ax, ay = _as_xy(attacker_pos)
    dx, dy = _as_xy(defender_pos)

    vx = ax - dx
    vy = ay - dy

    facing_vectors = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
    }

    fx, fy = facing_vectors[defender_facing]

    dot = vx * fx + vy * fy

    if dot > 0:
        sector = AttackSector.FRONT
    elif dot < 0:
        sector = AttackSector.REAR
    else:
        cross = fx * vy - fy * vx
        if cross > 0:
            sector = AttackSector.FLANK_LEFT
        else:
            sector = AttackSector.FLANK_RIGHT

    _trace(
        "ATTACK_SECTOR",
        attacker_pos=(ax, ay),
        defender_pos=(dx, dy),
        defender_facing=defender_facing,
        sector=sector.name,
    )

    return sector