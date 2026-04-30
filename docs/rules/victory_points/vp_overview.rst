Victory Points Overview
=======================

This section documents the **Victory Points (VP)** subsystem of the Assault
game engine.

Victory Points represent scenario-defined objectives that contribute to the
final outcome of a battle or campaign. While the *value* of each objective
may vary between scenarios, the **mechanics governing occupation, control,
and evaluation of Victory Points are consistent across all campaigns**.

Scope
-----

This subsystem defines:

- How Victory Points are defined by scenarios.
- How hex control is resolved at the end of each turn.
- When and how Victory Points are awarded.
- How contested objectives are handled.

Victory Points are **never awarded immediately upon movement**. Instead, they
are evaluated during turn resolution, based on the final, consolidated state
of the battlefield.

Canonical Evaluation Point
--------------------------

Victory Point evaluation occurs at a **single, canonical point** in the
engine lifecycle:

- ``assault_model.core.game_state.GameState.end_turn``

During turn finalization, the game state is consolidated by:

1. Resolving unit presence per hex.
2. Determining exclusive ownership or contest status.
3. Applying Victory Point scoring based on resolved hex ownership.

No other subsystem evaluates or awards Victory Points.

Architectural Placement
-----------------------

The Victory Points subsystem spans the following layers:

- **Scenario Definition**
  - Victory Point locations and values, defined per scenario.

- **State Resolution**
  - Hex ownership and contest status are resolved at end of turn.
  - Resolution is based on consolidated unit positions.

- **Scoring**
  - Victory Points are accumulated per side based on resolved hex control.

Key runtime classes involved include:

- ``assault_model.core.victory_conditions.VictoryConditions``
- ``assault_model.core.victory_point.VictoryPoint``
- ``assault_model.core.vp_tracker.VictoryPointTracker``
- ``assault_model.map.hex_state.HexState``
- ``assault_model.map.hex_ownership.HexOwnership``
- ``assault_model.core.game_state.GameState``

Hex State Consolidation
----------------------

Hex control is determined during turn resolution and stored as consolidated
state.

- ``HexState`` acts as a passive container for resolved hex status.
- ``HexState`` does **not** calculate ownership or contest.
- Ownership resolution is performed by ``GameState.end_turn``.

The resulting ownership state is exposed through ``HexOwnership`` enums and
consumed by the Victory Point scoring system.

Non-Responsibilities
--------------------

The Victory Points subsystem does **not**:

- Decide movement or combat.
- Trigger combat automatically.
- Influence unit activation.
- Encode strategic intent.
- Inspect or evaluate units directly.

Those concerns are handled by other subsystems and are documented elsewhere.