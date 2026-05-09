import copy
from assault_sim.debug.replay import Replay

class ReplayObserver:
    def __init__(self):
        self.replay = Replay()
        self.replay.replay_version = 2  # ✅ FIX
        self._current_turn = None
        self._current_events = []

    def __call__(self, event: dict):
        event_type = event.get("type")
        payload = event.get("payload", {})

        # ---------------- RESET ----------------
        if event_type == "RESET":
            self._current_turn = None
            self._current_events = []
            self.replay.turns.clear()

        # ---------------- ACTION ----------------
        elif event_type == "ACTION":
            turn = payload.get("turn")
            if self._current_turn != turn:
                self._flush_turn()
                self._current_turn = turn
            self._current_events.append(copy.deepcopy(event))

        # ---------------- ACTION EFFECT ----------------
        elif event_type == "ACTION_EFFECT":
            self._current_events.append(copy.deepcopy(event))

        # ---------------- UNIT MOVED ----------------
        elif event_type == "UNIT_MOVED":
            self._current_events.append(copy.deepcopy(event))

        # ---------------- TURN END ----------------
        elif event_type == "TURN_END":
            self._flush_turn()
            self._current_turn = None

        # ---------------- MATCH END ----------------
        elif event_type == "MATCH_END":
            self._flush_turn()

    def _flush_turn(self):
        """
        Store buffered events as a completed turn.
        """
        if self._current_turn is None or not self._current_events:
            return

        self.replay.turns.append({
            "turn": self._current_turn,
            "events": list(self._current_events),
        })

        self._current_events.clear()
