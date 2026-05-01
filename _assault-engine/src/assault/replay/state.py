from dataclasses import dataclass


@dataclass(frozen=True)
class UnitState:
    """
    Immutable snapshot of a single unit at a given moment in time.

    Notes:
    - Represents factual game state only
    - Does NOT represent actions or events
    - Used inside ReplayState for board reconstruction
    """
    unit_id: str
    unit_key: str
    side: str
    position: tuple[int, int]
    strength: int
    experience: str          # "REGULAR", "VETERAN", "ELITE"
    statuses: tuple[str, ...]


@dataclass(frozen=True)
class ReplayState:
    """
    Immutable snapshot of the complete board state at a given turn.

    Semantics:
    - Represents the world AFTER a full turn has completed
    - Contains no information about decisions, actions or events
    - Structural events (END_TURN, END_MATCH) are NOT stored here
      and belong to the replay event stream instead

    This class is intentionally minimal and factual.
    """
    turn: int
    units: tuple[UnitState, ...]