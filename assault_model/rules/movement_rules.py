from assault_model.rules.movement_path import MovementPath
from assault_model.rules.movement_outcome import MovementOutcome
from assault_model.map.hex_coord import HexCoord

from assault_model.rules.movement_terrain_rules import MovementTerrainRules


class MovementRules:

    @staticmethod
    def get_legal_paths(game_state, unit):

        paths: list[MovementPath] = []

        pos: HexCoord = unit.position
        q = pos.q
        r = pos.r

        # ✅ FIX: vecinos correctos según tu grid (odd-r)
        if r % 2 == 0:
            neighbors = [
                (-1,  0),
                (+1,  0),
                ( 0, -1),
                ( 0, +1),
                (-1, -1),
                (-1, +1),
            ]
        else:
            neighbors = [
                (-1,  0),
                (+1,  0),
                ( 0, -1),
                ( 0, +1),
                (+1, -1),
                (+1, +1),
            ]

        for dq, dr in neighbors:

            target_q = q + dq
            target_r = r + dr

            hex_tile = game_state.game_map.get_hex(target_q, target_r)
            if hex_tile is None:
                continue

            if not MovementTerrainRules.can_enter_hex(unit, hex_tile):
                continue

            dest_hex = HexCoord(target_q, target_r)

            occupant = next(
                (
                    u
                    for u in game_state.units
                    if u.alive and u.position == dest_hex
                ),
                None,
            )

            if occupant is None:
                paths.append(
                    MovementPath(
                        path=[dest_hex],
                        outcome=MovementOutcome.END_IN_EMPTY_HEX,
                    )
                )
                continue

            if occupant.side != unit.side:
                paths.append(
                    MovementPath(
                        path=[dest_hex],
                        outcome=MovementOutcome.END_IN_ENEMY_HEX,
                        target_unit_id=occupant.unit_id,
                    )
                )
                continue

            if getattr(occupant, "is_vehicle", False):
                paths.append(
                    MovementPath(
                        path=[dest_hex],
                        outcome=MovementOutcome.END_IN_FRIENDLY_VEHICLE,
                        target_unit_id=occupant.unit_id,
                    )
                )
                continue

        return paths