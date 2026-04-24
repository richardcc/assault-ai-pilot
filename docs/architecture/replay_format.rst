Replay Format – Engine to Viewer Contract
=========================================

This document defines the **Replay format** used to represent a fully resolved
game simulation produced by an agent and executed by the engine.

The Replay acts as a **read‑only, immutable description of world evolution**.
It is the only structure consumed by the viewer for visualization and debugging.

------------------------------------------------------------

1. Purpose of the Replay
------------------------

The Replay exists to:

- Visualize a game already solved by an agent
- Debug decisions made by the agent
- Inspect engine behavior step by step
- Enable deterministic reproduction of simulations

The Replay **does not**:

- Contain game logic
- Validate rules
- Execute actions
- Provide interactivity

------------------------------------------------------------

2. Architectural Principle
--------------------------

**Three strict roles are enforced:**

- The **Engine** decides and mutates live state
- The **Replay** describes immutable snapshots
- The **Viewer** renders snapshots without logic

Violating this separation leads to fragile systems and coupled bugs.

------------------------------------------------------------

3. Replay Structure Overview
----------------------------

A Replay is defined as an **ordered sequence of immutable states**.

::

    Replay
        └── states: List[ReplayState]

Each element represents the full world state at a given simulation step.

------------------------------------------------------------

4. ReplayState (World Snapshot)
-------------------------------

A ReplayState is a frozen, self‑contained description of the game world.

It must not reference engine objects or mutable state.

::

    @dataclass(frozen=True)
    class ReplayState:
        turn: int
        active_player: str
        units: tuple[UnitState, ...]

------------------------------------------------------------

5. UnitState
------------

Each unit visible in the world is represented by a UnitState.

::

    @dataclass(frozen=True)
    class UnitState:
        unit_id: str
        side: str
        hex: str
        strength: int
        status: str

Notes:

- ``hex`` is stored as a string (e.g. "A9")
- World‑to‑grid mapping is handled by the viewer
- No engine references are allowed

------------------------------------------------------------

6. Snapshot Creation
--------------------

Snapshots are created by **extracting data from the engine state** after each
simulation step.

This process must:

- Allocate new objects
- Avoid sharing references
- Preserve chronological order

::

    def snapshot(engine_state) -> ReplayState:
        return ReplayState(
            turn=engine_state.turn,
            active_player=engine_state.active_player,
            units=tuple(
                UnitState(
                    unit_id=str(unit.id),
                    side=unit.side,
                    hex=str(unit.hex),
                    strength=unit.strength,
                    status=unit.status.name,
                )
                for unit in engine_state.units
            ),
        )

Snapshots must be created:

- After reset (initial state)
- After each engine step
- Never mutated afterward

------------------------------------------------------------

7. Responsibilities and Restrictions
-------------------------------------

Engine
^^^^^^

- Owns mutable game state
- Applies actions
- Advances turns
- Produces snapshots

Replay
^^^^^^

- Stores immutable state history
- Contains no behavior
- Contains no logic
- Is safe to serialize

Viewer
^^^^^^

- Reads ReplayState objects
- Renders grid, terrain, and units
- Never mutates state
- Never infers rules

------------------------------------------------------------

8. Determinism and Debugging
----------------------------

Because ReplayStates are immutable and ordered:

- Any visual bug can be reproduced exactly
- Agent decisions can be inspected in context
- Different agents can be compared turn by turn

If a rendered state is incorrect, the bug is:

- In the engine (if data is wrong)
- Or in the viewer (if data is rendered wrong)

Never assume both.

------------------------------------------------------------

9. Forbidden Practices
----------------------

The following practices are explicitly forbidden:

- Mutating ReplayState after creation
- Storing engine objects inside replay
- Computing logic inside the viewer
- Allowing the viewer to modify game state
- Treating Replay as authoritative for rules

------------------------------------------------------------

10. Final Note
--------------

The Replay format is a **debugging and inspection tool**, not a gameplay system.

All gameplay decisions must happen **before** the Replay is produced.

✅ Status: Accepted and stable