from assault_model.combat.attack_profile import AttackProfile
from assault_model.combat.defense_profile import DefenseProfile
from assault_model.combat.combat_band import CombatBand
from assault_model.combat.modifier import DiceModifier
from assault_model.combat.line_of_sight import LineOfSight
from assault_model.combat.flank import Flank

from assault_model.combat.range_logic import distance_to_range_band
from assault_model.combat.range_band import RangeBand
from assault_model.units.unit_class_mapping import CLASSIFICATION_TO_UNIT_CLASS


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

    # =================================================
    # RANGED COMBAT FACTORY
    # =================================================
    @classmethod
    def from_ranged_attack(
        cls,
        *,
        attacker,
        target,
        distance: int,
        los: LineOfSight,
        flank: Flank = Flank.FRONT,
        modifiers: list[DiceModifier] | None = None,
    ) -> "CombatActionContext":
        """
        Build a CombatActionContext for DIRECT RANGED FIRE.

        Responsibilities (domain logic):
        - Convert distance to RangeBand
        - Select correct attack table based on target class
        - Build AttackProfile and DefenseProfile from unit cards
        """

        # Distance -> semantic combat band
        band: RangeBand = distance_to_range_band(distance)

        # Target combat class (INFANTRY / VEHICLE)
        target_class_name = CLASSIFICATION_TO_UNIT_CLASS[
            target.unit_type.classification
        ].name

        # Build attack profile from attacker unit card
        attack_profile = AttackProfile(
            attacker.unit_type.attack[target_class_name]
        )

        # Build defense profile from target unit card
        defense_profile = DefenseProfile(
            target.unit_type.base_defense
        )

        return cls(
            attack=attack_profile,
            defense=defense_profile,
            band=band,
            los=los,
            flank=flank,
            modifiers=modifiers or [],
        )