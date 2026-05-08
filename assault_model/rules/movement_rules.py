from assault_model.rules.movement_path import MovementPath
from assault_model.rules.movement_outcome import MovementOutcome
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_direction import HexDirection

from assault_model.rules.movement_terrain_rules import MovementTerrainRules


class MovementRules:
    """
    Computes legal movement paths.

    Version 1:
    - Single-hex movement only
    - No terrain cost
    - No ZOC

    Rules: TM-R02, TM-R03
    """

    @staticmethod
    def get_legal_paths(game_state, unit):
        """
        Returns a list of MovementPath.
        Each path represents ONE complete movement action.

        Rules: TM-R02, TM-R03
        """
        paths: list[MovementPath] = []

        pos: HexCoord = unit.position
        q = pos.q
        r = pos.r

        for direction in HexDirection:
            dq, dr = direction.value
            target_q = q + dq
            target_r = r + dr

            # -------------------------
            # Hex outside map
            # -------------------------
            hex_tile = game_state.game_map.get_hex(target_q, target_r)
            if hex_tile is None:
                continue

            # -------------------------
            # Destination legality (terrain, structural rules)
            # -------------------------
            # Rules: TM-R02, TM-R03, TM-R09
            if not MovementTerrainRules.can_enter_hex(unit, hex_tile):
                continue

            dest_hex = HexCoord(target_q, target_r)

            # -------------------------
            # Occupancy check
            # -------------------------
            occupant = next(
                (
                    u
                    for u in game_state.units
                    if u.alive and u.position == dest_hex
                ),
                None,
            )

            # -------------------------
            # EMPTY HEX → normal move
            # -------------------------
            if occupant is None:
                paths.append(
                    MovementPath(
                        path=[dest_hex],
                        outcome=MovementOutcome.END_IN_EMPTY_HEX,
                    )
                )
                continue

            # -------------------------
            # ENEMY → close combat
            # -------------------------
            if occupant.side != unit.side:
                paths.append(
                    MovementPath(
                        path=[dest_hex],
                        outcome=MovementOutcome.END_IN_ENEMY_HEX,
                        target_unit_id=occupant.unit_id,
                    )
                )
                continue

            # -------------------------
            # FRIENDLY VEHICLE → embark
            # -------------------------
            if getattr(occupant, "is_vehicle", False):
                paths.append(
                    MovementPath(
                        path=[dest_hex],
                        outcome=MovementOutcome.END_IN_FRIENDLY_VEHICLE,
                        target_unit_id=occupant.unit_id,
                    )
                )
                continue

            # -------------------------
            # FRIENDLY INFANTRY → illegal destination
            # -------------------------
            # Rule: TM-R09
            # No path added

        return paths