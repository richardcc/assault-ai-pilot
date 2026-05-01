# Combat actions

# assault_model/actions/combat.py
from assault_model.actions.action import Action
from assault_model.actions.action_type import ActionType
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class RangedAttackAction(Action):
    def __init__(self, unit_id: str, target_id: str):
        _trace(
            "RANGED_ATTACK_ACTION_INIT",
            attacker_id=unit_id,
            target_id=target_id,
        )

        super().__init__(
            unit_id,
            ActionType.RANGED_ATTACK,
            payload={"target_id": target_id},
        )


class CloseCombatAction(Action):
    def __init__(self, unit_id: str, target_id: str):
        _trace(
            "CLOSE_COMBAT_ACTION_INIT",
            attacker_id=unit_id,
            target_id=target_id,
        )

        super().__init__(
            unit_id,
            ActionType.CLOSE_COMBAT,
            payload={"target_id": target_id},
        )