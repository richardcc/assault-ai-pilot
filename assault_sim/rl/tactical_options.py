# assault_sim/rl/tactical_options.py

from enum import Enum


class TacticalOption(Enum):
    """
    High-level tactical intentions.

    These are the ONLY actions the RL policy is allowed to choose.
    They are semantic, human-level decisions.

    IMPORTANT:
    - These options define the HRL action space.
    - They MUST remain stable across time for replay + explanation + RAG.
    """

    ADVANCE = 0     # Move towards combat / objective
    FLANK = 1       # Seek a flank or rear position
    ATTACK = 2      # Engage the enemy directly
    HOLD = 3        # Hold position / wait
    RETREAT = 4     # Disengage or reposition defensively

    # -------------------------------------------------
    # Human-readable canonical description
    # -------------------------------------------------
    def description(self) -> str:
        """
        Canonical human-readable explanation fragment.

        This text is safe to use in:
        - UI
        - Logs
        - Replay explanation
        - RAG prompts

        DO NOT change lightly once replays exist.
        """
        return {
            TacticalOption.ADVANCE: "advance towards the objective",
            TacticalOption.FLANK: "attempt to outflank the enemy",
            TacticalOption.ATTACK: "engage the enemy directly",
            TacticalOption.HOLD: "hold the current position",
            TacticalOption.RETREAT: "disengage and reposition defensively",
        }[self]

    # -------------------------------------------------
    # Tactical category (for structured explanation)
    # -------------------------------------------------
    def category(self) -> str:
        """
        High-level tactical category.

        Useful for:
        - Explanation grouping
        - Doctrine comparison
        - RAG conditioning
        """
        return {
            TacticalOption.ADVANCE: "MANEUVER",
            TacticalOption.FLANK: "MANEUVER",
            TacticalOption.ATTACK: "ENGAGEMENT",
            TacticalOption.HOLD: "DEFENSIVE",
            TacticalOption.RETREAT: "DEFENSIVE",
        }[self]