# assault_sim/engine/activation_manager.py

class ActivationManager:
    """
    Deterministic activation scheduler by side.

    Guarantees:
    - No None active_unit
    - Explicit unit selection
    - Turn-based alternation
    """

    def __init__(self, state):
        self.state = state
        self.turn = state.turn if hasattr(state, "turn") else 1

        # Alternating sides (can expand later)
        self.sides = ["US", "GE"]
        self.side_index = 0  # who acts next

    # -------------------------------------------------

    def next_activation(self):
        """
        Returns:
            (side, unit) or (None, None) if nobody can act
        """
        for _ in range(len(self.sides)):
            side = self.sides[self.side_index]

            unit = self._find_activable_unit(side)

            # advance side for next call (important!)
            self.side_index = (self.side_index + 1) % len(self.sides)

            if unit is not None:
                return side, unit

        # nobody can act → caller must end turn
        return None, None

    # -------------------------------------------------

    def _find_activable_unit(self, side):
        """
        Find first valid unit for a side.
        """
        for u in self.state.units:
            if not u.alive:
                continue

            if u.side != side:
                continue

            if self._can_act(u):
                return u

        return None

    # -------------------------------------------------

    def _can_act(self, unit):
        """
        Replace runtime._can_unit_act safely.
        """
        if hasattr(unit, "is_suppressed") and unit.is_suppressed():
            return False

        if hasattr(unit, "is_in_fallback") and unit.is_in_fallback():
            return False

        return True