Architecture Overview
=====================

Core Design Principles
----------------------

The Assault Engine is built around a strict separation of concerns.

- Mechanics resolve combat effects.
- Rules interpret combat and decide outcomes.
- State stores map and unit data.
- Executors apply rules to the map.

This separation ensures determinism, testability, and clean extensibility.

---

Layered Architecture
--------------------

Mechanics Layer
^^^^^^^^^^^^^^^

Pure, stateless logic.

- ``CloseCombatResolver``
- Dice resolution
- Hit cancellation
- Damage application

This layer has no knowledge of map, turns, or unit positions.

---

Rule Layer
^^^^^^^^^^

High-level game rules.

- ``AssaultAction``
- Multiple close combat rounds
- Stalemate detection
- Retreat and advance decisions

This layer does not move units on the map.

---

State Layer
^^^^^^^^^^^

The single source of truth.

- ``GameState``
- ``Hex``
- ``Unit``

This layer stores data but does not implement rules.

---

Execution Layer
^^^^^^^^^^^^^^^

Applies rules to the map.

- ``AssaultExecutor``

This is the only layer allowed to move or remove units.

---

Determinism
-----------

All randomness is injected via ``random.Random``.
Global randomness is forbidden in the engine.
