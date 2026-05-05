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
    - If unit is unknown (e.g., early events), falls back gracefully.
    """

    def __init__(self):
        self._units = []

    # -------------------------------------------------
    # STATE UPDATE
    # -------------------------------------------------
    def update_units(self, units: list):
        """
        Update the current unit list (typically on MAP_STATE).

        Expected unit attributes:
        - unit_id: str
        - side: str ("GE" / "US")
        - hp: int
        """
        self._units = units or []

    # -------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------
    def label(self, unit_id: str) -> str:
        """
        Return the formatted label for a unit.

        Format:
        - 🔵GE_1 ❤️❤️❤️
        - 🔴US_2 ❤️❤️
        """

        for u in self._units:
            if u.unit_id == unit_id:
                icon = "🔵" if u.side == "GE" else "🔴"
                hp = max(0, getattr(u, "hp", 0))
                hearts = "❤️" * hp
                return f"{icon}{u.unit_id} {hearts}".strip()

        # Fallback (unit not yet known to the formatter)
        return unit_id