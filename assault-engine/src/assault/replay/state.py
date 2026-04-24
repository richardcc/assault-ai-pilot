from dataclasses import dataclass

@dataclass(frozen=True)
class UnitState:
    unit_id: str
    side: str
    hex: str
    strength: int
    status: str


@dataclass(frozen=True)
class ReplayState:
    turn: int
    units: tuple[UnitState, ...]