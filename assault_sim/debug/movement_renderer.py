# assault_sim/debug/movement_renderer.py

class MovementRenderer:
    """
    MovementRenderer

    Responsibility:
    - Render UNIT_MOVED domain events.
    - Attach movement INLINE to the corresponding action line.
    - Fall back to a standalone line only if attachment is impossible.

    Design rules:
    - Presentation only (NO game logic).
    - Reflects exactly what the engine reports.
    """

    def __init__(self, turn_buffer):
        self.turn_buffer = turn_buffer

    # -------------------------------------------------
    # EVENT HANDLER
    # -------------------------------------------------
    def on_unit_moved(self, payload: dict) -> None:
        unit_id = payload.get("unit_id")
        from_hex = payload.get("from")
        to_hex = payload.get("to")

        if not unit_id or not from_hex or not to_hex:
            return

        if from_hex.q == to_hex.q and from_hex.r == to_hex.r:
            return

        arrow = self._arrow(from_hex, to_hex)

        movement_text = (
            f" 🧭 ({from_hex.q},{from_hex.r} → {to_hex.q},{to_hex.r}) {arrow}"
        )

        # -------------------------------------------------
        # Try to attach INLINE to last action line
        # -------------------------------------------------
        attached = self.turn_buffer.append_to_last(
            unit_id,
            movement_text,
        )

        # -------------------------------------------------
        # Fallback (should be rare)
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