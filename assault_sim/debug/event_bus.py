# assault_model/core/event_bus.py


class EventBus:
    def __init__(self, config=None):
        """
        EventBus with optional observability filtering.

        CURRENT STATUS:
        - Passthrough mode: ALL events are emitted.
        - Filtering logic is temporarily disabled to guarantee full observability
          while the system architecture is still evolving.

        FUTURE INTENT:
        - Re-enable semantic filtering once the event taxonomy and observer
          contracts are stable.
        """
        self.subscribers = []
        self.config = config or {}

    def subscribe(self, fn):
        self.subscribers.append(fn)

    def emit(self, event: dict):
        # PASSTHROUGH:
        # Always emit events to subscribers.
        for fn in self.subscribers:
            fn(event)

    # -------------------------------------------------
    # OBSERVABILITY FILTER (DOCUMENTED, CURRENTLY DISABLED)
    # -------------------------------------------------
    def _is_enabled(self, event: dict) -> bool:
        """
        PASSTHROUGH FILTER

        This method currently allows ALL events to pass.

        RATIONALE:
        - The event model is not finalized.
        - Observers (console, debug, tests) rely on full causal visibility.
        - Premature filtering causes silent loss of critical information.

        FUTURE BEHAVIOR (TO BE RE-ENABLED):
        - Semantic filtering based on event categories:
          lifecycle, actions, movement, combat, state synchronization.
        - Filtering will be opt-out, never opt-in.
        - Structural events (movement, state changes, combat resolution)
          must NEVER be filtered by default.
        """

        return True