import heapq

from assault_model.rules.movement_path import MovementPath
from assault_model.rules.movement_outcome import MovementOutcome
from assault_model.map.hex_coord import HexCoord

from assault_model.rules.movement_terrain_rules import MovementTerrainRules
from assault_model.map.terrain import Terrain
from assault_model.map.terrain_config import terrain_config
from typing import Optional, Dict, List, Tuple, Any, Set
from assault_model.map.hex_utils import neighbors as hex_neighbors, safe_hex_distance
from assault_model.rules.fortification_rules import FortificationRules
from assault_model.combat.line_of_sight import check_line_of_sight, LineOfSight


def _is_vehicle(unit) -> bool:
    flag = getattr(unit, "is_vehicle", None)
    if flag is not None:
        return bool(flag)
    try:
        return unit.unit_type.category.name == "VEHICLE"
    except Exception:
        return False


def _reconstruct(came_from, key):
    """Ruta de HexCoord desde el primer paso (excluyendo el origen) hasta `key`."""
    seq = []
    cur = key
    while cur is not None and came_from.get(cur) is not None:
        seq.append(HexCoord(cur[0], cur[1]))
        cur = came_from[cur]
    seq.reverse()
    return seq


class MovementRules:
    """
    Genera los movimientos legales de una unidad respetando:
    - allowance de movimiento de la unidad (unit_type.movement)
    - coste de terreno por tipo de movimiento (terrain_config.get_move_cost)
    - paso a traves de unidades amigas (stacking solo se aplica al terminar)
    - hex enemigo -> asalto (END_IN_ENEMY_HEX)
    - terreno impasable y harsh terrain (9.5)

    Reglamento: 9.1 (Normal Movement), 9.4 (Terrain Costs), 9.5 (Harsh Terrain).
    """

    @staticmethod
    def can_use_fast_action(unit) -> bool:
        """
        Check if unit can perform fast action (Rule 9.2).
        Units with SLOW, SLOW_UNIT, IMMOBILE, or SET_UP_TIME cannot use fast action.
        """
        if unit is None:
            return False
        prohibited = {"SLOW", "SLOW_UNIT", "IMMOBILE", "SET_UP_TIME", "HEAVY_WEIGHT"}
        if hasattr(unit, "has_trait"):
            if any(unit.has_trait(t) for t in prohibited):
                return False
        unit_type = getattr(unit, "unit_type", None)
        if unit_type is not None and hasattr(unit_type, "has_trait"):
            if any(unit_type.has_trait(t) for t in prohibited):
                return False
        return True

    @staticmethod
    def get_legal_paths(game_state, unit):
        # Short-lived cache keyed by authoritative state version.
        state_version = int(getattr(game_state, "_cache_version", 0))
        pos = getattr(unit, "position", None)
        cache_key = (
            state_version,
            getattr(unit, "unit_id", None),
            getattr(pos, "q", None),
            getattr(pos, "r", None),
            getattr(unit, "side", None),
            int(getattr(getattr(unit, "unit_type", None), "movement", 0) or 0),
            str(getattr(getattr(unit, "unit_type", None), "movement_type", "foot")),
        )
        cache = getattr(game_state, "_movement_paths_cache", None)
        if cache is None:
            cache = {}
            game_state._movement_paths_cache = cache
        cached = cache.get(cache_key)
        if cached is not None:
            # Shallow copy list container to avoid accidental caller mutation.
            return list(cached)

        paths: list[MovementPath] = []

        start = getattr(unit, "position", None)
        if start is None or not getattr(unit, "alive", True):
            return paths

        max_mp = getattr(unit.unit_type, "movement", 0) or 0
        if max_mp <= 0:
            return paths

        # Rule: IMMOBILE units (e.g. 8.8cm Flak 36, 90mm AA Gun) cannot move autonomously
        if hasattr(unit, "has_trait") and unit.has_trait("IMMOBILE"):
            return paths
        unit_type = getattr(unit, "unit_type", None)
        if unit_type is not None and hasattr(unit_type, "has_trait") and unit_type.has_trait("IMMOBILE"):
            return paths

        move_type = getattr(unit.unit_type, "movement_type", "foot")

        # -------------------------------------------------
        # ocupantes (vivos) indexados por coordenada
        # -------------------------------------------------
        occupants = {}
        for u in game_state.units:
            if u.alive and u.position is not None:
                occupants[(u.position.q, u.position.r)] = u

        start_key = (start.q, start.r)

        best_cost = {start_key: 0}
        came_from = {start_key: None}

        empty_dests = set()          # key -> destino vacio
        enemy_dests = {}             # key -> (coste, target_id, path)
        vehicle_dests = {}           # key -> (coste, vehicle_id, path)

        frontier = [(0, start.q, start.r)]

        # Precomputed static adjacency & enter costs (Roadmap 6.1)
        gmap = game_state.game_map
        get_static_graph = getattr(gmap, "get_static_movement_graph", None)
        static_adj_tuples = None
        if callable(get_static_graph):
            graph_res = get_static_graph(move_type, terrain_config)
            if graph_res:
                static_adj_tuples = graph_res[0]

        # -------------------------------------------------
        # Dijkstra bounded by movement point budget
        # -------------------------------------------------
        while frontier:
            cost, q, r = heapq.heappop(frontier)

            if cost > best_cost.get((q, r), float("inf")):
                continue

            if static_adj_tuples is not None:
                neighbor_entries = static_adj_tuples.get((q, r), ())
            else:
                neighbor_entries = []
                for nq, nr in hex_neighbors((q, r)):
                    tile = gmap.get_hex(nq, nr)
                    if tile is None or not MovementTerrainRules.can_enter_hex(unit, tile):
                        continue
                    ec = terrain_config.get_move_cost(tile.get_terrain(), move_type)
                    ft = gmap.get_hex_fortification(nq, nr)
                    ec = FortificationRules.movement_cost_for_fortification(ft, move_type, ec)
                    if ec is not None:
                        neighbor_entries.append((nq, nr, ec))

            current_tile = gmap.get_hex(q, r) if gmap else None
            for nq, nr, enter_cost in neighbor_entries:
                new_cost = cost + enter_cost
                if new_cost > max_mp:
                    continue

                # Rule: HEAVY_WEIGHT cannot move up or down an elevation level (Hill) autonomously
                if (hasattr(unit, "has_trait") and unit.has_trait("HEAVY_WEIGHT")) or (
                    getattr(unit, "unit_type", None) and hasattr(unit.unit_type, "has_trait") and unit.unit_type.has_trait("HEAVY_WEIGHT")
                ):
                    next_tile = gmap.get_hex(nq, nr) if gmap else None
                    if current_tile is not None and next_tile is not None:
                        is_cur_hill = (getattr(current_tile, "terrain", None) == Terrain.HILL or getattr(current_tile, "terrain_type", None) == "hill")
                        is_next_hill = (getattr(next_tile, "terrain", None) == Terrain.HILL or getattr(next_tile, "terrain_type", None) == "hill")
                        if is_cur_hill != is_next_hill:
                            continue

                key = (nq, nr)
                occ = occupants.get(key)

                # -----------------------------------------
                # HEX ENEMIGO -> ASALTO (no transitable)
                # -----------------------------------------
                if occ is not None and occ.side != unit.side:
                    prev = enemy_dests.get(key)
                    if prev is None or new_cost < prev[0]:
                        path = _reconstruct(came_from, (q, r)) + [HexCoord(nq, nr)]
                        enemy_dests[key] = (new_cost, occ.unit_id, path)
                    continue

                # -----------------------------------------
                # HEX AMIGO
                # -----------------------------------------
                if occ is not None and occ.side == unit.side:
                    if _is_vehicle(occ):
                        # cargar en vehiculo: destino, no transitable
                        prev = vehicle_dests.get(key)
                        if prev is None or new_cost < prev[0]:
                            path = _reconstruct(came_from, (q, r)) + [HexCoord(nq, nr)]
                            vehicle_dests[key] = (new_cost, occ.unit_id, path)
                        continue
                    # infanteria/artilleria amiga: se puede ATRAVESAR,
                    # pero no TERMINAR encima (stacking).
                    if new_cost < best_cost.get(key, float("inf")):
                        best_cost[key] = new_cost
                        came_from[key] = (q, r)
                        heapq.heappush(frontier, (new_cost, nq, nr))
                    continue

                # -----------------------------------------
                # HEX VACIO -> destino valido + transitable
                # -----------------------------------------
                if new_cost < best_cost.get(key, float("inf")):
                    best_cost[key] = new_cost
                    came_from[key] = (q, r)
                    empty_dests.add(key)
                    heapq.heappush(frontier, (new_cost, nq, nr))

        # -------------------------------------------------
        # HARSH TERRAIN (9.5): vecino inmediato cuyo coste de
        # entrada supera la allowance -> 1 hex desde adyacente,
        # gasta todo el MP. Solo hexes vacios.
        # -------------------------------------------------
        if static_adj_tuples is not None:
            start_neighbors = static_adj_tuples.get(start_key, ())
            for nq, nr, enter_cost in start_neighbors:
                if enter_cost <= max_mp:
                    continue
                key = (nq, nr)
                if key in best_cost or key in empty_dests or key in enemy_dests or key in vehicle_dests:
                    continue
                if occupants.get(key) is not None:
                    continue
                empty_dests.add(key)
                came_from[key] = start_key
        else:
            for nq, nr in hex_neighbors((start.q, start.r)):
                key = (nq, nr)
                if key in best_cost or key in empty_dests:
                    continue
                if key in enemy_dests or key in vehicle_dests:
                    continue

                tile = gmap.get_hex(nq, nr)
                if tile is None:
                    continue
                if not MovementTerrainRules.can_enter_hex(unit, tile):
                    continue
                if occupants.get(key) is not None:
                    continue

                enter_cost = terrain_config.get_move_cost(tile.get_terrain(), move_type)
                fort_type = gmap.get_hex_fortification(nq, nr)
                enter_cost = FortificationRules.movement_cost_for_fortification(
                    fort_type, move_type, enter_cost
                )
                if enter_cost is None:
                    continue
                if enter_cost > max_mp:
                    empty_dests.add(key)
                    came_from[key] = start_key

        # -------------------------------------------------
        # CONSTRUIR MovementPaths
        # -------------------------------------------------
        for key in empty_dests:
            path = _reconstruct(came_from, key)
            if not path:
                continue
            paths.append(
                MovementPath(
                    path=path,
                    outcome=MovementOutcome.END_IN_EMPTY_HEX,
                )
            )

        for key, (_, target_id, path) in enemy_dests.items():
            paths.append(
                MovementPath(
                    path=path,
                    outcome=MovementOutcome.END_IN_ENEMY_HEX,
                    target_unit_id=target_id,
                )
            )

        for key, (_, vehicle_id, path) in vehicle_dests.items():
            paths.append(
                MovementPath(
                    path=path,
                    outcome=MovementOutcome.END_IN_FRIENDLY_VEHICLE,
                    target_unit_id=vehicle_id,
                )
            )

        cache[cache_key] = tuple(paths)
        return list(paths)

    # -------------------------------------------------
    # FALLBACK RETREAT ALGORITHM (Section 6.4 / Rule 13.3)
    # -------------------------------------------------
    @staticmethod
    def calculate_fallback_destination(
        game_state,
        unit,
        attacker=None,
        friendly_edge: Optional[str] = None,
        game_map=None,
    ) -> Tuple[Optional[HexCoord], List[Dict[str, Any]]]:
        """
        Calculates the tactical fallback retreat destination according to Rule 13.3 / Section 6.4:
        1. Moves away from the direction of attack (must not decrease distance to attacker if avoidable).
        2. Filters for legal, passable hexes (excludes enemy-occupied, out-of-bounds, impassable).
        3. Prioritizes Defilade (LOS BLOCKED from attacker > LOS HINDERED > CLEAR).
        4. Selects best available terrain defense cover (trenches, bunkers, woods, buildings).
        5. Aligns retreat vector towards the friendly board edge (retaguardia amiga).
        6. Deterministic tie-breaking by coordinates.
        7. Returns (best_hex_coord, scored_candidates). If no legal hex exists, returns (None, []).
        """
        gmap = getattr(game_state, "game_map", None) or game_map
        if gmap is None:
            return None, []

        start = getattr(unit, "position", None)
        if start is None or not getattr(unit, "alive", True):
            return None, []

        start_coord = HexCoord.from_any(start)
        start_t = (start_coord.q, start_coord.r)

        all_units = getattr(game_state, "units", None) or []
        if not all_units and (unit or attacker):
            all_units = [u for u in (unit, attacker) if u is not None]

        occupants: Dict[Tuple[int, int], Any] = {}
        for u in all_units:
            u_pos = getattr(u, "position", None)
            if getattr(u, "alive", True) and u_pos is not None:
                u_coord = HexCoord.from_any(u_pos)
                if getattr(u, "unit_id", None) != getattr(unit, "unit_id", None):
                    occupants[(u_coord.q, u_coord.r)] = u

        attacker_pos = getattr(attacker, "position", None) if attacker is not None else None
        attacker_coord = HexCoord.from_any(attacker_pos) if attacker_pos is not None else None
        current_dist = safe_hex_distance(start_coord, attacker_coord) if attacker_coord is not None else 0

        # Infer friendly edge if not explicitly provided
        unit_side = str(getattr(unit, "side", "")).upper()
        if not friendly_edge:
            fe_map = getattr(game_state, "friendly_edges", {}) or {}
            friendly_edge = fe_map.get(unit_side)
            if not friendly_edge:
                if unit_side in ("US", "UK"):
                    friendly_edge = "SOUTH"
                elif unit_side in ("IT", "GE"):
                    friendly_edge = "NORTH"

        scored_candidates: List[Dict[str, Any]] = []

        for nq, nr in hex_neighbors(start_t):
            tile = gmap.get_hex(nq, nr)
            if tile is None:
                continue
            if not MovementTerrainRules.can_enter_hex(unit, tile):
                continue

            occ = occupants.get((nq, nr))
            if occ is not None:
                if getattr(occ, "side", None) != getattr(unit, "side", None):
                    continue  # Enemy occupied
                # Friendly unit stacking check
                if _is_vehicle(occ) and not _is_vehicle(unit):
                    pass  # Infantry mounting friendly vehicle in emergency
                else:
                    continue  # Friendly foot unit already occupies hex

            cand_coord = HexCoord(nq, nr)

            # --- 1. Defilade Evaluation (Line of Sight from Attacker) ---
            los_result = LineOfSight.CLEAR
            defilade_score = 0
            if attacker is not None and attacker_coord is not None:
                los_result = check_line_of_sight(attacker, cand_coord, gmap, terrain_config)
                if los_result == LineOfSight.BLOCKED:
                    defilade_score = 100
                elif los_result == LineOfSight.HINDERED:
                    defilade_score = 40
                else:
                    defilade_score = 0
            else:
                terrain_name_str = tile.get_terrain()
                cfg_los = terrain_config.get(terrain_name_str, {}).get("los", "CLEAR") if hasattr(terrain_config, "get") else "CLEAR"
                if cfg_los == "BLOCKED":
                    defilade_score = 50
                elif cfg_los == "HINDERED":
                    defilade_score = 25

            # --- 2. Terrain Defense Cover Evaluation ---
            terrain_name_str = tile.get_terrain()
            unit_cat = getattr(getattr(unit, "unit_type", None), "category", None)
            unit_cat_name = unit_cat.name if hasattr(unit_cat, "name") else "INFANTRY"
            dice_names = terrain_config.get_defense_dice(terrain_name_str, unit_cat_name)
            cover_score = 0
            for d in dice_names:
                if d == "GREEN":
                    cover_score += 6
                elif d == "BLUE":
                    cover_score += 4
                elif d == "YELLOW":
                    cover_score += 2

            fort_type = gmap.get_hex_fortification(nq, nr)
            if fort_type == "bunker":
                cover_score += 15
            elif fort_type in ("casemate", "pillbox"):
                cover_score += 12
            elif fort_type == "trench":
                cover_score += 8
            elif fort_type in ("sandbag", "sandbag_position"):
                cover_score += 4

            # --- 3. Distance to Attacker (Away from Attack) ---
            dist_score = 0
            cand_dist = 0
            if attacker_coord is not None:
                cand_dist = safe_hex_distance(cand_coord, attacker_coord)
                delta_d = cand_dist - current_dist
                if delta_d > 0:
                    dist_score = 30 * delta_d
                elif delta_d == 0:
                    dist_score = 5
                else:
                    dist_score = -500  # Strongly penalize moving closer to the threat

            # --- 4. Alignment with Friendly Board Edge ---
            edge_score = 0
            if friendly_edge == "NORTH":
                edge_score = -(nr - start_coord.r) * 15
            elif friendly_edge == "SOUTH":
                edge_score = (nr - start_coord.r) * 15
            elif friendly_edge == "EAST":
                edge_score = (nq - start_coord.q) * 15
            elif friendly_edge == "WEST":
                edge_score = -(nq - start_coord.q) * 15
            elif attacker_coord is not None:
                dot = (nq - start_coord.q) * (start_coord.q - attacker_coord.q) + (nr - start_coord.r) * (start_coord.r - attacker_coord.r)
                edge_score = 10 * dot

            total_score = defilade_score + cover_score + dist_score + edge_score

            scored_candidates.append({
                "coord": cand_coord,
                "q": nq,
                "r": nr,
                "total_score": total_score,
                "defilade_score": defilade_score,
                "defilade_status": los_result,
                "cover_score": cover_score,
                "dist_score": dist_score,
                "cand_dist": cand_dist,
                "edge_score": edge_score,
            })

        if not scored_candidates:
            return None, []

        scored_candidates.sort(
            key=lambda c: (
                c["total_score"],
                c["defilade_score"],
                c["cover_score"],
                c["cand_dist"],
                -c["q"],
                -c["r"],
            ),
            reverse=True,
        )

        best_coord = scored_candidates[0]["coord"]
        return best_coord, scored_candidates

