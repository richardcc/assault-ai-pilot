from assault_model.combat.line_of_sight import check_line_of_sight
from assault_model.combat.spotting import can_spot


def update_spotting(state, terrain_config):

    for unit in state.units:

        if not unit.alive:
            unit.spotted_enemies = set()
            continue

        visible = []

        for other in state.units:

            if other.side == unit.side:
                continue

            if not other.alive:
                continue

            # ✅ LOS correcto
            los = check_line_of_sight(
                unit,
                other,
                state.game_map,
                terrain_config
            )

            # ✅ spotting coherente
            if can_spot(unit, other, los, state.game_map, terrain_config):
                visible.append(other.unit_id)

        unit.spotted_enemies = set(visible)
