from enum import Enum


class MovementOutcome(Enum):
    """
    Semantic result of a movement path.
    """
    END_IN_EMPTY_HEX = "END_IN_EMPTY_HEX"
    END_IN_ENEMY_HEX = "END_IN_ENEMY_HEX"
    END_IN_FRIENDLY_VEHICLE = "END_IN_FRIENDLY_VEHICLE"