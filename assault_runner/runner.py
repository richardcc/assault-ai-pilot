"""
Runner: neutral execution of a full game.

Responsibilities (current stage):
- Produce a sequence of GameState objects
- Each GameState contains all UnitState instances
- Build a Replay consumable by the viewer

Does NOT:
- Render anything
- Train agents
- Apply real engine rules (yet)
"""

from dataclasses import dataclass
from typing import List

from assault_runner.replay import Replay


# =========================
# GAME STATE STRUCTURES
# =========================

@dataclass(frozen=True)
class UnitState:
    """
    Immutable representation of a unit on the board.
    """
    id: str
    counter_id: str
    hex: str


@dataclass(frozen=True)
class GameState:
    """
    Immutable snapshot of the board at a given step.
    """
    units: List[UnitState]


# =========================
# RUNNER
# =========================

class Runner:
    """
    Minimal runner producing a Replay with multiple units.
    """

    def run(self, hex_path: List[str]) -> Replay:
        """
        Generate a simple replay where one unit moves
        across the hex_path and others remain static.
        """
        states: List[GameState] = []

        for step_index, moving_hex in enumerate(hex_path):
            units = [
                UnitState(
                    id="US1",
                    counter_id="US_RIFLES_43",
                    hex=moving_hex,
                ),
                UnitState(
                    id="US2",
                    counter_id="US_RANGERS_43",
                    hex="D11",
                ),
                UnitState(
                    id="GE1",
                    counter_id="GE_RIFLES_43",
                    hex="C10",
                ),
                UnitState(
                    id="GE2",
                    counter_id="GE_FJ_RIFLES_43",
                    hex="B10",
                ),
            ]

            states.append(GameState(units=units))

        initial_state = states[0]
        final_state = states[-1]

        return Replay(
            initial_state=initial_state,
            states=states,
            final_state=final_state,
        )
