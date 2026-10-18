"""
Procedural Scenario & Asymmetric Force Mutator (Palma et al. Transfer)
=======================================================================
Applies seed-deterministic procedural perturbations to terrain cover density,
unit initial deployment coordinates, and asymmetric unit strength to improve
zero-shot tactical generalization during self-play.
"""

from __future__ import annotations

import random
from typing import Dict, Any

from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import neighbors
from assault_model.map.terrain import Terrain
from assault_model.state.game_state import GameState

_NATURAL_COVER_TERRAINS = (
    Terrain.LIGHT_FOREST,
    Terrain.HEAVY_FOREST,
    Terrain.BRUSH,
    Terrain.HILL,
    Terrain.ROCKY,
    Terrain.OLIVE_GROVE,
)


def apply_procedural_mutation(
    state: GameState,
    seed: int,
    terrain_mutation_prob: float = 0.0,
    unit_jitter_prob: float = 0.0,
    asymmetric_strength_jitter: float = 0.0,
    spatial_clumping: bool = True,
) -> Dict[str, Any]:
    """
    Mutate a GameState in-place using a deterministic RNG seeded by `seed`.

    Incorporates Palma et al. (2025) asymmetric procedural perturbation and
    Henry Hyde (2015, Ch. 6, pp. 308-310) spatial autocorrelation ("clumping")
    so generated hills and woods form realistic contiguous ridges/hedgerows
    instead of isolated "molehills".
    """
    rng = random.Random(int(seed) ^ 0x5A17C9)
    vp_hexes = set()
    if state.victory:
        vp_hexes = {vp.hex_coords for vp in state.victory.points}

    occupied = {
        (u.position.q, u.position.r)
        for u in state.units
        if u.alive and u.position is not None
    }

    mutated_terrain_count = 0
    clumped_terrain_count = 0
    jittered_units_count = 0
    strength_jittered_count = 0

    # 1. Procedural Scenery / Terrain Density Mutation with Hyde Spatial Clumping
    if terrain_mutation_prob > 0.0:
        for hex_obj in state.game_map.hexes:
            coords = (hex_obj.q, hex_obj.r)
            if coords in vp_hexes or coords in occupied:
                continue
            if hex_obj.terrain in (Terrain.WATER, Terrain.BUILDING_SINGLE, Terrain.BUILDING_MULTI):
                continue

            # Check adjacent natural cover hexes for spatial autocorrelation (Hyde 2015, p. 310)
            neighbor_cover_terrains = []
            if spatial_clumping:
                for nb in neighbors(coords):
                    nb_state = state.hex_states.get(nb)
                    if nb_state is not None and nb_state.hex.terrain in _NATURAL_COVER_TERRAINS:
                        neighbor_cover_terrains.append(nb_state.hex.terrain)

            effective_prob = float(terrain_mutation_prob)
            if spatial_clumping and hex_obj.terrain == Terrain.CLEAR and neighbor_cover_terrains:
                # Boost probability near existing hills/woods to form ridges/clusters
                effective_prob = min(0.85, effective_prob * 1.45)

            if rng.random() < effective_prob:
                if hex_obj.terrain == Terrain.CLEAR:
                    if spatial_clumping and neighbor_cover_terrains and rng.random() < 0.70:
                        # 70% chance to propagate neighbor terrain type (Hyde p. 310)
                        hex_obj.terrain = rng.choice(neighbor_cover_terrains)
                        clumped_terrain_count += 1
                    else:
                        hex_obj.terrain = rng.choice(_NATURAL_COVER_TERRAINS)
                    mutated_terrain_count += 1
                elif hex_obj.terrain in _NATURAL_COVER_TERRAINS:
                    # Preserve contiguous clusters more often than isolated "molehills"
                    if not (spatial_clumping and len(neighbor_cover_terrains) >= 2 and rng.random() < 0.60):
                        hex_obj.terrain = Terrain.CLEAR
                        mutated_terrain_count += 1

    # 2. Tactical Unit Deployment Position Jitter
    if unit_jitter_prob > 0.0:
        for unit in state.units:
            if not unit.alive or unit.position is None:
                continue
            old_coords = (unit.position.q, unit.position.r)
            if old_coords in vp_hexes:
                continue
            if rng.random() < unit_jitter_prob:
                cand_neighbors = [
                    nb
                    for nb in neighbors(old_coords)
                    if nb in state.hex_states
                    and nb not in occupied
                    and state.hex_states[nb].hex.terrain != Terrain.WATER
                ]
                if cand_neighbors:
                    new_q, new_r = rng.choice(cand_neighbors)
                    occupied.discard(old_coords)
                    occupied.add((new_q, new_r))
                    unit.position = HexCoord(new_q, new_r)
                    state.record_unit_event(unit, prev_coords=old_coords)
                    jittered_units_count += 1

    # 3. Asymmetric Force Strength Perturbation
    if asymmetric_strength_jitter > 0.0:
        for unit in state.units:
            if not unit.alive:
                continue
            max_str = int(getattr(unit, "max_strength", getattr(unit, "strength", 1)) or 1)
            cur_str = int(getattr(unit, "strength", max_str) or max_str)
            if max_str > 1 and rng.random() < asymmetric_strength_jitter:
                delta = rng.choice([-1, 1])
                new_str = max(1, min(max_str, cur_str + delta))
                if new_str != cur_str:
                    unit.strength = new_str
                    strength_jittered_count += 1

    if jittered_units_count > 0:
        state.recalculate_hex_control()

    return {
        "mutated_terrain_count": mutated_terrain_count,
        "clumped_terrain_count": clumped_terrain_count,
        "jittered_units_count": jittered_units_count,
        "strength_jittered_count": strength_jittered_count,
    }
