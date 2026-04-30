Tactical Movement Overview
==========================

This section documents the **Tactical Movement** subsystem of the Assault
game engine.

Tactical Movement governs how units are repositioned on the map during play,
including:

- When a unit is allowed to move.
- Which movements are legal.
- How movement consumes activations.
- How movement interacts with turn sequencing.
- How movement positions units to satisfy Victory Conditions.

This documentation is derived directly from the official Assault rulebook
and mapped to the runtime implementation.

Movement is executed through *actions* and *never* modifies the game state
directly. All rule enforcement occurs during action resolution.

Architectural Placement
-----------------------

Tactical Movement spans the following architectural layers:

- **Intent Layer**
  - ``MoveAction`` (player-visible action)

- **Execution Layer**
  - ``RuntimeGameState.apply_action``

- **State Layer**
  - ``GameState``
  - ``ActivationState``
  - ``TurnState``

- **Support Systems**
  - ``ActionCatalog`` (legal move generation)
  - ``VictoryPointTracker`` (movement positioning only)

Non-Responsibilities
--------------------

The Tactical Movement subsystem does **not**:

- Resolve combat.
- Award Victory Points.
- Evaluate control of objectives.
- Select targets.
- Perform pathfinding heuristics beyond legal move generation.

These behaviors belong to other subsystems and are documented elsewhere.