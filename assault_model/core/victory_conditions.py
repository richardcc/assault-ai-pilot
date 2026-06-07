from typing import List, Dict, Any
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

        def _normalize_hex_entry(
            entry: Any,
            default_value: int,
        ) -> tuple[tuple[int, int], str | None, int]:
            # Backward-compatible format: [q, r]
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                q, r = entry
                return (int(q), int(r)), None, default_value

            # Extended format:
            # { "q": 4, "r": 8, "initial_owner": "GE" }
            # { "coords": [4, 8], "owner": "US" }
            if isinstance(entry, dict):
                if "coords" in entry:
                    q, r = entry["coords"]
                elif "hex" in entry:
                    q, r = entry["hex"]
                else:
                    q = entry.get("q")
                    r = entry.get("r")
                if q is None or r is None:
                    raise ValueError(f"Invalid VP hex entry: {entry}")
                owner = (
                    entry.get("initial_owner")
                    or entry.get("owner")
                    or entry.get("occupied_by")
                )
                owner = str(owner).strip().upper() if owner else None
                per_turn = entry.get("value", entry.get("per_turn", default_value))
                return (int(q), int(r)), owner, int(per_turn)

            raise ValueError(f"Invalid VP hex entry: {entry}")

        points: List[VictoryPoint] = []
        for hex_entry in raw.get("hexes", []):
            coords, initial_owner, per_turn = _normalize_hex_entry(
                hex_entry,
                value,
            )
            points.append(
                VictoryPoint(
                    hex_coords=coords,
                    per_turn=per_turn,
                    initial_owner=initial_owner,
                )
            )

        return cls(points)