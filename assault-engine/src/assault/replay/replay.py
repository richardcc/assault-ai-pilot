class Replay:
    """
    Replay is an ordered container of game snapshots.

    The `states` list may contain:
    - ReplayState instances (world state snapshots)
    - dict-based SYSTEM EVENT snapshots (e.g. END_TURN, END_MATCH)

    This class is intentionally minimal and does not interpret
    the contents of the states.
    """

    def __init__(self, states):
        self.states = states