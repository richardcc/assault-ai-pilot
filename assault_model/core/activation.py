from typing import List, Optional
from assault_model.units.unit_instance import UnitInstance


class ActivationState:
    """
    Handles unit activation within a turn.
    """

    def __init__(self, units: List[UnitInstance]):
        self.remaining: List[UnitInstance] = list(units)
        self.activated: List[UnitInstance] = []
        self.active_unit: Optional[UnitInstance] = None

    # -------------------------------------------------
    # NEXT UNIT
    # -------------------------------------------------
    def next_unit(self) -> Optional[UnitInstance]:

        while self.remaining:

            unit = self.remaining.pop(0)

            if unit in self.activated:
                continue

            self.active_unit = unit
            return unit

        self.active_unit = None
        return None


    # -------------------------------------------------
    # CONSUME ACTIVATION
    # -------------------------------------------------
    def consume(self, unit: UnitInstance) -> None:

        if unit not in self.activated:
            self.activated.append(unit)

        # ✅ limpiar active_unit
        if self.active_unit == unit:
            self.active_unit = None

    # -------------------------------------------------
    # RESET TURN
    # -------------------------------------------------
    def reset(self, units: List[UnitInstance]) -> None:

        alive = [u for u in units if u.alive]

        # group by side
        by_side = {}
        for u in alive:
            by_side.setdefault(u.side, []).append(u)

        # ✅ ensure deterministic order
        sides = sorted(by_side.keys())

        self.remaining = []
        index = 0

        while True:
            added = False

            for side in sides:
                side_units = by_side[side]
                if index < len(side_units):
                    unit = side_units[index]
                    self.remaining.append(unit)
                    added = True

            if not added:
                break

            index += 1
        self.activated = []
        self.active_unit = None
