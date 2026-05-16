from assault_model.combat.unit_class import UnitClass

CLASSIFICATION_TO_UNIT_CLASS = {
    "STANDARD_INFANTRY": UnitClass.INFANTRY,
    "SPECIALIZED_INFANTRY": UnitClass.INFANTRY,
    "ELITE_INFANTRY": UnitClass.INFANTRY,

    # ✅ NEW (CRITICAL)
    "INDIRECT_FIRE_UNIT": UnitClass.INFANTRY,

    "LIGHT_VEHICLE": UnitClass.VEHICLE,
    "ARMORED_VEHICLE": UnitClass.VEHICLE,
}
