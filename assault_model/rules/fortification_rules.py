from assault_model.combat.attack_sector import AttackSector
from assault_model.map.fortification_config import fortification_config


class FortificationRules:
    """
    Minimal fortification rules for scenario overlays.

    Scope:
    - Defensive bonus dice for ranged defense.
    - Movement cost overrides/penalties by movement type.
    """

    @staticmethod
    def defense_bonus(fort_type: str | None, unit_category: str, sector: AttackSector):
        return fortification_config.get_defense_bonus(
            fort_type=fort_type,
            unit_category=unit_category,
            sector=sector,
        )

    @staticmethod
    def movement_cost_for_fortification(
        fort_type: str | None,
        move_type: str,
        base_cost: int | None,
    ):
        return fortification_config.apply_movement_delta(
            fort_type=fort_type,
            move_type=move_type,
            base_cost=base_cost,
        )
