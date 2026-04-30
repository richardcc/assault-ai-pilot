Engine Overview
===============

This document defines the **purpose, role, and boundaries** of the Assault game engine.

Engine Purpose
--------------

The engine exists to answer one fundamental question:

**Given a game state, a set of rules, and an action, what is the next game state?**

All engine design decisions follow from this premise.

Engine Responsibilities
-----------------------

The engine is responsible for:

- defining simulation entities
- enforcing rules and constraints
- resolving state transitions deterministically
- producing authoritative game states

The engine is NOT responsible for:

- visualization
- rendering
- user interfaces
- asset selection

These responsibilities belong to external consumer layers.

Engine Boundaries
-----------------

The engine is a closed system with:

- explicit inputs (scenarios, actions)
- deterministic execution
- explicit outputs (replays, states)

External systems must adapt to the engine output, never the reverse.