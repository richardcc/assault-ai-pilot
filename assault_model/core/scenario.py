from typing import List, Optional, Dict

from assault_model.map.map import Map
from assault_model.units.unit_instance import UnitInstance


class Scenario:
    """
    Entry point of engine execution.

    A Scenario defines the initial conditions of the game.
    """

    def __init__(
        self,
        name: str,
        game_map: Map,
        units: List[UnitInstance],
        max_turns: Optional[int] = None,
        vp_conditions: Optional[Dict] = None,
    ) -> None:
        self.name = name
        self.game_map = game_map
        self.units = units
        self.max_turns = max_turns
        self.vp_conditions = vp_conditions