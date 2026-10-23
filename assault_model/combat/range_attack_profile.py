from typing import Dict, List
from assault_model.combat.range_band import RangeBand
from assault_model.combat.dice_color import DiceColor


class RangeAttackProfile:
    """
    Defines which attack dice are rolled at each range band.
    """

    def __init__(self, profile: Dict[RangeBand, List[DiceColor]]):
        self.profile = profile

    def dice_for_range(self, band: RangeBand) -> List[DiceColor]:
        """Return attack dice colors for the given range band."""
        return list(self.profile.get(band, []))
