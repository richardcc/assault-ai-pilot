from collections import deque
from typing import Dict, List, Iterable, Optional

from assault.core.unit import Unit


class ActivationController:
    """
    Controls unit activations according to the Assault rulebook.

    CONTRACT:
    - NEVER decides when a match ends.
    - ONLY manages which alive unit may activate.
    - When a new round starts, ONLY eligible units are reactivated.
    """

    def __init__(
        self,
        *,
        units_by_side: Dict[str, Dict[str, Unit]],
        starting_side: Optional[str] = None,
    ):
        if not units_by_side:
            raise ValueError("ActivationController requires at least one side")

        self.units_by_side = units_by_side
        self.sides: List[str] = list(units_by_side.keys())

        if starting_side is None:
            starting_side = self.sides[0]

        if starting_side not in self.sides:
            raise ValueError(f"Invalid starting side: {starting_side}")

        self.starting_side = starting_side
        self.current_side = starting_side
        self.round_number = 1

        # Units that have NOT yet activated this round
        self._pending: Dict[str, deque[Unit]] = {}

        # Units that already activated this round
        self._activated: Dict[str, List[Unit]] = {}

        self._initialize_round_state()

    # --------------------------------------------------
    # Round lifecycle
    # --------------------------------------------------

    def _initialize_round_state(self) -> None:
        """
        Rebuilds round activation state.

        IMPORTANT:
        - Re-adds ONLY units that are alive AND eligible to act.
        """
        self._pending.clear()
        self._activated.clear()

        for side, units in self.units_by_side.items():
            eligible_units = [
                u for u in units.values()
                if self._is_unit_eligible(u)
            ]
            self._pending[side] = deque(eligible_units)
            self._activated[side] = []

        self.current_side = self.starting_side

    def start_next_round(self) -> None:
        """
        Starts a new round.

        NOTE:
        - End-of-match logic does NOT live here.
        - This ALWAYS rebuilds the activation state.
        """
        self.round_number += 1
        self.current_side = self._other_side(self.starting_side)
        self.starting_side = self.current_side

        # ✅ RECUPERACIÓN DE SUPRESIÓN
        self._recover_suppression()

        self._initialize_round_state()

    # --------------------------------------------------
    # Activation logic
    # --------------------------------------------------

    def next_unit_to_activate(self) -> Optional[Unit]:
        """
        Returns the next unit to activate WITHOUT mutating state.

        Returns None if no eligible units remain.
        """
        if not self.has_units_available():
            return None

        # Try current side first
        unit = self._peek_next_unit(self.current_side)
        if unit:
            return unit

        # Try the other side
        other = self._other_side(self.current_side)
        unit = self._peek_next_unit(other)
        if unit:
            self.current_side = other
            return unit

        return None

    def mark_activated(self, unit: Unit) -> None:
        """
        Marks a unit as having acted this round.
        """
        side = self._find_unit_side(unit)
        if side is None:
            return

        pending = self._pending.get(side)
        if pending:
            self._pending[side] = deque(
                u for u in pending if u.unit_id != unit.unit_id
            )

        self._activated[side].append(unit)

        # Switch turn if the opposing side still has pending units
        other = self._other_side(self.current_side)
        if any(u.is_alive() for u in self._pending.get(other, [])):
            self.current_side = other

    # --------------------------------------------------
    # State checks
    # --------------------------------------------------

    def has_units_available(self) -> bool:
        for pending in self._pending.values():
            for unit in pending:
                if unit.is_alive():
                    return True
        return False

    def is_round_finished(self) -> bool:
        for pending in self._pending.values():
            if pending:
                return False
        return True

    def iter_alive_units(self) -> Iterable[Unit]:
        for units in self.units_by_side.values():
            for unit in units.values():
                if unit.is_alive():
                    yield unit

    # --------------------------------------------------
    # Eligibility & recovery rules
    # --------------------------------------------------

    def _is_unit_eligible(self, unit: Unit) -> bool:
        """
        Defines whether a unit may act at the start of a round.

        CURRENT RULE:
        - Unit must be alive
        - Unit must NOT be suppressed
        """
        if not unit.is_alive():
            return False

        if "suppressed" in unit.statuses:
            return False

        return True

    def _recover_suppression(self) -> None:
        """
        Clears suppression from all surviving units at round start.
        """
        for unit in self.iter_alive_units():
            if "suppressed" in unit.statuses:
                unit.statuses.remove("suppressed")

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _peek_next_unit(self, side: str) -> Optional[Unit]:
        pending = self._pending.get(side)
        if not pending:
            return None

        for unit in pending:
            if unit.is_alive():
                return unit

        return None

    def _other_side(self, side: str) -> str:
        for s in self.sides:
            if s != side:
                return s
        raise RuntimeError("Only one side present")

    def _find_unit_side(self, unit: Unit) -> Optional[str]:
        for side, units in self.units_by_side.items():
            if unit.unit_id in units:
                return side
        return None