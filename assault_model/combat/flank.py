# assault_model/combat/flank.py
from enum import Enum


class Flank(Enum):
    FRONT = "FRONT"
    SIDE = "SIDE"
    REAR = "REAR"