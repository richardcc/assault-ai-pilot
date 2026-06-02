from assault_model.map.hex_utils import safe_hex_distance
from assault_model.map.hex_coord import HexCoord
from assault_model.combat.line_of_sight import check_line_of_sight


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
    # ✅ PATH (same ray as LOS terrain check)
    # -------------------------------------------------
    los_debug = getattr(attacker, "_los_debug", {})
    full_path = los_debug.get("path", [])
    path = full_path[1:-1] if len(full_path) > 2 else []

    blocking = los_debug.get("blocking", [])
    hindrance = los_debug.get("hindrance", [])

    # -------------------------------------------------
    # RETURN
    # -------------------------------------------------
    return {
        "distance": distance,
        "los": los.name,
        "path": path,
        "path_full": full_path,
        "blocking": blocking,
        "hindrance": hindrance,
    }