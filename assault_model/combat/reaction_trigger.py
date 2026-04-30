from enum import Enum


class ReactionTrigger(Enum):
    """
    Semantic triggers that may open a reaction window.
    Conditions (LOS, range, etc.) are evaluated elsewhere.
    """

    ENEMY_MOVES_IN_LOS = "ENEMY_MOVES_IN_LOS"
    ENEMY_LEAVES_HEX = "ENEMY_LEAVES_HEX"
    ENEMY_ENTERS_HEX = "ENEMY_ENTERS_HEX"
    ENEMY_ASSAULTS = "ENEMY_ASSAULTS"