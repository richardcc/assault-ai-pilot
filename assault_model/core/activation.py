from typing import List, Optional
from assault_model.units.unit_instance import UnitInstance


class ActivationState:
    """
    Handles unit activation within a turn.
    Exactly one unit may be active at any given time.
    """

    def __init__(self, units: List[UnitInstance]):
        self.remaining: List[UnitInstance] = list(units)
        self.activated: List[UnitInstance] = []
        self.active_unit: Optional[UnitInstance] = None

    def next_unit(self) -> Optional[UnitInstance]:
        """
        Activates the next unit in the remaining list.
        Returns the active unit, or None if no units remain.
        """
        if not self.remaining:
            self.active_unit = None
            return None

        unit = self.remaining.pop(0)
        self.activated.append(unit)
        self.active_unit = unit
        return unit

    def reset(self, units: List[UnitInstance]) -> None:
        """
        Resets activation state for a new turn.
        """
        self.remaining = list(units)
        self.activated = []
        self.active_unit = None