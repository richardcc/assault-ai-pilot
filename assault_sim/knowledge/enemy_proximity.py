# assault_sim/knowledge/bricks/enemy_proximity.py

from assault_model.map.hex_utils import hex_distance


class EnemyProximityBrick:
    """
    Knowledge Brick:
    Describes proximity of enemy units.
    """

    def evaluate(self, state, unit_id):
        unit = next(
            (u for u in state.units if u.unit_id == unit_id),
            None
        )

        if unit is None:
            return {}

        enemies = [u for u in state.units if u.side != unit.side]

        if not enemies:
            return {
                "enemy_count": 0,
                "nearest_enemy_distance": None,
            }

        distances = [
            hex_distance(unit.position, e.position)
            for e in enemies
        ]

        return {
            "enemy_count": len(enemies),
            "nearest_enemy_distance": min(distances),
        }