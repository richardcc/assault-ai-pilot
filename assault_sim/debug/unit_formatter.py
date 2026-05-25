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

        for u in self._units:

            # ✅ soportar dict y objeto
            uid = getattr(u, "unit_id", None) or u.get("unit_id")
            side = getattr(u, "side", None) or u.get("side")

            if uid == unit_id:

                icon = "🔵" if side == "GE" else "🔴"

                hp = self._hp_override.get(
                    unit_id,
                    getattr(u, "hp", None) or u.get("hp", 0)
                )

                hearts = "❤️" * max(0, hp)

                return f"{icon}{uid} {hearts}".strip()

        return unit_id