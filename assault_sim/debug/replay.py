class Replay:
    """
    Minimal replay container.
    Pure data object.
    No logic, no IO, no dependencies.
    """

    def __init__(self):
        # General context of the replay
        self.meta = {}

        # State before Turn 1
        self.initial_state = {}

        # List of turns:
        # [{ "turn": int, "events": [...] }]
        self.turns = []

    def to_dict(self):
        """
        Convert replay to plain dict for serialization.
        """
        return {
            "meta": self.meta,
            "initial_state": self.initial_state,
            "turns": self.turns,
        }