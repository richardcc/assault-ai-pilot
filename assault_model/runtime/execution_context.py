class ExecutionContext:
    """
    ExecutionContext carries non-domain infrastructure needed during execution.

    Examples:
    - EventBus (observability)
    - Debug flags
    - Future: replay hooks, profiling, logging

    IMPORTANT:
    This object MUST NOT be stored inside GameState.
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus