from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory


from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.config.movement_tactical_config import load_movement_tactical_config
from assault_model.map.terrain_config import terrain_config
from assault_model.map.hex_utils import safe_hex_distance


_MOVE_CFG = load_movement_tactical_config()


class OptionExecutor:
    _ALLOWED_OPTIONS_BY_STRATEGY = {
        StrategicIntent.CAPTURE: {TacticalOption.ADVANCE, TacticalOption.FLANK, TacticalOption.ATTACK},
        StrategicIntent.DENY: {TacticalOption.ADVANCE, TacticalOption.ATTACK, TacticalOption.HOLD},
        StrategicIntent.ATTRIT: {TacticalOption.ATTACK, TacticalOption.FLANK, TacticalOption.ADVANCE},
        StrategicIntent.PRESERVE: {TacticalOption.RETREAT, TacticalOption.HOLD, TacticalOption.ADVANCE},
    }


    def __init__(self, heuristic_controller, avoid_bad_trades: bool = False, adv_threshold: float = -0.5):
        self.heuristic = heuristic_controller
        # When True, block attacks whose combat advantage is below adv_threshold.
        self.avoid_bad_trades = avoid_bad_trades
        # Minimum combat advantage required to consider an attack.
        self.adv_threshold = adv_threshold

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
            # Prioritize uncaptured objectives; deprioritize already owned.
            need = 0.0 if owned_by_self else 1.0
            dist = safe_hex_distance(unit.position, vp.hex_coords)
            score = need * 100.0 + float(getattr(vp, "per_turn", 0)) * 2.0 - float(dist)
            if score > best_score:
                best_score = score
                best = vp.hex_coords
        return best

    def _has_uncaptured_objective(self, state, unit) -> bool:
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        own_ownership = side_to_ownership.get(unit.side)
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is None:
                continue
            if hs.ownership != own_ownership:
                return True
        return False

    def _is_target_on_enemy_or_neutral_vp(self, state, unit, target) -> bool:
        if target is None or getattr(target, "position", None) is None:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        pos = (target.position.q, target.position.r)
        vp_hexes = {vp.hex_coords for vp in points}
        if pos not in vp_hexes:
            return False
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        own_ownership = side_to_ownership.get(unit.side)
        hs = state.hex_states.get(pos)
        return hs is None or hs.ownership != own_ownership

    def _is_capture_emergency(self, state, unit) -> bool:
        if unit is None:
            return False
        hp = float(getattr(unit, "hp", 0) or 0)
        max_hp = float(getattr(getattr(unit, "unit_type", None), "max_strength", 0) or 0)
        suppressed = bool(getattr(unit, "suppressed", False))
        enemies = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) != getattr(unit, "side", None)
            and getattr(u, "position", None) is not None
            and getattr(unit, "position", None) is not None
        ]
        close_threat = any(safe_hex_distance(unit.position, e.position) <= 2 for e in enemies)
        low_hp = hp <= max(1.0, max_hp * 0.34) if max_hp > 0 else hp <= 1.0
        return bool(suppressed or (low_hp and close_threat))

    def _tag_action(self, action, option: TacticalOption, strategy: StrategicIntent | None):
        if action is None:
            return None
        action.rl_l2_option = option.name
        action.rl_l3_strategy = strategy.name if strategy is not None else None
        return action

    # -------------------------------------------------
    def execute(
        self,
        state,
        unit,
        option: TacticalOption,
        attack_mode: int | None = None,
        strategy: StrategicIntent | None = None,
    ):

        if unit is None:
            return WaitAction("SYSTEM")

        option = self._resolve_option_for_strategy(state, unit, option, strategy)
        option = self._apply_local_role_bias(state, unit, option, strategy)
        if (
            strategy == StrategicIntent.CAPTURE
            and option == TacticalOption.RETREAT
            and self._has_uncaptured_objective(state, unit)
            and not self._is_capture_emergency(state, unit)
        ):
            option = TacticalOption.ADVANCE

        # -------------------------------------------------
        # ✅ ATTACK
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            return self._tag_action(self._execute_attack(state, unit, attack_mode), option, strategy)

        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self._tag_action(self._move_closer(state, unit), option, strategy)

        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return self._tag_action(self._flank_move(state, unit), option, strategy)

        # -------------------------------------------------
        # ✅ RETREAT (NO ATAQUE)
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:

            action = self.heuristic.choose_action(state, unit, option)

            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                return self._tag_action(WaitAction(unit.unit_id), option, strategy)

            return self._tag_action(action or WaitAction(unit.unit_id), option, strategy)

        # -------------------------------------------------
        # ✅ HOLD (MEJORADO CON FALLBACK)
        # -------------------------------------------------
        if option == TacticalOption.HOLD:

            actions = ActionCatalog(state, unit, terrain_config).actions()

            attacks = [
                a for a in actions
                if isinstance(a, RangedDirectAttack)
            ]

            if attacks:
                best = self._best_attack(attacks, state=state, unit=unit)
                return self._tag_action(best if best else attacks[0], option, strategy)
            # If there are relevant objectives to capture, avoid pure passivity.
            if self._objective_target_hex(state, unit) is not None:
                return self._tag_action(self._move_closer(state, unit), option, strategy)
            return self._tag_action(WaitAction(unit.unit_id), option, strategy)

        return self._tag_action(WaitAction(unit.unit_id), option, strategy)

    def _resolve_option_for_strategy(self, state, unit, option: TacticalOption, strategy: StrategicIntent | None):
        if strategy is None:
            return option
        allowed = self._ALLOWED_OPTIONS_BY_STRATEGY.get(strategy)
        if not allowed or option in allowed:
            return option

        # Strategy-constrained fallback option (deterministic).
        if strategy == StrategicIntent.CAPTURE:
            if self._has_uncaptured_objective(state, unit):
                return TacticalOption.ADVANCE
            return TacticalOption.ATTACK
        if strategy == StrategicIntent.DENY:
            return TacticalOption.ATTACK if self._has_uncaptured_objective(state, unit) else TacticalOption.HOLD
        if strategy == StrategicIntent.ATTRIT:
            return TacticalOption.ATTACK
        if strategy == StrategicIntent.PRESERVE:
            return TacticalOption.RETREAT
        return option

    def _local_role_kind(self, state, unit) -> str:
        classification = str(getattr(getattr(unit, "unit_type", None), "classification", "")).upper()
        if "INDIRECT" in classification or "SUPPORT" in classification:
            return "SUPPORT"
        enemies = [u for u in state.units if u.alive and u.side != unit.side and u.position is not None]
        if not enemies or getattr(unit, "position", None) is None:
            return "MANEUVER"
        dmin = min(safe_hex_distance(unit.position, e.position) for e in enemies)
        if dmin <= 2:
            return "ASSAULT"
        return "MANEUVER"

    def _apply_local_role_bias(self, state, unit, option: TacticalOption, strategy: StrategicIntent | None) -> TacticalOption:
        if strategy is None:
            return option
        allowed = self._ALLOWED_OPTIONS_BY_STRATEGY.get(strategy, set())
        role = self._local_role_kind(state, unit)

        preferred = option
        if role == "SUPPORT":
            if strategy in (StrategicIntent.CAPTURE, StrategicIntent.DENY, StrategicIntent.ATTRIT):
                preferred = TacticalOption.ATTACK
            elif strategy == StrategicIntent.PRESERVE:
                preferred = TacticalOption.HOLD
        elif role == "ASSAULT":
            if strategy == StrategicIntent.PRESERVE:
                preferred = TacticalOption.RETREAT
            elif strategy in (StrategicIntent.CAPTURE, StrategicIntent.ATTRIT):
                preferred = TacticalOption.ATTACK
        else:  # MANEUVER
            if strategy == StrategicIntent.CAPTURE:
                preferred = TacticalOption.ADVANCE
            elif strategy == StrategicIntent.ATTRIT:
                preferred = TacticalOption.FLANK

        if preferred in allowed:
            return preferred
        return option if option in allowed else self._resolve_option_for_strategy(state, unit, option, strategy)

    # -------------------------------------------------
    # ✅ ATTACK (MEJORADO CON FALLBACK)
    # -------------------------------------------------
    def _execute_attack(self, state, unit, attack_mode):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        attacks = [
            a for a in actions
            if isinstance(a, (RangedDirectAttack, RangedIndirectAttack))
        ]

        if not attacks:
            return self._move_closer(state, unit)

        best = self._best_attack(attacks, state=state, unit=unit)

        # ✅ fallback crítico (SIEMPRE dispara)
        return best if best else attacks[0]

    # -------------------------------------------------
    def _move_closer(self, state, unit):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        objective_target = self._objective_target_hex(state, unit)
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if objective_target is None and not enemies:
            return WaitAction(unit.unit_id)

        if objective_target is None:
            objective_target = min(
                enemies,
                key=lambda e: safe_hex_distance(unit.position, e.position)
            ).position

        best = None
        best_score = float("-inf")

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            d = safe_hex_distance(new_pos, objective_target)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = -float(d) + _MOVE_CFG.advance_terrain_weight * terrain_score

            if score > best_score:
                best = a
                best_score = score

        return best or WaitAction(unit.unit_id)

    # -------------------------------------------------
    def _flank_move(self, state, unit):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        objective_target = self._objective_target_hex(state, unit)
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if objective_target is None and not enemies:
            return WaitAction(unit.unit_id)

        if objective_target is None:
            objective_target = min(
                enemies,
                key=lambda e: safe_hex_distance(unit.position, e.position)
            ).position

        best = None
        best_score = float("-inf")

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            dist = safe_hex_distance(new_pos, objective_target)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)

            # ✅ Siempre preferir acercarse (antes: todas las casillas a
            # >6 hex puntuaban 0 y se elegía el primer movimiento del
            # catálogo → deriva horizontal sin avanzar).
            score = -dist + _MOVE_CFG.flank_terrain_weight * terrain_score

            # Bonus de flanqueo: posiciones en el "anillo" de combate
            # (cerca pero sin pegarse de frente al objetivo).
            if 1 < dist <= 3:
                score += 3

            if score > best_score:
                best_score = score
                best = a

        return best or self._move_closer(state, unit)

    # -------------------------------------------------
    # ✅ TARGET SELECTION (FIX SUAVE + FALLBACK)
    # -------------------------------------------------
    def _best_attack(self, attacks, state=None, unit=None):

        best = None
        best_score = float("-inf")

        for a in attacks:

            target = getattr(a, "target", None)

            if target is None or not target.alive:
                continue

            # robustly obtain the acting unit from the action object
            unit = getattr(a, "unit", None) or getattr(a, "actor", None) or getattr(a, "attacker", None)
            if unit is None:
                # cannot score this attack without a unit reference
                continue

            adv = unit.get_combat_advantage(target)
            # expected damage proxy (optional further gating)
            exp_dmg = getattr(unit, "get_expected_damage", lambda t: 0.0)(target)
            hp = getattr(target, "hp", 10)

            # If configured, block attacks that look like bad trades.
            if self.avoid_bad_trades:
                # hard block for very negative advantage
                if adv < -0.3:
                    continue

                # configurable threshold: skip when advantage below threshold
                if adv < self.adv_threshold:
                    continue

                # avoid low-advantage attacks vs high-HP targets
                if adv < 0.0 and hp > 6:
                    continue

                # avoid tiny expected damage attacks (e.g., bazooka team against armored)
                if exp_dmg <= 0.05 and hp > 3:
                    continue

            score = 0

            # ✅ núcleo del scoring
            score += adv * 30

            # ✅ debilidad del enemigo
            score += (10 - hp) * 3

            # ✅ kill confirm
            if hp <= 1:
                score += 60

            # ✅ castigo a duros
            score -= hp * 2

            # ✅ sesgo ofensivo
            score += 5

            # Objective-aware priority:
            # if target is on a VP not controlled by our side, prioritize this attack.
            if state is not None and unit is not None and self._is_target_on_enemy_or_neutral_vp(state, unit, target):
                score += 35

            # distancia
            if hasattr(unit, "position") and hasattr(target, "position"):
                dist = safe_hex_distance(unit.position, target.position)

                if dist <= 2:
                    score += 3
                elif dist > 6:
                    score -= 5

            if score > best_score:
                best_score = score
                best = a

        # If no acceptable attack was found, fall back to the safest available attack.
        if best is not None:
            return best

        # fallback crítico: JAMÁS dejar sin ataque
        return attacks[0] if attacks else WaitAction("SYSTEM")
