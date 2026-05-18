from enum import Enum

from assault_model.map.hex_line import hex_line
from assault_model.map.hex_coord import HexCoord


# -------------------------------------------------
# LOS RESULT
# -------------------------------------------------

class LineOfSight(Enum):
    CLEAR = 0
    HINDERED = 1
    BLOCKED = 2


# -------------------------------------------------
# CACHE GLOBAL
# -------------------------------------------------

_los_cache = {}


def _make_key(a: HexCoord, b: HexCoord):
    return (a.q, a.r, b.q, b.r)


def check_line_of_sight(attacker, target, game_map, terrain_config):

    start = attacker.position
    end = target.position

    key = _make_key(start, end)

    # ✅ CACHE HIT
    if key in _los_cache:
        return _los_cache[key]

    line = hex_line(start, end)

    # ignoramos origen y destino
    path = line[1:-1]

    hindrance = 0

    for coord in path:
        hex_ = game_map.get_hex(coord.q, coord.r)

        if not hex_:
            continue

        terrain = hex_.get_terrain()
        config = terrain_config.get(terrain, {})

        los_type = config.get("los", "CLEAR")

        # -------------------------------------------------
        # BLOCKED → exit inmediato
        # -------------------------------------------------
        if los_type == "BLOCKED":
            result = LineOfSight.BLOCKED
            _los_cache[key] = result
            return result

        # -------------------------------------------------
        # HINDERED → acumulamos
        # -------------------------------------------------
        if los_type == "HINDERED":
            hindrance += 1

            # ✅ regla del manual: 3 hindrances = BLOCKED
            if hindrance >= 3:
                result = LineOfSight.BLOCKED
                _los_cache[key] = result
                return result

    # -------------------------------------------------
    # RESULTADO FINAL
    # -------------------------------------------------
    if hindrance >= 1:
        result = LineOfSight.HINDERED
    else:
        result = LineOfSight.CLEAR

    _los_cache[key] = result
    return result


def has_line_of_sight(attacker, target, game_map, terrain_config):
    return check_line_of_sight(
        attacker,
        target,
        game_map,
        terrain_config
    ) != LineOfSight.BLOCKED