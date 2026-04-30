from enum import Enum


class LineOfSight(Enum):
    CLEAR = "CLEAR"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


# -------------------------------------------------
# Hex distance helper (axial coordinates)
# -------------------------------------------------
def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """
    Compute axial hex distance between two hexes (q, r).
    """
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


# -------------------------------------------------
# LOS computation (RANGE-BASED, SIMPLE)
# -------------------------------------------------
def check_line_of_sight(attacker, target, game_map) -> LineOfSight:
    """
    LOS rule (temporary):
    - CLEAR if distance <= 3 hexes
    - BLOCKED otherwise
    """

    dist = hex_distance(attacker.position, target.position)

    if dist <= 3:
        return LineOfSight.CLEAR

    return LineOfSight.BLOCKED


def has_line_of_sight(attacker, target, game_map) -> bool:
    """
    Convenience helper used by RuntimeGameState.
    """
    return check_line_of_sight(attacker, target, game_map) == LineOfSight.CLEAR
