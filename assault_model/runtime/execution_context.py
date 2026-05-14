# assault_model/runtime/execution_context.py

from typing import Optional


class ExecutionContext:
    """
    ExecutionContext carries non-domain, runtime infrastructure needed during execution.

    -------------------------------------------------------------------------
    🧠 PURPOSE
    -------------------------------------------------------------------------
    This object provides external dependencies required by systems during
    action resolution (e.g., combat, reactions), without polluting GameState.

    It is intentionally NOT part of the domain model.

    -------------------------------------------------------------------------
    ✅ WHAT BELONGS HERE
    -------------------------------------------------------------------------
    - Event bus (for observability)
    - Game map (for spatial queries like terrain, LOS)
    - Debug / tracing flags
    - Future hooks (profiling, replay, logging)

    These are runtime dependencies, NOT game rules.

    -------------------------------------------------------------------------
    ❌ WHAT MUST NOT BE HERE
    -------------------------------------------------------------------------
    - Game logic
    - Game rules
    - Mutable game state (HP, positions, etc.)

    Those belong in:
        - GameState
        - UnitInstance
        - Combat resolvers

    -------------------------------------------------------------------------
    🧩 DESIGN PRINCIPLE
    -------------------------------------------------------------------------
    ExecutionContext allows resolvers to:
        ✅ Query environment (e.g., terrain, LOS)
        ✅ Emit events
    without:
        ❌ Coupling GameState to infrastructure
        ❌ Violating clean architecture boundaries

    -------------------------------------------------------------------------
    🔥 WHY game_map IS HERE
    -------------------------------------------------------------------------
    We include game_map so that combat systems can:

        - Query terrain:
            hex = context.game_map.get_hex(unit.position)

        - Compute line of sight (LOS)

        - Evaluate spatial rules without embedding the map in units or GameState logic

    This keeps:
        - Units = pure domain objects
        - GameState = pure state
        - Context = execution environment

    -------------------------------------------------------------------------
    🚀 CURRENT USAGE
    -------------------------------------------------------------------------
    - Ranged combat:
        → terrain modifiers
    - Next step:
        → LOS computation
    - Future:
        → pathfinding, reaction triggers, visibility

    -------------------------------------------------------------------------
    ❗ IMPORTANT RULE
    -------------------------------------------------------------------------
    ExecutionContext MUST NEVER be stored inside GameState.

    It is ephemeral and tied to a specific execution step.
    """

    def __init__(
        self,
        *,
        event_bus: Optional[object] = None,
        game_map: Optional[object] = None,
    ):
        """
        Initialize ExecutionContext.

        Parameters:
        ---------------------------------------------------------------------
        event_bus : Optional
            Event bus used to emit ACTION_EFFECT and other debug/trace events.

        game_map : Optional
            Map instance used for:
                - Terrain lookup
                - LOS calculation
                - Spatial queries

            Expected interface:
                game_map.get_hex(position) → Hex
        """
        self.event_bus = event_bus
        self.game_map = game_map
