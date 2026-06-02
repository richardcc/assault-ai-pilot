from assault_model.map.hex_utils import safe_hex_distance
from assault_model.map.hex_coord import HexCoord
from assault_model.combat.line_of_sight import (
    check_line_of_sight,
    _hex_path_strict
)


def compute_targeting_info(game_state, attacker_id: str, target_q: int, target_r: int):
    """
    Returns:
    {
        "distance": int,
        "los": "CLEAR|HINDERED|BLOCKED",
        "path": [(q, r), ...],
        "blocking": [(q, r), ...],
        "hindrance": [(q, r), ...]
    }
    """

    # ✅ buscar atacante
    attacker = next(
        (u for u in game_state.units if u.unit_id == attacker_id),
        None
    )

    if attacker is None or not attacker.alive:
        return None

    # ✅ posición target (hex)
    target_pos = HexCoord(target_q, target_r)

    # ✅ dummy target
    class DummyTarget:
        def __init__(self, pos):
            self.position = pos

    target = DummyTarget(target_pos)

    # ✅ DISTANCIA REAL
    distance = safe_hex_distance(attacker.position, target_pos)

    # ✅ LOS REAL (esto también rellena _los_debug)
    los = check_line_of_sight(
        attacker,
        target,
        game_state.game_map,
        game_state.game_map.terrain_config
    )

    # -------------------------------------------------
    # ✅ PATH REAL (MISMO QUE LOS)
    # -------------------------------------------------
    path_coords = _hex_path_strict(
        attacker.position,
        target_pos
    )

    # ignorar start y end si quieres coherencia con LOS
    path_coords = path_coords[1:-1] if path_coords else []

    path = [(h.q, h.r) for h in path_coords]

    # -------------------------------------------------
    # ✅ DEBUG LOS (bloqueos y hindrance)
    # -------------------------------------------------
    los_debug = getattr(attacker, "_los_debug", {})

    blocking = los_debug.get("blocking", [])
    hindrance = los_debug.get("hindrance", [])

    # -------------------------------------------------
    # RETURN
    # -------------------------------------------------
    return {
        "distance": distance,
        "los": los.name,
        "path": path,
        "blocking": blocking,
        "hindrance": hindrance,
    }