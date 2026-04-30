# assault_model/combat/critical_table.py
from typing import Dict
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.critical_effect import CriticalEffect


CRITICAL_TABLE: Dict[UnitClass, CriticalEffect] = {
    UnitClass.INFANTRY: CriticalEffect.ELIMINATED,
    UnitClass.VEHICLE: CriticalEffect.DAMAGED,
    UnitClass.ARTILLERY: CriticalEffect.SUPPRESSED,
}