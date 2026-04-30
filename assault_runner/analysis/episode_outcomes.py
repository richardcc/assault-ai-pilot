"""
Episode Outcome computation.

Engine-level outcome logic.
Uses abstract sides ("A", "B").
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class EpisodeOutcome:
    """
    Result of a single completed episode.
    """
    winner: str      # "A", "B", or "DRAW"
    vp_A: int
    vp_B: int
    total_turns: int   # REAL number of rounds played

    def to_dict(self) -> Dict:
        return {
            "winner": self.winner,
            "vp_A": self.vp_A,
            "vp_B": self.vp_B,
            "total_turns": self.total_turns,
        }


def compute_episode_outcome(
    game_state,
    total_turns: Optional[int] = None,
) -> EpisodeOutcome:
    """
    Computes the episode outcome from the final GameState.

    CANONICAL RULE ORDER:
    1) Victory by elimination
    2) Victory by VP comparison
    3) Draw if tied

    BACKWARD‑COMPATIBLE CONTRACT:
    - If total_turns is provided: use it (preferred).
    - If not provided: fall back to legacy behaviour.
    """

    # --------------------------------------------------
    # 1) Check victory by elimination (highest priority)
    # --------------------------------------------------
    alive_by_side = {
        side: [u for u in units.values() if u.is_alive()]
        for side, units in game_state.units.items()
    }

    alive_sides = {side for side, units in alive_by_side.items() if units}

    # --------------------------------------------------
    # VP count (always computed for reporting)
    # --------------------------------------------------
    vp_A = sum(1 for o in game_state.vp_owner.values() if o == "A")
    vp_B = sum(1 for o in game_state.vp_owner.values() if o == "B")

    if len(alive_sides) == 1:
        # Exactly one side still has units alive
        winner = next(iter(alive_sides))    # "A" or "B"

    else:
        # --------------------------------------------------
        # 2) No elimination → decide by Victory Points
        # --------------------------------------------------
        if vp_A > vp_B:
            winner = "A"
        elif vp_B > vp_A:
            winner = "B"
        else:
            winner = "DRAW"

    # --------------------------------------------------
    # Backward compatibility for total_turns
    # --------------------------------------------------
    if total_turns is None:
        total_turns = getattr(game_state, "turn", 1)

    return EpisodeOutcome(
        winner=winner,
        vp_A=vp_A,
        vp_B=vp_B,
        total_turns=total_turns,
    )