from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack

from assault_model.rules.movement_rules import MovementRules
from assault_model.rules.movement_outcome import MovementOutcome

from assault_model.map.hex_utils import safe_hex_distance
from assault_model.combat.line_of_sight import has_line_of_sight
from assault_model.actions.ranged_indirect import RangedIndirectAttack

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE] {tag} {payload}")


class ActionCatalog:

    def __init__(self, game_state, unit, terrain_config=None):
        self.gs = game_state
        self.unit = unit

        if terrain_config is None:
            raise ValueError(
                "ActionCatalog requires terrain_config. "
                "Use: ActionCatalog(state, unit, terrain_config)"
            )

        self.terrain_config = terrain_config


    def actions(self):
        active = self.unit

        if active is None:
            return [WaitAction("SYSTEM")]

        if not getattr(active, "alive", True):
            return []

        actions = []

        _trace("ACTION_CATALOG_START", unit=active.unit_id)

        # ----------------------------------
        # MOVEMENT
        # ----------------------------------
        movement_paths = MovementRules.get_legal_paths(self.gs, active)

        for mp in movement_paths:

            _trace(
                "MOVEMENT_PATH_EVAL",
                unit=active.unit_id,
                outcome=str(mp.outcome),
                target=mp.target_unit_id,
            )

            if mp.outcome == MovementOutcome.END_IN_EMPTY_HEX:
                actions.append(
                    MoveAction(
                        unit_id=active.unit_id,
                        path=mp.path,
                    )
                )

            elif mp.outcome == MovementOutcome.END_IN_ENEMY_HEX:
                target = next(
                    (u for u in self.gs.units if u.unit_id == mp.target_unit_id),
                    None,
                )

                if target is not None and target.alive:
                    actions.append(
                        AssaultAction(
                            unit_id=active.unit_id,
                            target_id=mp.target_unit_id,
                        )
                    )

        # ----------------------------------
        # RANGED FIRE
        # ----------------------------------
        actions.extend(self._ranged_fire_actions(active))

        # ----------------------------------
        # WAIT
        # ----------------------------------
        actions.append(WaitAction(active.unit_id))

        # ----------------------------------
        # DEBUG FINAL
        # ----------------------------------

        _trace(
            "ACTION_CATALOG_END",
            unit=active.unit_id,
            action_count=len(actions),
        )

        # ✅ ✅ NUEVO: DEBUG ACTION IDs
        if DEBUG_TRACE:
            for a in actions:
                _trace(
                    "ACTION_ID",
                    unit=active.unit_id,
                    action=getattr(a, "action_id", None)
                )

        return actions

    # ==================================================
    # RANGED FIRE
    # ==================================================
    def _ranged_fire_actions(self, active):

        actions = []

        if not getattr(active, "can_fire", True):
            return actions

        for other in self.gs.units:

            if other.side == active.side:
                continue

            if not other.alive:
                continue

            if other.unit_id not in getattr(active, "spotted_enemies", []):
                continue

            distance = safe_hex_distance(active.position, other.position)

            if not self._in_weapon_range(active, other):
                continue

            mode = active.unit_type._resolve_attack_mode(distance)

            if mode == "DIRECT_FIRE":
                if not self._has_line_of_sight(active, other):
                    continue

            if mode == "INDIRECT_FIRE":
                _trace(
                    "ACTION_ADD",
                    action="RangedIndirectAttack",
                    attacker=active.unit_id,
                    target=other.unit_id,
                    mode=mode,
                )
                act = RangedIndirectAttack(active.unit_id, (other.position.q, other.position.r))
                # Compatibility metadata used by logs/telemetry.
                act.target_id = other.unit_id
                act.attack_mode = "INDIRECT_FIRE"
                actions.append(act)
            else:
                _trace(
                    "ACTION_ADD",
                    action="RangedDirectAttack",
                    attacker=active.unit_id,
                    target=other.unit_id,
                    mode=mode,
                )
                act = RangedDirectAttack(active.unit_id, other.unit_id)
                act.attack_mode = "DIRECT_FIRE"
                actions.append(act)

        return actions

    # ==================================================
    def _in_weapon_range(self, attacker, target):

        distance =safe_hex_distance(attacker.position, target.position)
        attack = attacker.unit_type._attack_raw

        for mode_data in attack.values():
            table = mode_data.get(target.unit_type.category.value)
            if not table:
                continue

            for key in table.keys():

                if "-" in key:
                    start, end = map(int, key.split("-"))
                    if start <= distance <= end:
                        return True
                else:
                    if int(key) == distance:
                        return True

        return False

    # ==================================================
    def _has_line_of_sight(self, attacker, target):
        return has_line_of_sight(
            attacker,
            target,
            self.gs.game_map,
            self.terrain_config
        )
