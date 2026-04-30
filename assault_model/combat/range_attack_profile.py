# assault_model/combat/range_attack_profile.py

from typing import Dict, List
from assault_model.combat.range_band import RangeBand
from assault_model.combat.attack_die import AttackDie
from assault_model.combat.dice_color import DiceColor


class RangeAttackProfile:
    """
    Defines which attack dice are rolled at each range band.
    """

    def __init__(self, profile: Dict[RangeBand, List[DiceColor]]):
        """
        profile:
            Dict mapping RangeBand -> list of DiceColor
        """
        self.profile = profile

    def dice_for_range(self, band: RangeBand) -> List[AttackDie]:
        """
        Return AttackDie objects for the given range band.
        """
        colors = self.profile.get(band, [])
        return [AttackDie(color=c) for c in colors]