from typing import List, Dict, Tuple
from assault_model.core.victory_point import VictoryPoint


class VictoryConditions:
    def __init__(self, points: List[VictoryPoint]):
        self.points = points

    @classmethod
    def from_json(cls, raw: Dict) -> "VictoryConditions":
        value = raw.get("value_per_hex", 0)
        points = [
            VictoryPoint(
                hex_coords=(q, r),
                per_turn=value
            )
            for q, r in raw.get("hexes", [])
        ]
        return cls(points)