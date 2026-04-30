from typing import List, Tuple

from assault_model.map.hex_direction import HexDirection
from assault_model.units.unit_instance import UnitInstance
from assault_model.core.game_state import GameState


class MovementRules:
    @staticmethod
    def can_unit_move(game_state: GameState, unit: UnitInstance) -> bool:
        return game_state.active_unit == unit

    @staticmethod
    def get_legal_moves(
        game_state: GameState,
        unit: UnitInstance,
    ) -> List[Tuple[int, int]]:

        if not MovementRules.can_unit_move(game_state, unit):
            return []

        q, r = unit.position
        legal_moves: List[Tuple[int, int]] = []

        for direction in HexDirection:
            dq, dr = direction.value
            target = (q + dq, r + dr)

            if game_state.game_map.get_hex(*target) is None:
                continue

            if any(u.position == target for u in game_state.units):
                continue

            legal_moves.append(target)

        return legal_moves