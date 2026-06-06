import heapq

from assault_model.rules.movement_path import MovementPath
from assault_model.rules.movement_outcome import MovementOutcome
from assault_model.map.hex_coord import HexCoord

from assault_model.rules.movement_terrain_rules import MovementTerrainRules
from assault_model.map.terrain_config import terrain_config
from assault_model.map.hex_utils import neighbors as hex_neighbors
from assault_model.rules.fortification_rules import FortificationRules


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
    def get_legal_paths(game_state, unit):

        paths: list[MovementPath] = []

        start = getattr(unit, "position", None)
        if start is None:
            return paths

        max_mp = getattr(unit.unit_type, "movement", 0) or 0
        if max_mp <= 0:
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

        # -------------------------------------------------
        # DIJKSTRA por presupuesto de puntos de movimiento
        # -------------------------------------------------
        while frontier:
            cost, q, r = heapq.heappop(frontier)

            if cost > best_cost.get((q, r), float("inf")):
                continue

            for nq, nr in hex_neighbors((q, r)):

                tile = game_state.game_map.get_hex(nq, nr)
                if tile is None:
                    continue

                if not MovementTerrainRules.can_enter_hex(unit, tile):
                    continue

                enter_cost = terrain_config.get_move_cost(
                    tile.get_terrain(), move_type
                )
                fort_type = game_state.game_map.get_hex_fortification(nq, nr)
                enter_cost = FortificationRules.movement_cost_for_fortification(
                    fort_type, move_type, enter_cost
                )
                if enter_cost is None:
                    continue  # impasable para este tipo de movimiento

                new_cost = cost + enter_cost
                if new_cost > max_mp:
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
        for nq, nr in hex_neighbors((start.q, start.r)):
            key = (nq, nr)
            if key in best_cost or key in empty_dests:
                continue
            if key in enemy_dests or key in vehicle_dests:
                continue

            tile = game_state.game_map.get_hex(nq, nr)
            if tile is None:
                continue
            if not MovementTerrainRules.can_enter_hex(unit, tile):
                continue
            if occupants.get(key) is not None:
                continue

            enter_cost = terrain_config.get_move_cost(tile.get_terrain(), move_type)
            fort_type = game_state.game_map.get_hex_fortification(nq, nr)
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

        return paths
