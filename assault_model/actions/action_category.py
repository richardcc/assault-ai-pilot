# assault_model/actions/action_category.py
from enum import Enum


class ActionCategory(Enum):
    MOVEMENT = "MOVEMENT"
    COMBAT = "COMBAT"
    STATUS = "STATUS"
