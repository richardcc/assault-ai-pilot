# assault_model/combat/reaction_trigger.py
from enum import Enum


class ReactionTrigger(Enum):
    ENEMY_MOVES_IN_LOS = "ENEMY_MOVES_IN_LOS"
    ENEMY_LEAVES_HEX = "ENEMY_LEAVES_HEX"
    ENEMY_ENTERS_HEX = "ENEMY_ENTERS_HEX"
    ENEMY_ASSAULTS = "ENEMY_ASSAULTS"