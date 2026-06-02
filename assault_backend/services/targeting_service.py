from assault_model.map.hex_utils import hex_distance
from assault_model.map.hex_coord import HexCoord
from assault_model.combat.line_of_sight import check_line_of_sight


def compute_targeting_info(game_state, attacker_id: str, target_q: int, target_r: int):
    """
    Returns:
    {
        "distance": int,
        "los": "CLEAR|HINDERED|BLOCKED"
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

    # ✅ objeto dummy target (solo necesita .position)
    class DummyTarget:
        def __init__(self, pos):
            self.position = pos

    target = DummyTarget(target_pos)

    # ✅ DISTANCIA REAL
    distance = hex_distance(attacker.position, target_pos)

    # ✅ LOS REAL (FIXED ✅)
    los = check_line_of_sight(
        attacker,
        target,
        game_state.game_map,
        game_state.game_map.terrain_config   # ✅ CORRECTO
    )

    return {
        "distance": distance,
        "los": los.name
    }