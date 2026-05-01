# assault_model/core/event_bus.py

class EventBus:
    def __init__(self, config=None):
        """
        EventBus with optional observability filtering.

        - If no config is provided, ALL events are emitted.
        - Events are only suppressed if a flag is explicitly set to False.
        """
        self.subscribers = []
        self.config = config or {}

    def subscribe(self, fn):
        self.subscribers.append(fn)

    def emit(self, event: dict):
        if not self._is_enabled(event):
            return

        for fn in self.subscribers:
            fn(event)

    # -------------------------------------------------
    # OBSERVABILITY FILTER
    # -------------------------------------------------
    def _is_enabled(self, event: dict) -> bool:
        event_type = event.get("type")
        payload = event.get("payload", {})
        payload_cfg = self.config.get("payload", {})

        # =================================================
        # CLOSE COMBAT via ACTION_EFFECT (REAL MODEL)
        # =================================================
        if (
            event_type == "ACTION_EFFECT"
            and payload.get("action") == "CloseCombat"
        ):
            combat_cfg = payload_cfg.get("combat")

            # No combat config -> allow
            if not combat_cfg:
                return True

            # Master switch
            if combat_cfg.get("enabled") is False:
                return False

            close_cfg = combat_cfg.get("close_combat", {})

            # Close combat result visibility
            return close_cfg.get("winner", True)

        # =================================================
        # FUTURE COMBAT_* EVENTS (FORWARD COMPATIBLE)
        # =================================================
        if event_type and event_type.startswith("COMBAT_"):
            combat_cfg = payload_cfg.get("combat")

            if not combat_cfg:
                return True

            if combat_cfg.get("enabled") is False:
                return False

            close_cfg = combat_cfg.get("close_combat", {})

            return {
                "COMBAT_ROUND": close_cfg.get("rounds", True),
                "COMBAT_DAMAGE": close_cfg.get("damage", True),
                "COMBAT_HP_DELTA": close_cfg.get("hp_delta", True),
                "COMBAT_RESULT": close_cfg.get("winner", True),
            }.get(event_type, True)

        # =================================================
        # GENERIC EVENTS (opt-out + payload control)
        # =================================================
        events_cfg = payload_cfg.get("events", {})

        mapping = {
            "RESET": "lifecycle",
            "UNIT_LOADED": "lifecycle",
            "ACTION": "actions",
            "DEBUG_MOVE_PATH": "movement",
            "ACTION_EFFECT": "effects",
            "TURN_STATE": "turns",
            "TURN_END": "turns",
            "VP_UPDATE": "victory",
            "MAP_STATE": "turns",
        }

        key = mapping.get(event_type)

        # No mapping -> controlled by "payload"
        if not key:
            return events_cfg.get("payload", True)

        # Mapping exists but flag not present -> allow
        if key not in events_cfg:
            return True

        # Explicit False blocks
        return events_cfg[key] is not False
