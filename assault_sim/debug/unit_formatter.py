# assault_sim/debug/unit_formatter.py

class UnitFormatter:
    """
    UnitFormatter

    Responsibility:
    - Render a unit consistently everywhere in the console output.
    - Apply side color (🔵 GE / 🔴 US).
    - Append hearts (❤️) representing current HP.

    Design rules:
    - Presentation-only (NO game logic).
    - Reads unit state from the current unit list (GameState snapshot).
    - Supports temporary HP overrides for accurate per-round combat rendering.
    """

    def __init__(self):
        self._units = []
        self._hp_override = {}  # ✅ temporary visual overrides

    # -------------------------------------------------
    # STATE UPDATE
    # -------------------------------------------------
    def update_units(self, units: list):
        """
        Update the current unit list (typically on MAP_STATE).

        This resets any temporary HP overrides.
        """
        self._units = units or []
        self._hp_override.clear()

    # -------------------------------------------------
    # HP OVERRIDE (VISUAL ONLY)
    # -------------------------------------------------
    def override_hp(self, unit_id: str, hp: int):
        """
        Temporarily override HP displayed for a unit.
        Used during combat rounds ONLY.
        """
        self._hp_override[unit_id] = max(0, hp)

    # -------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------
    def label(self, unit_id: str) -> str:
        """
        Return the formatted label for a unit.

        Examples:
        - 🔵GE_1 ❤️❤️
        - 🔴US_2 ❤️
        """

        for u in self._units:
            if u.unit_id == unit_id:
                icon = "🔵" if u.side == "GE" else "🔴"

                # ✅ Use override if present, otherwise real unit.hp
                hp = self._hp_override.get(
                    unit_id,
                    getattr(u, "hp", 0)
                )

                hearts = "❤️" * max(0, hp)
                return f"{icon}{u.unit_id} {hearts}".strip()

        # Fallback if unit is unknown
        return unit_id