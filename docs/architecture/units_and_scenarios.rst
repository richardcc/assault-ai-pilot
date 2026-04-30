Units and Scenarios
===================

This document defines the **static semantic inputs** of the Assault game engine:
**units** and **scenarios**.

Together, they provide all the information required to construct the
**initial game state** and begin execution.

---

1. Role of Units and Scenarios
------------------------------

Units and scenarios define the **what** and the **starting conditions**
of the simulation.

- Units define **who can act**
- Scenarios define **where, when, and under which constraints** the game starts

Neither of them is responsible for execution logic.
That role belongs exclusively to the engine runtime
(described in :doc:`execution_model`).

---

2. Unit Model
-------------

Units are the primary semantic entities within the engine.

A unit is a **pure simulation object** and contains no presentation data.

### Canonical unit structure

Each unit includes:

- a unique identifier (``unit_id``)
- a unit type (reference to unit definition)
- experience level
- combat attributes
- current strength
- map position
- internal status flags

Unit definitions describe **capabilities**,
while unit instances represent **stateful entities** inside a game state.

---

3. Scenario Model (Engine Entry Point)
--------------------------------------

The **scenario is the entry point of engine execution**.

No game execution can occur without a scenario.

A scenario is a **pure data specification** that defines the complete
initial conditions of a game.

### Scenario definition includes

A scenario explicitly defines:

- the set of participating units
- the initial position of each unit
- the map layout and terrain configuration
- scenario-specific constraints
- scenario-specific objectives (if any)

The scenario does **not** contain logic.
