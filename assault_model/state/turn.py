# assault_model/core/turn.py
"""
TurnState represents the authoritative turn lifecycle state of the game.

This class does NOT control turn flow.
It only describes the current phase and number.

The turn lifecycle is governed by RuntimeGameState.

Rules:
- Phase transitions are decided by the engine.
- External coordinators must NOT change turn phase directly.
"""

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