from enum import Enum, auto


class AttackSector(Enum):
    """
    Semantic combat concept.

    Represents the relative sector from which an attack is made
    against the defender.
    """

    FRONT = auto()
    FLANK_LEFT = auto()
    FLANK_RIGHT = auto()
    REAR = auto()