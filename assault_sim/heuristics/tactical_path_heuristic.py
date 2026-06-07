from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.map.terrain_config import terrain_config
from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.config.movement_tactical_config import load_movement_tactical_config

from assault_model.map.hex_utils import safe_hex_distance


_MOVE_CFG = load_movement_tactical_config()


class TacticalPathHeuristic:
    def _unit_group(self, unit) -> str:
        ut = getattr(unit, "unit_type", None)
        cat = getattr(ut, "category", None)
        val = str(getattr(cat, "value", "INFANTRY")).upper()
        if "VEHICLE" in val:
            return "VEHICLE"
        if "ARTILLERY" in val:
            return "ARTILLERY"
        return "INFANTRY"

    def _hex_terrain_name(self, state, pos) -> str:
        game_map = getattr(state, "game_map", None)
        if game_map is None or pos is None:
            return "clear"
        hx = game_map.get_hex(pos.q, pos.r)
        if hx is None:
            return "clear"
        return hx.get_terrain()

    def _terrain_tactical_score(self, state, unit, pos) -> float:
        terrain_name = self._hex_terrain_name(state, pos)
        group = self._unit_group(unit)
        # More defense dice and hindered/blocked LOS are generally safer.
        defense_score = float(len(terrain_config.get_defense_dice(terrain_name, group)))
        los = str(terrain_config.get_los(terrain_name)).upper()
        los_bonus = 0.0
        if los == "HINDERED":
            los_bonus = 0.35
        elif los == "BLOCKED":
            los_bonus = 0.6
        return defense_score + los_bonus

    def _objective_target_hex(self, state, unit):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        own_ownership = side_to_ownership.get(unit.side)
        best = None
        best_score = float("-inf")
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            owned_by_self = hs is not None and hs.ownership == own_ownership
            need = 0.0 if owned_by_self else 1.0
            dist = safe_hex_distance(unit.position, vp.hex_coords)
            score = need * 100.0 + float(getattr(vp, "per_turn", 0)) * 2.0 - float(dist)
            if score > best_score:
                best_score = score
                best = vp.hex_coords
        return best

    # -------------------------------------------------
    def choose_action(self, state, unit, option):

        if unit is None:
            return None

        # ------------------------------------------
        # ✅ acciones válidas
        # ------------------------------------------
        actions = ActionCatalog(state, unit, terrain_config).actions()
        if not actions:
            return None

        # ------------------------------------------
        # ✅ tipos de acción
        # ------------------------------------------
        attacks = [
            a for a in actions
            if isinstance(a, (RangedDirectAttack, RangedIndirectAttack))
        ]

        moves = [
            a for a in actions
            if getattr(a.action_type, "category", None).name == "MOVEMENT"
        ]

        # ------------------------------------------
        # ✅ opciones
        # ------------------------------------------

        if option == TacticalOption.ATTACK:
            if attacks:
                return attacks[0]
            return self._move_closer(state, unit, moves)

        if option == TacticalOption.ADVANCE:
            return self._move_closer(state, unit, moves)

        if option == TacticalOption.FLANK:
            return self._flank_move(state, unit, moves)

        if option == TacticalOption.HOLD:
            return WaitAction(unit.unit_id)

        if option == TacticalOption.RETREAT:
            return self._retreat(state, unit, moves)

        return None

    # -------------------------------------------------
    def _nearest_enemy(self, state, unit):

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return None

        return min(
            enemies,
            key=lambda e: safe_hex_distance(unit.position, e.position)
        )

    # -------------------------------------------------
    def _move_closer(self, state, unit, moves):
        objective_target = self._objective_target_hex(state, unit)
        target = self._nearest_enemy(state, unit)
        if objective_target is None and target is None:
            return None
        if not moves:
            return None

        best = None
        best_score = float("-inf")

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            ref = objective_target if objective_target is not None else target.position
            d = safe_hex_distance(new_pos, ref)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = -float(d) + _MOVE_CFG.advance_terrain_weight * terrain_score

            if score > best_score:
                best_score = score
                best = m

        return best

    # -------------------------------------------------
    def _flank_move(self, state, unit, moves):
        objective_target = self._objective_target_hex(state, unit)
        target = self._nearest_enemy(state, unit)
        if objective_target is None and target is None:
            return None
        if not moves:
            return None

        best = None
        best_score = -999

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            ref = objective_target if objective_target is not None else target.position
            dist = safe_hex_distance(new_pos, ref)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = max(0, 6 - dist) + _MOVE_CFG.flank_terrain_weight * terrain_score

            if score > best_score:
                best_score = score
                best = m

        return best

    # -------------------------------------------------
    def _retreat(self, state, unit, moves):

        target = self._nearest_enemy(state, unit)

        if target is None or not moves:
            return None

        best = None
        best_score = float("-inf")

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            d = safe_hex_distance(new_pos, target.position)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = float(d) + _MOVE_CFG.retreat_terrain_weight * terrain_score

            if score > best_score:
                best_score = score
                best = m

        return best
