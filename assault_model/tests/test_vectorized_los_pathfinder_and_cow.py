"""
Tests for Roadmap Section 6.1 (Vectorized Ray-Casting LOS & Pathfinder with NumPy/Numba)
and Section 6.2 (Transactional Copy-on-Write CoW & Delta State for MCTS).
"""

from __future__ import annotations

import copy
import time
import numpy as np

from assault_model.combat.line_of_sight import (
    LineOfSight,
    _hexes_at_pixel_ui,
    _hex_to_pixel_ui,
    _trace_ray_geometry_tuples,
    check_line_of_sight,
    clear_los_cache,
    precompute_visibility_matrix,
)
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_ownership import HexOwnership
from assault_model.map.hex_utils import (
    hex_distance,
    hex_distance_batch,
    precompute_adjacency_tensors,
    vectorized_kinematic_dijkstra,
)
from assault_model.map.terrain_config import terrain_config
from assault_model.rules.movement_rules import MovementRules
from assault_model.state.cow_state import CoWHexStateMap
from voec_sim.core.simulator import VOECSimulator


def _reference_ray_paths(a: HexCoord, b: HexCoord):
    """Pure Python reference ray tracer to verify 100% parity with vectorized kernel."""
    if a.q == b.q and a.r == b.r:
        return ((a.q, a.r),), ()
    dist = hex_distance(a, b)
    if dist <= 1:
        return ((a.q, a.r), (b.q, b.r)), ()

    ax, ay = _hex_to_pixel_ui(a.q, a.r)
    bx, by = _hex_to_pixel_ui(b.q, b.r)
    samples = max(dist * 4, dist + 1)

    path_full = [(a.q, a.r)]
    primary_spine = [(a.q, a.r)]
    for i in range(samples + 1):
        t = i / samples
        px = ax + (bx - ax) * t
        py = ay + (by - ay) * t
        seg = _hexes_at_pixel_ui(px, py)
        if seg:
            p0 = (seg[0].q, seg[0].r)
            if primary_spine[-1] != p0:
                primary_spine.append(p0)
        for h in seg:
            ht = (h.q, h.r)
            if path_full[-1] != ht:
                path_full.append(ht)

    end_t = (b.q, b.r)
    if path_full[-1] != end_t:
        path_full.append(end_t)
    if primary_spine[-1] != end_t:
        primary_spine.append(end_t)

    inner = []
    seen = set()
    for pt in primary_spine[1:-1]:
        if pt == end_t or pt in seen:
            continue
        seen.add(pt)
        inner.append(pt)
    return tuple(path_full), tuple(inner)


def test_section_6_1_vectorized_ray_interpolation_exact_parity():
    clear_los_cache()
    coords = [HexCoord(q, r) for q in range(0, 10, 2) for r in range(0, 10, 2)]
    for a in coords:
        for b in coords:
            vec_full, vec_inner = _trace_ray_geometry_tuples(a, b)
            ref_full, ref_inner = _reference_ray_paths(a, b)
            assert vec_full == ref_full
            assert vec_inner == ref_inner


def test_section_6_1_precomputed_visibility_and_adjacency_tensors():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=42)
    state = sim._state
    gmap = state.game_map

    # 1. Precomputed topology & distance tensors
    adj_indices, coord_to_idx, dist_matrix, coords_list = gmap.get_topology_tensors()
    n = len(coords_list)
    assert adj_indices.shape == (n, 6)
    assert dist_matrix.shape == (n, n)
    assert np.all(np.diag(dist_matrix) == 0)

    # Verify batch hex distance matches scalar hex_distance
    sample_idx = min(n, 20)
    for i in range(sample_idx):
        for j in range(sample_idx):
            assert int(dist_matrix[i, j]) == hex_distance(coords_list[i], coords_list[j])

    # 2. Precomputed visibility matrix matches check_line_of_sight
    vis_matrix, vis_coord_to_idx = precompute_visibility_matrix(gmap, terrain_config)
    assert vis_matrix.shape == (n, n)
    assert vis_coord_to_idx == coord_to_idx

    alive_units = [u for u in state.units if u.alive and u.position is not None]
    for u1 in alive_units:
        for u2 in alive_units:
            if u1.unit_id == u2.unit_id:
                continue
            los_enum = check_line_of_sight(u1, u2, gmap, terrain_config)
            idx1 = vis_coord_to_idx[(u1.position.q, u1.position.r)]
            idx2 = vis_coord_to_idx[(u2.position.q, u2.position.r)]
            assert int(vis_matrix[idx1, idx2]) == int(los_enum.value)

    # 3. Precomputed static movement graph & kinematic Dijkstra kernel
    adj_tuples, adj_enter_costs, _, _, _ = gmap.get_static_movement_graph("foot", terrain_config)
    assert len(adj_tuples) == n
    assert adj_enter_costs.shape == (n, 6)

    impassable = np.zeros(n, dtype=np.bool_)
    best_cost, came_from = vectorized_kinematic_dijkstra(
        adj_indices, adj_enter_costs, start_idx=0, max_mp=4, impassable_mask=impassable
    )
    assert best_cost.shape == (n,)
    assert came_from.shape == (n,)
    assert int(best_cost[0]) == 0

    # Verify MovementRules.get_legal_paths works seamlessly with static movement graph
    paths = MovementRules.get_legal_paths(state, alive_units[0])
    assert isinstance(paths, list)


def test_section_6_2_cow_cloning_singleton_sharing_and_delta_isolation():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=11)
    root_state = sim._state
    assert isinstance(root_state.hex_states, CoWHexStateMap)

    # Clone via clone_cow and copy.deepcopy
    child_state = root_state.clone_cow()
    deep_state = copy.deepcopy(root_state)

    # 1. Static singletons are shared in read-only memory (zero duplication)
    assert child_state.game_map is root_state.game_map
    assert deep_state.game_map is root_state.game_map
    assert child_state.victory is root_state.victory
    assert child_state.turn_order is root_state.turn_order
    assert child_state.side_to_ownership is root_state.side_to_ownership
    assert child_state.units[0].unit_type is root_state.units[0].unit_type

    # 2. Immediately after branching, 0 HexState objects are duplicated in _deltas
    assert isinstance(child_state.hex_states, CoWHexStateMap)
    assert child_state.hex_states.delta_count == 0
    assert child_state.hex_states.base_count == len(root_state.game_map.hexes)

    # 3. Mutate dynamic state in child_state (move unit, apply damage, suppress, recalculate control)
    u0_child = child_state.units[0]
    u0_root = root_state.units[0]
    orig_pos = (u0_root.position.q, u0_root.position.r)
    orig_hp = u0_root.strength

    # Find an empty valid hex on the map to move u0_child to
    occupied = {(u.position.q, u.position.r) for u in child_state.units if u.position}
    target_hex = next(
        (h.q, h.r) for h in child_state.game_map.hexes if (h.q, h.r) not in occupied
    )
    u0_child.move_to(target_hex[0], target_hex[1])
    u0_child.apply_damage(1)
    u0_child.apply_suppression()
    child_state.recalculate_hex_control()

    # Verify root_state is 100% untouched
    assert (u0_root.position.q, u0_root.position.r) == orig_pos
    assert u0_root.strength == orig_hp
    assert not u0_root.suppressed
    assert root_state.hex_states.get_readonly(target_hex).ownership == HexOwnership.NONE
    assert child_state.hex_states.get_readonly(target_hex).ownership != HexOwnership.NONE

    # Only the few hexes whose ownership actually changed were materialized in _deltas!
    assert 1 <= child_state.hex_states.delta_count <= 4

    # 4. Verify transactional delta registry (Delta positions, Delta health, Delta morale, Delta hex ownership)
    delta = root_state.compute_delta(child_state)
    assert not delta.is_empty
    assert delta.delta_positions[u0_child.unit_id] == target_hex
    assert delta.delta_health[u0_child.unit_id] == (orig_hp - 1, u0_child.alive)
    assert delta.delta_morale[u0_child.unit_id] == (True, False)
    assert target_hex in delta.delta_hex_ownership

    # 5. Verify O(Delta) checkpoint & restore_checkpoint rollback
    ckpt = root_state.create_checkpoint()
    root_state.units[0].move_to(target_hex[0], target_hex[1])
    root_state.units[0].apply_damage(1)
    root_state.recalculate_hex_control()
    assert (root_state.units[0].position.q, root_state.units[0].position.r) == target_hex

    root_state.restore_checkpoint(ckpt)
    root_state.recalculate_hex_control()
    assert (root_state.units[0].position.q, root_state.units[0].position.r) == orig_pos
    assert root_state.units[0].strength == orig_hp
    assert root_state.hex_states.get_readonly(target_hex).ownership == HexOwnership.NONE


def test_section_6_1_and_6_2_mcts_expansion_speed_benchmark():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=99)
    state = sim._state

    # Warm up static caches once
    _ = precompute_visibility_matrix(state.game_map, terrain_config)
    _ = MovementRules.get_legal_paths(state, state.units[0])

    # Benchmark 500 CoW state clones + incremental control updates (MCTS expansion hot loop)
    t0 = time.perf_counter()
    for _ in range(500):
        cloned = state.clone_cow()
        cloned.recalculate_hex_control()
    elapsed_s = time.perf_counter() - t0
    steps_per_sec = 500.0 / max(elapsed_s, 1e-9)

    # Target from Roadmap 6.1/6.2: > 2,000 steps/s in expansion/simulation hot path
    assert steps_per_sec > 2000.0, f"Expected > 2000 clones/s, got {steps_per_sec:.1f}"
