from assault_model.rules.movement_path import MovementPath
from assault_model.rules.movement_outcome import MovementOutcome
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_distance
from assault_model.map.hex_direction import HexDirection


class MovementRules:
    """
    Computes legal movement paths.

    Version 1:
    - Single-hex movement only
    - No terrain cost
    - No ZOC
    """

    @staticmethod
    def get_legal_paths(game_state, unit):
        """
        Returns a list of MovementPath.
        Each path represents ONE complete movement action.
        """
        paths: list[MovementPath] = []

        # ✅ unit.position is a HexCoord
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
            if game_state.game_map.get_hex(target_q, target_r) is None:
                continue

            dest_hex = HexCoord(target_q, target_r)

            occupant = next(
                (u for u in game_state.units if u.position == dest_hex),
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
            # FRIENDLY INFANTRY → illegal
            # -------------------------
            # Do nothing (no path added)

        return paths
