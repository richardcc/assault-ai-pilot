# assault_model/combat/critical_effect.py
from enum import Enum


class CriticalEffect(Enum):
    ELIMINATED = "ELIMINATED"
    DOUBLE_DAMAGE = "DOUBLE_DAMAGE"
    SUPPRESSED = "SUPPRESSED"
    RETREAT = "RETREAT"
    DAMAGED = "DAMAGED"
    NO_EFFECT = "NO_EFFECT"
``