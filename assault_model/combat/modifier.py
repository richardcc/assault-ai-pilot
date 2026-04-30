from abc import ABC, abstractmethod
from assault_model.combat.dice_color import DiceColor


class DiceModifier(ABC):
    @abstractmethod
    def modify_attack(self, dice: list[DiceColor]) -> list[DiceColor]:
        pass

    @abstractmethod
    def modify_defense(self, dice: list[DiceColor]) -> list[DiceColor]:
        pass