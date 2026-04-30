from enum import Enum, auto


class UnitStatus(Enum):
    """
    Represents transient tactical states affecting unit behavior.
    """
    SUPPRESSED = auto()


class Experience(Enum):
    """
    Experience level of a unit.

    REGULAR is the default when no marker or formation rule applies.
    """
    REGULAR = auto()
    VETERAN = auto()
    ELITE = auto()


class Unit:
    """
    Core combat unit representation.

    A unit has:
    - strength (hit points / combat effectiveness)
    - position on the map
    - experience level (REGULAR by default)
    - transient statuses (e.g. SUPPRESSED)
    """

    def __init__(
        self,
        *,
        unit_id: str,
        unit_key: str,
        strength: int,
        position: tuple[int, int],
        experience: Experience = Experience.REGULAR,
        statuses: set[UnitStatus] | None = None,
    ):
        self.unit_id = unit_id
        self.unit_key = unit_key
        self.strength = strength
        self.position = position
        self.experience = experience
        self.statuses = statuses or set()

    # --------------------------------------------------
    # Core state checks
    # --------------------------------------------------
    def is_alive(self) -> bool:
        return self.strength > 0

    def is_half_strength(self) -> bool:
        return self.strength <= 1

    def is_suppressed(self) -> bool:
        return UnitStatus.SUPPRESSED in self.statuses

    # --------------------------------------------------
    # Damage & status handling
    # --------------------------------------------------
    def apply_damage(self, hits: int) -> None:
        """
        Applies combat damage to the unit.

        Damage is strictly bounded at zero.
        """
        if hits <= 0:
            return
        self.strength = max(0, self.strength - hits)

    # --------------------------------------------------
    # Representation helpers
    # --------------------------------------------------
    def to_dict(self) -> dict:
        """
        Serializes unit state for replay snapshots.
        """
        return {
            "unit_id": self.unit_id,
            "unit_key": self.unit_key,
            "strength": self.strength,
            "position": list(self.position),
            "experience": self.experience.name,
            "statuses": [s.name for s in self.statuses],
        }