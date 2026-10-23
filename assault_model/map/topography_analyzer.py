"""
Topography and Terrain Intelligence Preparation of the Battlefield (IPB) Analyzer.

Performs Turn-0 static topographical profiling to classify hexagons into:
1. Key Terrain (VPs and commanding elevation)
2. Defilade Corridors (Protected covered infiltration avenues)
3. Killzones (Open, crossfire-exposed interdiction zones)
4. Chokepoints (Constricted lateral mobility funnels / bottlenecks)
5. Base of Fire Positions (Commanding overwatch hexes with broad fields of fire)

Computes a 5-dimensional tactical vector per hexagon:
[cover_rating, elevation_dominance, los_exposure, chokepoint_bottleneck, vp_proximity_utility]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import math

from assault_model.map.hex_utils import hex_distance, neighbors


# Standard cover ratings by canonical terrain keyword
_TERRAIN_COVER_WEIGHTS: Dict[str, float] = {
    "bunker": 1.00,
    "pillbox": 1.00,
    "fortification": 0.95,
    "trench": 0.85,
    "heavy_building": 0.90,
    "stone_building": 0.90,
    "building": 0.85,
    "urban": 0.85,
    "city": 0.85,
    "ruins": 0.80,
    "dense_woods": 0.75,
    "forest": 0.75,
    "woods": 0.70,
    "bocage": 0.75,
    "sunken_road": 0.65,
    "rough": 0.55,
    "orchard": 0.50,
    "brush": 0.40,
    "grain": 0.30,
    "clear": 0.15,
    "open": 0.15,
    "road": 0.10,
    "paved_road": 0.10,
    "sand": 0.15,
    "water": 0.00,
    "swamp": 0.25,
}

_TERRAIN_ELEVATION_WEIGHTS: Dict[str, float] = {
    "hill_crest": 1.00,
    "crest": 0.90,
    "hill": 0.80,
    "ridge": 0.85,
    "high_ground": 0.75,
    "building": 0.40,
    "clear": 0.10,
}

_IMPASSABLE_TERRAINS: Set[str] = {
    "water",
    "deep_water",
    "sea",
    "cliff",
    "impassable",
}


@dataclass(frozen=True)
class Hex5DProfile:
    """
    5-Dimensional Topographical and Tactical Profile for a single hexagon.
    """
    q: int
    r: int
    terrain: str
    cover_rating: float          # [0.0, 1.0] Defensive terrain and concealment value
    elevation_dominance: float   # [0.0, 1.0] Relative commanding elevation
    los_exposure: float          # [0.0, 1.0] Exposure to crossfire / open sightlines
    chokepoint_bottleneck: float # [0.0, 1.0] Lateral constriction / funneling intensity
    vp_proximity_utility: float  # [0.0, 1.0] Proximity / utility towards Key Terrain (VPs)
    classification: str          # KEY_TERRAIN, DEFILADE_CORRIDOR, KILLZONE, CHOKEPOINT, BASE_OF_FIRE, MANEUVER_TRANSIT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "q": int(self.q),
            "r": int(self.r),
            "terrain": str(self.terrain),
            "cover_rating": round(float(self.cover_rating), 3),
            "elevation_dominance": round(float(self.elevation_dominance), 3),
            "los_exposure": round(float(self.los_exposure), 3),
            "chokepoint_bottleneck": round(float(self.chokepoint_bottleneck), 3),
            "vp_proximity_utility": round(float(self.vp_proximity_utility), 3),
            "classification": str(self.classification),
        }

    @property
    def vector5d(self) -> Tuple[float, float, float, float, float]:
        return (
            float(self.cover_rating),
            float(self.elevation_dominance),
            float(self.los_exposure),
            float(self.chokepoint_bottleneck),
            float(self.vp_proximity_utility),
        )


@dataclass
class TopographyProfile:
    """
    Full battlefield Intelligence Preparation of the Battlefield (IPB) profile.
    """
    scenario_id: str = ""
    hex_profiles: Dict[Tuple[int, int], Hex5DProfile] = field(default_factory=dict)
    key_terrain_hexes: Set[Tuple[int, int]] = field(default_factory=set)
    defilade_corridor_hexes: Set[Tuple[int, int]] = field(default_factory=set)
    killzone_hexes: Set[Tuple[int, int]] = field(default_factory=set)
    chokepoint_hexes: Set[Tuple[int, int]] = field(default_factory=set)
    base_of_fire_hexes: Set[Tuple[int, int]] = field(default_factory=set)

    def is_key_terrain(self, q: int, r: int) -> bool:
        return (int(q), int(r)) in self.key_terrain_hexes

    def is_defilade(self, q: int, r: int) -> bool:
        return (int(q), int(r)) in self.defilade_corridor_hexes

    def is_killzone(self, q: int, r: int) -> bool:
        return (int(q), int(r)) in self.killzone_hexes

    def is_chokepoint(self, q: int, r: int) -> bool:
        return (int(q), int(r)) in self.chokepoint_hexes

    def is_base_of_fire(self, q: int, r: int) -> bool:
        return (int(q), int(r)) in self.base_of_fire_hexes

    def get_classification(self, q: int, r: int) -> str:
        prof = self.hex_profiles.get((int(q), int(r)))
        return prof.classification if prof else "MANEUVER_TRANSIT"

    def get_5d_vector(self, q: int, r: int) -> Tuple[float, float, float, float, float]:
        prof = self.hex_profiles.get((int(q), int(r)))
        return prof.vector5d if prof else (0.15, 0.10, 0.50, 0.0, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": str(self.scenario_id),
            "counts": {
                "key_terrain": len(self.key_terrain_hexes),
                "defilade_corridors": len(self.defilade_corridor_hexes),
                "killzones": len(self.killzone_hexes),
                "chokepoints": len(self.chokepoint_hexes),
                "base_of_fire": len(self.base_of_fire_hexes),
                "total_hexes": len(self.hex_profiles),
            },
            "key_terrain_hexes": [list(h) for h in sorted(self.key_terrain_hexes)],
            "defilade_corridor_hexes": [list(h) for h in sorted(self.defilade_corridor_hexes)],
            "killzone_hexes": [list(h) for h in sorted(self.killzone_hexes)],
            "chokepoint_hexes": [list(h) for h in sorted(self.chokepoint_hexes)],
            "base_of_fire_hexes": [list(h) for h in sorted(self.base_of_fire_hexes)],
            "hex_profiles": [p.to_dict() for p in sorted(self.hex_profiles.values(), key=lambda x: (x.r, x.q))],
        }


class TopographyAnalyzer:
    """
    Analyzes battlefield topography, cover distributions, and elevation lines
    to generate Intelligence Preparation of the Battlefield (IPB) profiles.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, TopographyProfile] = {}

    def analyze(
        self,
        hex_data: List[Dict[str, Any]],
        vp_hexes: Optional[List[Dict[str, Any]]] = None,
        scenario_id: str = "",
        force_recompute: bool = False,
    ) -> TopographyProfile:
        """
        Analyzes a list of hex dictionaries (each with 'q', 'r', 'terrain') and VP locations.
        """
        cache_key = f"{scenario_id}::{len(hex_data)}"
        if not force_recompute and scenario_id and cache_key in self._cache:
            return self._cache[cache_key]

        grid: Dict[Tuple[int, int], str] = {}
        for h in hex_data:
            if not isinstance(h, dict):
                continue
            q = int(h.get("q", 0))
            r = int(h.get("r", 0))
            t = str(h.get("terrain", "clear") or "clear").lower()
            grid[(q, r)] = t

        vps: Set[Tuple[int, int]] = set()
        for vp in vp_hexes or []:
            if isinstance(vp, dict):
                vps.add((int(vp.get("q", 0)), int(vp.get("r", 0))))
            elif isinstance(vp, (list, tuple)) and len(vp) >= 2:
                vps.add((int(vp[0]), int(vp[1])))

        # 1. Base Cover and Elevation Ratings
        cover_map: Dict[Tuple[int, int], float] = {}
        elevation_map: Dict[Tuple[int, int], float] = {}
        for coord, t_raw in grid.items():
            t_clean = t_raw.lower().replace(" ", "_").replace("-", "_")
            c_score = 0.15
            for k, val in _TERRAIN_COVER_WEIGHTS.items():
                if k in t_clean:
                    c_score = max(c_score, val)
                    break
            cover_map[coord] = c_score

            e_score = 0.10
            for k, val in _TERRAIN_ELEVATION_WEIGHTS.items():
                if k in t_clean:
                    e_score = max(e_score, val)
                    break
            elevation_map[coord] = e_score

        # 2. Chokepoints (Bottlenecks): Constriction between impassable terrain / obstacles
        chokepoint_map: Dict[Tuple[int, int], float] = {}
        for coord in grid:
            t = grid[coord]
            if t in _IMPASSABLE_TERRAINS:
                chokepoint_map[coord] = 0.0
                continue
            nbrs = [n for n in neighbors(coord) if n in grid]
            impassable_count = sum(1 for n in nbrs if grid[n] in _IMPASSABLE_TERRAINS)
            if impassable_count >= 2:
                # Flanked by 2 or more impassable/obstacle hexes -> funnel bottleneck
                chokepoint_map[coord] = 0.85
            elif impassable_count == 1 and len(nbrs) <= 4:
                chokepoint_map[coord] = 0.55
            else:
                chokepoint_map[coord] = 0.10

        # 3. VP Proximity Utility
        vp_utility_map: Dict[Tuple[int, int], float] = {}
        for coord in grid:
            if not vps:
                vp_utility_map[coord] = 0.50
            else:
                min_d = min(hex_distance(coord, vp) for vp in vps)
                vp_utility_map[coord] = 1.0 / (1.0 + float(min_d))

        # 4. LOS Exposure: High on flat open ground, lower in broken/urban/wooded terrain
        los_exposure_map: Dict[Tuple[int, int], float] = {}
        for coord in grid:
            c = cover_map[coord]
            # Open hexes with cover <= 0.20 are highly exposed to crossfire
            if c <= 0.20:
                # Check how open the surrounding 1-hex neighborhood is
                nbrs = [n for n in neighbors(coord) if n in grid]
                avg_nbr_cover = sum(cover_map[n] for n in nbrs) / float(max(1, len(nbrs)))
                # If surrounding hexes are also open, exposure is very high
                los_exposure_map[coord] = min(1.0, 0.70 + (0.30 * (1.0 - avg_nbr_cover)))
            elif c >= 0.70:
                los_exposure_map[coord] = max(0.05, 0.20 - (c * 0.15))
            else:
                los_exposure_map[coord] = max(0.10, 1.0 - c)

        # 5. Classification
        hex_profiles: Dict[Tuple[int, int], Hex5DProfile] = {}
        key_terrain_set: Set[Tuple[int, int]] = set()
        defilade_set: Set[Tuple[int, int]] = set()
        killzone_set: Set[Tuple[int, int]] = set()
        chokepoint_set: Set[Tuple[int, int]] = set()
        bof_set: Set[Tuple[int, int]] = set()

        for coord in grid:
            c = cover_map[coord]
            e = elevation_map[coord]
            l_exp = los_exposure_map[coord]
            chk = chokepoint_map[coord]
            vp_u = vp_utility_map[coord]

            is_vp = coord in vps
            min_vp_dist = min((hex_distance(coord, vp) for vp in vps), default=99)

            if is_vp:
                classification = "KEY_TERRAIN"
                key_terrain_set.add(coord)
            elif (e >= 0.75 or (c >= 0.70 and e >= 0.40)) and 1 <= min_vp_dist <= 6:
                classification = "BASE_OF_FIRE"
                bof_set.add(coord)
            elif chk >= 0.60 and c < 0.60:
                classification = "CHOKEPOINT"
                chokepoint_set.add(coord)
            elif c < 0.35 and l_exp >= 0.60 and min_vp_dist <= 4 and grid[coord] not in _IMPASSABLE_TERRAINS:
                classification = "KILLZONE"
                killzone_set.add(coord)
            elif c >= 0.65 or (c >= 0.50 and l_exp <= 0.35):
                classification = "DEFILADE_CORRIDOR"
                defilade_set.add(coord)
            else:
                classification = "MANEUVER_TRANSIT"

            hex_profiles[coord] = Hex5DProfile(
                q=coord[0],
                r=coord[1],
                terrain=grid[coord],
                cover_rating=c,
                elevation_dominance=e,
                los_exposure=l_exp,
                chokepoint_bottleneck=chk,
                vp_proximity_utility=vp_u,
                classification=classification,
            )

        profile = TopographyProfile(
            scenario_id=str(scenario_id),
            hex_profiles=hex_profiles,
            key_terrain_hexes=key_terrain_set,
            defilade_corridor_hexes=defilade_set,
            killzone_hexes=killzone_set,
            chokepoint_hexes=chokepoint_set,
            base_of_fire_hexes=bof_set,
        )

        if scenario_id:
            self._cache[cache_key] = profile

        return profile


_GLOBAL_ANALYZER = TopographyAnalyzer()


def analyze_battlefield_topography(
    hex_data: List[Dict[str, Any]],
    vp_hexes: Optional[List[Dict[str, Any]]] = None,
    scenario_id: str = "",
    force_recompute: bool = False,
) -> TopographyProfile:
    """
    Module-level function to perform fast Turn-0 IPB topographical profiling.
    """
    return _GLOBAL_ANALYZER.analyze(
        hex_data=hex_data,
        vp_hexes=vp_hexes,
        scenario_id=scenario_id,
        force_recompute=force_recompute,
    )
