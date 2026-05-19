# assault_sim/engine/activation_manager.py

class ActivationManager:
    """
    Deterministic activation scheduler by side.

    Guarantees:
    - No implicit active_unit
    - Explicit unit selection
    - Turn-based alternation
    """

    def __init__(self, state):
        self.state = state

        # ✅ dinámico desde GameState
        self.sides = list(self._extract_sides())

        self.side_index = 0
        self.blocked_units = set()  # ✅ clave para evitar repetir unidad

    # -------------------------------------------------

    def _extract_sides(self):
        """
        Extract unique sides dynamically.
        """
        return sorted({u.side for u in self.state.units if u.alive})

    # -------------------------------------------------


    def next_activation(self):
        """
        Returns:
            (side, unit) or (None, None)
        """

        # ✅ candidatos globales
        candidates = [
            u for u in self.state.units
            if u.alive
            and self._can_act(u)
            and u.unit_id not in self.blocked_units
        ]

        if not candidates:
            return None, None  # ✅ turno terminado real

        # ✅ intentar más veces (clave)
        attempts = 0
        max_attempts = len(self.sides) * 2  # 🔥 más margen

        while attempts < max_attempts:

            side = self.sides[self.side_index]

            unit = self._find_activable_unit(side)

            self.side_index = (self.side_index + 1) % len(self.sides)

            if unit is not None:
                return side, unit

            attempts += 1

        # ✅ fallback controlado
        u = candidates[0]
        return u.side, u


    # -------------------------------------------------

    def _find_activable_unit(self, side):
        """
        Find first valid unit for a side respecting blocked units.
        """

        for u in self.state.units:

            if not u.alive:
                continue

            if u.side != side:
                continue

            if u.unit_id in self.blocked_units:  # ✅ CRÍTICO
                continue

            if self._can_act(u):
                return u

        return None

    # -------------------------------------------------

    def _can_act(self, unit):
        """
        Safe check equivalent to runtime guard.
        """

        if hasattr(unit, "is_suppressed") and unit.is_suppressed():
            return False

        if hasattr(unit, "is_in_fallback") and unit.is_in_fallback():
            return False

        return True
