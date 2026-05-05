from typing import List, Optional
from assault_model.units.unit_instance import UnitInstance


class ActivationState:
    """
    Handles unit activation within a turn.

    Responsibilities:
    - Maintain the ordered list of units remaining to activate.
    - Expose the currently active unit.
    - Select the next unit to activate.
    - Track which units have completed their activation.

    IMPORTANT:
    - Selecting a unit (next_unit) is NOT the same as consuming its activation.
    - Activation consumption must be done explicitly by the engine
      once the unit action has completed.
    """

    def __init__(self, units: List[UnitInstance]):
        self.remaining: List[UnitInstance] = list(units)
        self.activated: List[UnitInstance] = []
        self.active_unit: Optional[UnitInstance] = None

    def next_unit(self) -> Optional[UnitInstance]:
        """
        Selects the next unit to activate.

        Returns:
        - The next active unit, or None if no units remain.

        NOTE:
        - This method ONLY selects the unit.
        - It does NOT consume the activation.
        """
        if not self.remaining:
            self.active_unit = None
            return None

        unit = self.remaining.pop(0)
        self.active_unit = unit
        return unit

    def consume(self, unit: UnitInstance) -> None:
        """
        Marks a unit as having completed its activation.

        This should be called by the game engine AFTER
        the unit has executed its action.
        """
        if unit not in self.activated:
            self.activated.append(unit)

    def reset(self, units: List[UnitInstance]) -> None:
        """
        Resets activation state for a new turn.
        """
        self.remaining = list(units)
        self.activated = []
        self.active_unit = None