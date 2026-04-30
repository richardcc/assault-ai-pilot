# assault_sim/debug/console_listener.py
#
# Console event listener.
# This listener subscribes to the EventBus and prints
# human-readable, high-level simulation information.
#
# It respects DebugConfig flags and does NOT rely on
# low-level tracing or environment variables.

from assault_sim.debug.debug_config import DebugConfig


class ConsoleListener:
    """
    Human-readable console listener for simulation events.

    This listener converts structured EventBus events into
    readable console output such as:
    - unit movements (from -> to)
    - hp changes per action
    - turn progression
    - close combat rounds and outcomes
    """

    def __init__(self, debug_config: DebugConfig):
        self.cfg = debug_config

    def __call__(self, event: dict):
        event_type = event.get("type")
        payload = event.get("payload", {})

        # -------------------------------------------------
        # Lifecycle events
        # -------------------------------------------------
        if event_type == "RESET" and self.cfg.enabled:
            print(
                f"[RESET] Scenario={payload.get('scenario')} "
                f"Turn={payload.get('turn')}"
            )

        elif event_type == "UNIT_LOADED" and self.cfg.enabled:
            print(
                f"[UNIT] {payload.get('unit_id')} "
                f"side={payload.get('side')} "
                f"pos={payload.get('position')}"
            )

        # -------------------------------------------------
        # Action-level events
        # -------------------------------------------------
        elif event_type == "ACTION" and self.cfg.log_actions:
            print(
                f"[ACTION] Turn {payload.get('turn')} "
                f"{payload.get('active_unit')} -> "
                f"{payload.get('action')}"
            )

        elif event_type == "DEBUG_MOVE_PATH" and self.cfg.log_movement:
            print(
                f"[MOVE] {payload.get('unit_id')} "
                f"path={payload.get('path')}"
            )

        elif event_type == "ACTION_EFFECT" and self.cfg.log_effects:
            before = payload.get("before", {})
            after = payload.get("after", {})
            hp_delta = payload.get("hp_delta")

            if hp_delta is not None:
                print(
                    f"[EFFECT] {payload.get('action')} "
                    f"{before.get('unit_id')} "
                    f"hp {before.get('hp')} -> {after.get('hp')}"
                )

        # -------------------------------------------------
        # Turn progression
        # -------------------------------------------------
        elif event_type == "TURN_STATE" and self.cfg.log_turns:
            print(
                f"[TURN] {payload.get('turn')} "
                f"active={payload.get('active_unit')}"
            )

        # -------------------------------------------------
        # Victory points
        # -------------------------------------------------
        elif event_type == "VP_UPDATE" and self.cfg.log_vp:
            print(
                f"[VP] total={payload.get('total')}"
            )

        # -------------------------------------------------
        # Close combat observability
        # -------------------------------------------------
        elif event_type == "CLOSE_COMBAT_ROUND" and self.cfg.log_close_combat:
            print(
                f"[CC] Round {payload.get('round')} "
                f"{payload.get('attacker')} hp "
                f"{payload.get('attacker_hp_before')} -> "
                f"{payload.get('attacker_hp_after')} | "
                f"{payload.get('defender')} hp "
                f"{payload.get('defender_hp_before')} -> "
                f"{payload.get('defender_hp_after')}"
            )

        elif event_type == "CLOSE_COMBAT_END" and self.cfg.log_close_combat:
            print(
                f"[CC END] winner={payload.get('winner')}"
            )