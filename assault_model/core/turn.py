# assault_model/core/turn.py

from enum import Enum


class TurnPhase(Enum):
    START = "START"
    ACTION = "ACTION"
    END = "END"


class TurnState:
    def __init__(self, turn_number: int = 1, phase: TurnPhase = TurnPhase.START):
        self.turn_number = turn_number
        self.phase = phase

    def advance_turn(self) -> None:
        """
        Advances to the next turn and resets the phase to START.
        """
        self.turn_number += 1
        self.phase = TurnPhase.START