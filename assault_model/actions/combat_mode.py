# assault_model/actions/combat_mode.py
from enum import Enum


class CombatMode(Enum):
    RANGED_DIRECT = "RANGED_DIRECT"
    RANGED_INDIRECT = "RANGED_INDIRECT"
    SMOKE = "SMOKE"
    ASSAULT = "ASSAULT"
    EXPLOSIVE_CHARGE = "EXPLOSIVE_CHARGE"

