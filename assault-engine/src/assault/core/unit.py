from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Tuple, Set


class UnitType(Enum):
    INFANTRY = auto()
    VEHICLE = auto()
    ARTILLERY = auto()


class Experience(Enum):
    RECRUIT = auto()
    REGULAR = auto()
    VETERAN = auto()
    ELITE = auto()


class UnitStatus(Enum):
    """
    Tactical status affecting combat resolution.
    """
    SUPPRESSED = auto()


@dataclass
class Unit:
    """
    Represents a tactical unit on the battlefield.
    """

    unit_id: str
    unit_type: UnitType
    experience: Experience
    strength: int
    max_strength: int
    attack_dice: Tuple[int, int, int, int]
    defense: int
    position: Tuple[int, int]
    statuses: Set[UnitStatus] = field(default_factory=set)

    def is_alive(self) -> bool:
        return self.strength > 0

    def is_half_strength(self) -> bool:
        return self.strength <= self.max_strength // 2

    def is_suppressed(self) -> bool:
        return UnitStatus.SUPPRESSED in self.statuses

    def apply_damage(self, amount: int) -> None:
        self.strength = max(0, self.strength - amount)
