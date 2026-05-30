# assault_sim/engine/activation_manager.py

class ActivationManager:
    """
    Deterministic activation scheduler by side.

    Guarantees:
    - No implicit active_unit
    - Explicit unit selection
    - Turn-based alternation
    
    Supports intelligent unit selection via optional selector callback.
    """

    def __init__(self, state, unit_selector=None):
        self.state = state
        self.unit_selector = unit_selector  # ✅ callback para selección inteligente

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
        Find best valid unit for a side respecting blocked units.
        
        If unit_selector callback is provided, use it for intelligent selection.
        Otherwise, fall back to sequential (first valid) selection.
        """
        
        # ✅ Si hay selector inteligente, usarlo
        if self.unit_selector:
            try:
                best_unit = self.unit_selector(side, self.state, self.blocked_units)
                if best_unit is not None and best_unit.unit_id not in self.blocked_units:
                    return best_unit
            except Exception as e:
                print(f"[WARN] Unit selector failed: {e}, falling back to sequential")

        # ✅ Fallback secuencial (primera unidad válida)
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
