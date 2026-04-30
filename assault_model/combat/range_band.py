# assault_model/combat/range_band.py
from enum import Enum


class RangeBand(Enum):
    CLOSE = "CLOSE"
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"