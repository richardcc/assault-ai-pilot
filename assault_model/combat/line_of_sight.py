from enum import Enum

# Canonical hex distance utility (supports HexCoord)
from assault_model.map.hex_utils import hex_distance


class LineOfSight(Enum):
    CLEAR = "CLEAR"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


# -------------------------------------------------
# LOS computation (RANGE-BASED, TEMPORARY)
# -------------------------------------------------
def check_line_of_sight(attacker, target, game_map) -> LineOfSight:
    """
    Temporary Line of Sight rule (Phase 01.5).

    This implementation is intentionally simple and is only
    used to validate ranged fire legality (RF-R02).

    Rules:
    - CLEAR if hex distance <= 3
    - BLOCKED otherwise

    Terrain, elevation, and obstruction modifiers are handled
    later during combat resolution.
    """
    distance = hex_distance(attacker.position, target.position)

    if distance <= 3:
        return LineOfSight.CLEAR

    return LineOfSight.BLOCKED


def has_line_of_sight(attacker, target, game_map) -> bool:
    """
    Convenience helper for direct ranged fire validation.

    Returns True only if LOS is CLEAR.
    """
    return (
        check_line_of_sight(attacker, target, game_map)
        == LineOfSight.CLEAR
    )
