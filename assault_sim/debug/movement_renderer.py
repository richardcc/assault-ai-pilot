# assault_sim/debug/movement_renderer.py

class MovementRenderer:
    """
    MovementRenderer

    Responsibility:
    - Render UNIT_MOVED domain events in a human-readable form.
    - Attach movement details to the corresponding MoveAction line when possible.
    - Fall back to a standalone movement line if attachment is not possible.

    Design rules:
    - Presentation only (NO game logic).
    - Does NOT decide or validate movement.
    - Reflects exactly what the engine reports.
    """

    def __init__(self, turn_buffer):
        """
        Parameters
        ----------
        turn_buffer : TurnBuffer
            Buffer that accumulates and prints per-turn output lines.
        """
        self.turn_buffer = turn_buffer

    # -------------------------------------------------
    # EVENT HANDLER
    # -------------------------------------------------
    def on_unit_moved(self, payload: dict) -> None:
        """
        Handle a UNIT_MOVED event.

        Expected payload:
        {
            "unit_id": str,
            "from": HexCoord,
            "to": HexCoord,
        }
        """

        unit_id = payload.get("unit_id")
        from_hex = payload.get("from")
        to_hex = payload.get("to")

        # Defensive validation
        if not unit_id or not from_hex or not to_hex:
            return

        # Ignore non-movements (engine already filters, this is just safety)
        if from_hex.q == to_hex.q and from_hex.r == to_hex.r:
            return

        arrow = self._arrow(from_hex, to_hex)

        movement_text = (
            f" 🧭 ({from_hex.q},{from_hex.r} → {to_hex.q},{to_hex.r}) {arrow}"
        )

        # -------------------------------------------------
        # Attach movement to the last action line if possible
        # -------------------------------------------------
        attached = self.turn_buffer.append_to_last(
            unit_id,
            movement_text,
        )

        # -------------------------------------------------
        # Fallback: standalone movement line
        # (always use formatted unit label)
        # -------------------------------------------------
        if not attached:
            label = self.turn_buffer.unit_label(unit_id)
            self.turn_buffer.add_line(
                f"         {label}{movement_text}"
            )

    # -------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------
    def _arrow(self, from_hex, to_hex) -> str:
        """
        Return a directional arrow based on axial delta.

        Note:
        - This intentionally supports only the most common directions.
        - Any other delta falls back to a neutral dot (•).
        """

        dq = to_hex.q - from_hex.q
        dr = to_hex.r - from_hex.r

        if dq == 1 and dr == 0:
            return "➡️"
        if dq == -1 and dr == 0:
            return "⬅️"
        if dq == 0 and dr == 1:
            return "⬇️"
        if dq == 0 and dr == -1:
            return "⬆️"

        return "•"