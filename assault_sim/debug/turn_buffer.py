# assault_sim/debug/turn_buffer.py

from assault_sim.debug.unit_formatter import UnitFormatter


class TurnBuffer:
    """
    TurnBuffer

    Responsibility:
    - Accumulate per-turn output lines.
    - Ensure consistent formatting of unit identifiers.
    - Attach action details (movement, combat, etc.) to existing lines.
    - Guarantee correct visual ordering of turns.
    """

    def __init__(self, unit_formatter: UnitFormatter | None = None):
        self.turn = None
        self.lines = []

        # Formatter responsible for coloring units and showing HP
        self._unit_formatter = unit_formatter

        # Track the last visually closed turn to prevent reopening
        self._closed_turn = None

    # -------------------------------------------------
    # TURN CONTROL
    # -------------------------------------------------
    def reset(self):
        self.turn = None
        self._closed_turn = None
        self.lines.clear()

    def close_turn(self):
        self.flush()
        self._closed_turn = self.turn
        self.turn = None

    # -------------------------------------------------
    # ACTION EVENT
    # -------------------------------------------------
    def on_action(self, payload: dict):

        turn = payload.get("turn")

        # ✅ Safety: if turn missing, ignore event
        if turn is None:
            return

        # ✅ Do not reopen closed turn
        if self._closed_turn == turn:
            return

        # ✅ Open new turn if needed
        if self.turn != turn:
            self.flush()
            self.turn = turn
            print(f"[TURN {turn}]")

        # ✅ NEW model: unit_id instead of active_unit
        uid = payload.get("unit_id")
        action = payload.get("action", "UNKNOWN")

        # ✅ Handle SYSTEM / None safely
        label = self.unit_label(uid) if uid else "SYSTEM"

        self.lines.append(
            f"         {label} -> {action}"
        )

    # -------------------------------------------------
    # LINE MANAGEMENT
    # -------------------------------------------------
    def append_to_last(self, unit_id: str, extra_text: str) -> bool:
        for i in range(len(self.lines) - 1, -1, -1):
            if unit_id and unit_id in self.lines[i]:
                self.lines[i] += extra_text
                return True
        return False

    def add_line(self, line: str):
        self.lines.append(line)

    def flush(self):
        for l in self.lines:
            print(l)
        self.lines.clear()

    # -------------------------------------------------
    # UNIT FORMATTING API
    # -------------------------------------------------
    def unit_label(self, unit_id: str) -> str:
        if unit_id is None:
            return "SYSTEM"

        if self._unit_formatter:
            return self._unit_formatter.label(unit_id)

        return unit_id