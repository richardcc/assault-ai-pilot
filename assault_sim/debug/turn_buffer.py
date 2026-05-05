# assault_sim/debug/turn_buffer.py

from assault_sim.debug.unit_formatter import UnitFormatter


class TurnBuffer:
    """
    TurnBuffer

    Responsibility:
    - Accumulate per-turn output lines.
    - Ensure consistent formatting of unit identifiers.
    - Attach action details (movement, combat, etc.) to existing lines.
    """

    def __init__(self, unit_formatter: UnitFormatter | None = None):
        self.turn = None
        self.lines = []

        # Formatter responsible for coloring units and showing HP
        self._unit_formatter = unit_formatter

    # -------------------------------------------------
    # TURN CONTROL
    # -------------------------------------------------
    def reset(self):
        self.turn = None
        self.lines.clear()

    def on_action(self, payload: dict):
        turn = payload["turn"]
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
        Append text to the latest line containing the given unit_id.
        """
        for i in range(len(self.lines) - 1, -1, -1):
            if unit_id in self.lines[i]:
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
        """
        Return a formatted unit label using UnitFormatter.
        Falls back to raw unit_id if formatter is unavailable.
        """
        if self._unit_formatter:
            return self._unit_formatter.label(unit_id)
        return unit_id