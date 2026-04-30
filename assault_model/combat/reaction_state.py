class ReactionState:
    """
    Tracks reaction usage for a unit within a turn.

    Default rules:
    - A unit may perform ONE reaction per turn.
    - Reaction fire consumes activation (handled elsewhere).
    - Command Cards may override these limits.
    """

    def __init__(self, max_reactions: int = 1):
        self.max_reactions = max_reactions
        self.reactions_used = 0

    @property
    def available(self) -> bool:
        return self.reactions_used < self.max_reactions

    def consume(self):
        if not self.available:
            raise RuntimeError("Reaction not available")
        self.reactions_used += 1

    def reset_turn(self):
        self.reactions_used = 0
``