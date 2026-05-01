from typing import List, Dict, Tuple
from assault_model.core.victory_point import VictoryPoint


class VictoryConditions:
    """
    Victory condition definition for a scenario.

    Role:
    - Defines which hexes are Victory Points.
    - Defines how many points each VP hex generates per turn.
    - Acts as a static, scenario-level definition.

    Guarantees:
    - Holds a list of VictoryPoint objects.
    - Does not change during the simulation.

    Does NOT:
    - Track control of VP hexes.
    - Award points per turn.
    - Decide winners or end the match.

    Usage:
    - Created by scenario_loader from scenario JSON.
    - Consumed by GameState / VictoryPointTracker to calculate scores.
    """

    def __init__(self, points: List[VictoryPoint]):
        """
        Create a VictoryConditions object.

        Parameters:
        - points: List of VictoryPoint definitions for the scenario.
        """
        self.points = points

    @classmethod
    def from_json(cls, raw: Dict) -> "VictoryConditions":
        """
        Build VictoryConditions from JSON data.

        Expected JSON format:

        {
            "value_per_hex": <int>,
            "hexes": [
                [q, r],
                [q, r],
                ...
            ]
        }

        Behavior:
        - All listed hexes share the same per-turn value.
        - Each hex is converted into a VictoryPoint object.

        Parameters:
        - raw: Dict parsed from scenario JSON under key "vp".

        Returns:
        - VictoryConditions
        """

        # Points awarded per VP hex per turn
        value = raw.get("value_per_hex", 0)

        # Create VictoryPoint objects for each specified hex
        points = [
            VictoryPoint(
                hex_coords=(q, r),
                per_turn=value
            )
            for q, r in raw.get("hexes", [])
        ]

        return cls(points)