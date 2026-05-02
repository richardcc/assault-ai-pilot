from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.map.hex_coord import HexCoord

from assault_sim.heuristics.pathfinding import bfs_hex_path


class TacticalPathHeuristic:
    """
    VP Tactical Heuristic

    Rules:
    1. VP free -> go to VP
    2. VP occupied by enemy -> attack (ENTER enemy hex)
    3. VP occupied by friendly -> move adjacent to cover
    """

    def choose_action(self, state):
        unit = state.active_unit
        if unit is None or not unit.alive:
            return WaitAction(unit.unit_id)

        # --- Victory Point ---
        if not state.victory or not state.victory.points:
            return WaitAction(unit.unit_id)

        vp_q, vp_r = state.victory.points[0].hex_coords
        vp_pos = (vp_q, vp_r)
        start = unit.position

        # -------------------------------------------------
        # Who is on the VP?
        # -------------------------------------------------
        vp_unit = None
        for u in state.units:
            if u.alive and u.position == vp_pos:
                vp_unit = u
                break

        # =================================================
        # CASE 1 & 2:
        #   - VP free
        #   - VP occupied by ENEMY
        #
        # IMPORTANT:
        #   If enemy is on VP, we MUST attempt to ENTER
        #   the hex to trigger CloseCombat.
        # =================================================
        if vp_unit is None or vp_unit.side != unit.side:
            path = bfs_hex_path(start, vp_pos, state)
            if path and len(path) > 0:
                next_hex = path[0]

                # DO NOT block enemy — entering enemy hex is intentional
                if any(
                    u.alive and u.position == next_hex and u.side == unit.side
                    for u in state.units
                ):
                    return WaitAction(unit.unit_id)

                return MoveAction(
                    unit.unit_id,
                    [HexCoord(*next_hex)]
                )

            return WaitAction(unit.unit_id)

        # =================================================
        # CASE 3:
        #   VP occupied by FRIENDLY -> cover it
        # =================================================
        vp_hex = state.game_map.get_hex(*vp_pos)
        if vp_hex is None:
            return WaitAction(unit.unit_id)

        # --- Find free adjacent hexes ---
        cover_hexes = []
        for neigh in vp_hex.neighbors():
            pos = (neigh.q, neigh.r)

            # Must be free
            if any(u.alive and u.position == pos for u in state.units):
                continue

            hex_n = state.game_map.get_hex(*pos)
            if hex_n is None:
                continue
            if hex_n.terrain.value == "water":
                continue

            cover_hexes.append(pos)

        if not cover_hexes:
            return WaitAction(unit.unit_id)

        # Choose closest cover hex
        target = min(
            cover_hexes,
            key=lambda h: abs(h[0] - start[0]) + abs(h[1] - start[1])
        )

        path = bfs_hex_path(start, target, state)
        if path and len(path) > 0:
            next_hex = path[0]

            if any(
                u.alive and u.position == next_hex
                for u in state.units
            ):
                return WaitAction(unit.unit_id)

            return MoveAction(
                unit.unit_id,
                [HexCoord(*next_hex)]
            )

        return WaitAction(unit.unit_id)