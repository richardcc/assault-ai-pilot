from enum import Enum
from assault_model.config.terrain_config import terrain_config


class LineOfSight(Enum):
    CLEAR = "CLEAR"
    HINDERED = "HINDERED"
    BLOCKED = "BLOCKED"


# -------------------------------------------------
# ✅ MAIN LOS FUNCTION
# -------------------------------------------------
def check_line_of_sight(attacker, target, game_map) -> LineOfSight:
    """
    Determines line of sight between attacker and target
    using terrain_config.

    Current simplified model:
    - Only target hex is evaluated
    - Future: full hex-path tracing
    """

    if game_map is None:
        return LineOfSight.CLEAR

    target_hex = game_map.get_hex_from_coord(target.position)

    if target_hex is None:
        return LineOfSight.CLEAR

    # ✅ single source of truth
    terrain_name = target_hex.get_terrain()

    # ✅ rules come from config
    los_type = terrain_config.get_los(terrain_name)

    try:
        return LineOfSight[los_type]
    except KeyError:
        raise ValueError(f"Invalid LOS type '{los_type}' in terrain_config")


# -------------------------------------------------
# ✅ HELPER
# -------------------------------------------------
def has_line_of_sight(attacker, target, game_map) -> bool:
    """
    Returns True if LOS is not blocked.
    """

    return check_line_of_sight(attacker, target, game_map) != LineOfSight.BLOCKED
