# assault_sim/rl/tactical_options.py

from enum import Enum


class TacticalOption(Enum):
    """
    High-level tactical intentions.

    These are the ONLY actions the RL policy is allowed to choose.
    They are semantic, human-level decisions.
    """

    ADVANCE = 0     # Move towards combat / objective
    FLANK = 1       # Seek a flank or rear position
    ATTACK = 2      # Engage the enemy directly
    HOLD = 3        # Hold position / wait
    RETREAT = 4     # Disengage or reposition defensively