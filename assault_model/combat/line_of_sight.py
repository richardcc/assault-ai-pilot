# assault_model/combat/line_of_sight.py
from enum import Enum


class LineOfSight(Enum):
    CLEAR = "CLEAR"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
