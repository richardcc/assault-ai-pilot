from assault_model.combat.attack_profile import AttackProfile
from assault_model.combat.defense_profile import DefenseProfile
from assault_model.combat.combat_band import CombatBand
from assault_model.combat.modifier import DiceModifier
from assault_model.combat.line_of_sight import LineOfSight
from assault_model.combat.flank import Flank


class CombatActionContext:
    def __init__(
        self,
        attack: AttackProfile,
        defense: DefenseProfile,
        band: CombatBand,
        los: LineOfSight,
        flank: Flank,
        modifiers: list[DiceModifier],
    ):
        self.attack = attack
        self.defense = defense
        self.band = band
        self.los = los
        self.flank = flank
        self.modifiers = modifiers