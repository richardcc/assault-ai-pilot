"""
Assault execution on the map.

This module applies the result of an AssaultAction
to the GameState, including unit removal, retreat,
and advance on the hex map.
"""

from typing import Optional, List, Tuple

from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.unit import Unit
from assault.core.actions.assault_action import (
    AssaultAction,
    AssaultOutcome,
    AssaultReport,
)
from assault.core.spatial.zone_of_control import ZoneOfControlService


class AssaultExecutionError(Exception):
    """Raised when an assault cannot be executed on the map."""
    pass


class AssaultExecutor:
    """
    Applies an AssaultAction to the GameState.
    """

    def __init__(
        self,
        state: GameState,
        attacker_id: str,
        defender_id: str,
    ) -> None:
        self.state = state
        self.attacker = state.get_unit(attacker_id)
        self.defender = state.get_unit(defender_id)
        self.zoc = ZoneOfControlService(state)

    def execute(self) -> AssaultReport:
        action = AssaultAction(self.attacker, self.defender)
        report = action.resolve()

        # Store defender original position BEFORE any movement
        defender_original_pos = self.defender.position

        self.apply_outcome(report, defender_original_pos)
        return report

    def apply_outcome(
        self,
        report: AssaultReport,
        defender_original_pos: Tuple[int, int],
    ) -> None:
        """
        Applies the assault outcome to the GameState.
        """
        if report.outcome == AssaultOutcome.DEFENDER_ELIMINATED:
            self.remove_unit(self.defender)
            self.advance_attacker(defender_original_pos)

        elif report.outcome == AssaultOutcome.ATTACKER_ELIMINATED:
            self.remove_unit(self.attacker)

        elif report.outcome == AssaultOutcome.BOTH_ELIMINATED:
            self.remove_unit(self.attacker)
            self.remove_unit(self.defender)

        elif report.outcome == AssaultOutcome.DEFENDER_RETREATS:
            retreat_hex = self.find_retreat_hex(self.defender)
            if retreat_hex is None:
                # No valid retreat → defender eliminated
                self.remove_unit(self.defender)
                self.advance_attacker(defender_original_pos)
            else:
                self.move_unit(self.defender, retreat_hex)
                self.advance_attacker(defender_original_pos)

        elif report.outcome == AssaultOutcome.STALEMATE:
            pass

    # ------------------------------------------------------------------
    # Map operations
    # ------------------------------------------------------------------

    def remove_unit(self, unit: Unit) -> None:
        q, r = unit.position
        hex_ = self.state.hexes[(q, r)]
        hex_.occupant = None
        del self.state.units[unit.unit_id]

    def move_unit(self, unit: Unit, hex_: Hex) -> None:
        old_q, old_r = unit.position
        self.state.hexes[(old_q, old_r)].occupant = None

        unit.position = (hex_.q, hex_.r)
        hex_.occupant = unit.unit_id

    def advance_attacker(self, target_pos: Tuple[int, int]) -> None:
        target_hex = self.state.hexes[target_pos]
        if target_hex.occupant is None:
            self.move_unit(self.attacker, target_hex)

    # ------------------------------------------------------------------
    # Advanced retreat logic (D8-B)
    # ------------------------------------------------------------------

    def _direction_away_from_attacker(
        self,
        attacker_pos: Tuple[int, int],
        defender_pos: Tuple[int, int],
        candidate_pos: Tuple[int, int],
    ) -> int:
        """
        Scores a retreat candidate by distance increase from attacker.
        Higher values are preferred.
        """
        ax, ay = attacker_pos
        dx, dy = defender_pos
        cx, cy = candidate_pos

        current_dist = abs(dx - ax) + abs(dy - ay)
        candidate_dist = abs(cx - ax) + abs(cy - ay)

        return candidate_dist - current_dist

    def find_retreat_hex(self, unit: Unit) -> Optional[Hex]:
        """
        Finds the best valid retreat hex according to advanced retreat rules:

        - Must be adjacent
        - Must be unoccupied
        - Must be passable terrain (movement_cost not excessive)
        - Must NOT be inside enemy ZOC
        - Prefer hexes further away from the attacker
        """
        defender_pos = unit.position
        attacker_pos = self.attacker.position

        candidates: List[Tuple[int, Hex]] = []

        for neighbor in self.get_adjacent_hexes(*defender_pos):

            # Must be unoccupied
            if neighbor.occupant is not None:
                continue

            # Must be passable terrain
            # Convention: very high movement cost means not passable (e.g. WATER = 99)
            if neighbor.terrain.movement_cost >= 99:
                continue

            # Must not retreat into enemy ZOC
            if self.zoc.is_hex_in_enemy_zoc(unit, (neighbor.q, neighbor.r)):
                continue

            score = self._direction_away_from_attacker(
                attacker_pos,
                defender_pos,
                (neighbor.q, neighbor.r),
            )
            candidates.append((score, neighbor))

        if not candidates:
            return None

        # Choose best retreat (max distance from attacker)
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def get_adjacent_hexes(self, q: int, r: int) -> List[Hex]:
        directions = [
            (+1, 0), (-1, 0),
            (0, +1), (0, -1),
            (+1, -1), (-1, +1),
        ]
        neighbors: List[Hex] = []
        for dq, dr in directions:
            coord = (q + dq, r + dr)
            if coord in self.state.hexes:
                neighbors.append(self.state.hexes[coord])
        return neighbors