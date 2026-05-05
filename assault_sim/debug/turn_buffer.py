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

    Design notes:
    - A turn is opened by the first ACTION event of that turn.
    - A turn is explicitly closed when a TURN_END event is received.
    - Once a turn is closed, it must never be reopened.
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
        """
        Fully reset the buffer (used on RESET event).
        """
        self.turn = None
        self._closed_turn = None
        self.lines.clear()

    def close_turn(self):
        """
        Explicitly close the current turn.

        Called when TURN_END is received. This ensures:
        - All accumulated lines are flushed.
        - No further ACTION belonging to this turn
          can reopen the [TURN X] header.
        """
        self.flush()
        self._closed_turn = self.turn
        self.turn = None

    def on_action(self, payload: dict):
        """
        Handle an ACTION event.

        Opens a new turn header if needed and appends the action line.
        """

        turn = payload["turn"]

        # ✅ Do not reopen a turn that has already been closed
        if self._closed_turn == turn:
            return

        # Open a new turn if needed
        if self.turn != turn:
            self.flush()
            self.turn = turn
            print(f"[TURN {turn}]")

        uid = payload["active_unit"]
        action = payload["action"]

        label = self.unit_label(uid)

        self.lines.append(
            f"         {label} -> {action}"
        )

    # -------------------------------------------------
    # LINE MANAGEMENT
    # -------------------------------------------------
    def append_to_last(self, unit_id: str, extra_text: str) -> bool:
        """
        Append extra text to the last line containing the given unit_id.
        Used to attach movement or combat details to an action line.
        """
        for i in range(len(self.lines) - 1, -1, -1):
            if unit_id in self.lines[i]:
                self.lines[i] += extra_text
                return True
        return False

    def add_line(self, line: str):
        """
        Add a standalone line (used for combat blocks, fallback messages, etc.).
        """
        self.lines.append(line)

    def flush(self):
        """
        Print all accumulated lines and clear the buffer.
        """
        for l in self.lines:
            print(l)
        self.lines.clear()

    # -------------------------------------------------
    # UNIT FORMATTING API
    # -------------------------------------------------
    def unit_label(self, unit_id: str) -> str:
        """
        Return a formatted unit label using UnitFormatter.
        Falls back to raw unit_id if formatter is unavailable.
        """
        if self._unit_formatter:
            return self._unit_formatter.label(unit_id)
        return unit_id
