from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction
from assault_model.map.hex_utils import safe_hex_distance


class OptionExecutorCombatMixin:
    def _is_attack_action(self, action) -> bool:
        return isinstance(
            action,
            (
                RangedDirectAttack,
                RangedIndirectAttack,
                MoveThenFireAction,
                FireThenMoveAction,
            ),
        )

    def _resolve_action_target(self, state, action):
        target = getattr(action, "target", None)
        if target is not None:
            return target
        target_id = getattr(action, "target_id", None)
        if target_id:
            return next(
                (u for u in getattr(state, "units", []) if getattr(u, "unit_id", None) == target_id),
                None,
            )
        return None

    def _execute_attack(self, state, unit, attack_mode):
        actions = self._get_unit_actions(state, unit)
        attacks = [a for a in actions if self._is_attack_action(a)]
        if not attacks:
            return self._move_closer(state, unit)
        best = self._best_attack(attacks, state=state, unit=unit)
        return best if best else attacks[0]

    def _has_immediate_attack(self, state, unit) -> bool:
        actions = self._get_unit_actions(state, unit)
        return any(self._is_attack_action(a) for a in actions)

    def _best_attack(self, attacks, state=None, unit=None):
        best = None
        best_score = float("-inf")
        for a in attacks:
            target = self._resolve_action_target(state, a)
            if target is None or not target.alive:
                continue

            unit_obj = (
                getattr(a, "unit", None)
                or getattr(a, "actor", None)
                or getattr(a, "attacker", None)
                or unit
            )
            if unit_obj is None:
                continue

            adv = unit_obj.get_combat_advantage(target)
            exp_dmg = getattr(unit_obj, "get_expected_damage", lambda t: 0.0)(target)
            hp = getattr(target, "hp", 10)
            is_move_then_fire = isinstance(a, MoveThenFireAction)
            is_fire_then_move = isinstance(a, FireThenMoveAction)

            if (is_move_then_fire or is_fire_then_move) and exp_dmg <= 0.02 and hp > 2:
                continue
            if is_move_then_fire or is_fire_then_move:
                target_on_vp = (
                    state is not None
                    and unit_obj is not None
                    and self._is_target_on_enemy_or_neutral_vp(state, unit_obj, target)
                )
                if not target_on_vp:
                    if adv < 0.25:
                        continue
                    if exp_dmg < 0.15:
                        continue

            if self.avoid_bad_trades:
                if adv < -0.3:
                    continue
                if adv < self.adv_threshold:
                    continue
                if adv < 0.0 and hp > 6:
                    continue
                if exp_dmg <= 0.05 and hp > 3:
                    continue

            score = 0
            score += adv * 30
            score += (10 - hp) * 3
            if hp <= 1:
                score += 60
            score -= hp * 2
            score += 5

            if is_move_then_fire:
                score += 1
            elif is_fire_then_move:
                score += 0.5

            if state is not None and unit_obj is not None and self._is_target_on_enemy_or_neutral_vp(state, unit_obj, target):
                score += 35

            if hasattr(unit_obj, "position") and hasattr(target, "position"):
                dist = safe_hex_distance(unit_obj.position, target.position)
                if dist <= 2:
                    score += 3
                elif dist > 6:
                    score -= 5

            if state is not None and (is_move_then_fire or is_fire_then_move):
                move_path = getattr(a, "move_path", None) or []
                if move_path:
                    end = move_path[-1]
                    score += 0.2 * self._terrain_tactical_score(state, unit_obj, end)

            if score > best_score:
                best_score = score
                best = a
                setattr(best, "rl_attack_expected_damage", float(exp_dmg or 0.0))

        if best is not None:
            return best
        return attacks[0] if attacks else WaitAction("SYSTEM")


__all__ = ["OptionExecutorCombatMixin"]
