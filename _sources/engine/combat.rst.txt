Attack Types Overview
=====================

The combat system is composed of several distinct attack types.
Each attack type represents a different tactical situation and is
implemented using the same architectural pattern:

- Mechanics (resolver)
- Rules (action)
- Map effects (executor)

This allows attack types to share core logic while remaining
independent, testable, and extensible.

Close Combat (Assault)
----------------------

Close combat represents direct engagement between adjacent units.

Characteristics:

- Units must be adjacent
- Combat is resolved in one or more rounds
- Outcomes may include retreat, advance, or stalemate
- Map position is modified as a result of the combat

This attack type is fully implemented.

Direct Ranged Fire (DRF)
------------------------

Direct ranged fire represents planned firing at a distance.

Characteristics:

- Requires a target within weapon range
- Requires line of sight (currently minimal)
- Resolved in a single step (no rounds)
- May cause damage and suppression
- Does not move units on the map

This attack type is implemented with a minimal visibility model.

Reaction / Opportunity Fire
---------------------------

Reaction fire represents automatic firing triggered by enemy actions,
such as movement, retreat, or advance.

Characteristics:

- Not initiated as a player action
- Triggered by other actions
- Uses Direct Ranged Fire mechanics
- May involve multiple reacting units
- Never allows self-targeting

This attack type is implemented as a trigger system layered on top of
Direct Ranged Fire.

Reaction Fire and ZOC Integration
---------------------------------

Reaction Fire is spatially gated by Zones of Control (ZOC).

A unit only triggers Reaction / Opportunity Fire if it is located
inside an enemy Zone of Control.

This means:

- Reaction Fire never occurs at arbitrary distance
- Reaction Fire represents close-range tactical threat
- Zones of Control act as the spatial condition for reaction triggers

The actual firing resolution is still performed using Direct Ranged Fire
mechanics.

ZOC affects *when* reaction fire may occur, not *how* combat is resolved.

Indirect Fire (Planned)
-----------------------

Indirect fire represents artillery and mortar attacks.

Characteristics:

- Does not require direct line of sight
- May affect an area rather than a single unit
- Typically does not cause unit movement

This attack type is planned but not yet implemented.

Design Notes
------------

Attack types do not implement movement directly.
All positional effects are handled at the execution layer.

Spatial rules such as Zones of Control (ZOC) influence when attacks
may occur but do not constitute attack types themselves.


Basic Movement
==============

Definition
----------

Basic movement allows a unit to move from its current hex to a single
adjacent hex using one action.

Movement is intentionally minimal at this stage of development and is
designed to support simulation, testing, and AI training rather than
full tactical realism.

Movement Rules
--------------

A unit may move to a target hex if all of the following conditions are met:

- The target hex exists on the map
- The target hex is adjacent to the unit’s current position
- The target hex is not occupied
- The terrain of the target hex is passable

Terrain passability is determined by terrain properties rather than
terrain names. Hexes with very high movement cost (for example, water)
are considered non-passable.

Movement is atomic: one action moves the unit exactly one hex.

Interaction with Other Systems
------------------------------

Basic movement interacts with other systems but does not implement their rules.

- Zones of Control (ZOC) are evaluated after movement
- Reaction / Opportunity Fire may be triggered if the unit ends its
  movement inside an enemy Zone of Control
- No direct combat resolution occurs as part of movement itself

This separation ensures that movement remains deterministic and simple,
while other systems react to movement through well-defined triggers.

Design Rationale
----------------

Movement is implemented as a minimal action in order to:

- Enable turn-based simulation
- Enable reinforcement learning environments
- Support perception-based agents (e.g. visual input via YOLO)
- Avoid premature complexity in pathfinding or cost calculation

More advanced features such as movement points, accumulated terrain
costs, forced stops inside ZOC, or pathfinding are explicitly out of
scope for this stage and will be introduced incrementally.

Current Status
--------------

Basic movement is fully implemented with the following properties:

- One-hex movement per action
- Terrain-based passability
- Integration with ZOC and Reaction Fire
- Deterministic execution and test coverage


Assault Rules
=============

Definition
----------

An assault represents close-quarters combat between two adjacent units.
It is resolved through one or more close combat rounds.

Assault Flow
------------

1. Resolve close combat rounds.
2. Stop when a unit is eliminated or when the maximum number of rounds is reached.
3. Apply post-assault consequences.

Outcomes
--------

Defender Eliminated
^^^^^^^^^^^^^^^^^^^

- Defender is removed from the game.
- Attacker may advance into the defender’s original hex.

Attacker Eliminated
^^^^^^^^^^^^^^^^^^^

- Attacker is removed.
- Defender holds position.

Both Eliminated
^^^^^^^^^^^^^^^

- Both units are removed.
- The hex becomes empty.

Defender Retreats
^^^^^^^^^^^^^^^^^

Conditions:

- Both units survive the assault.
- At least one effective hit occurred during the assault.

Effects:

- Defender must retreat to an adjacent free hex.
- If no retreat hex exists, the defender is eliminated.
- Attacker may advance.

Stalemate
^^^^^^^^^

Conditions:

- Both units survive.
- No effective hits occurred in any round.

Effects:

- No retreat occurs.
- No advance occurs.
- Units remain in place.

Design Rules
------------

- Retreat is never forced without combat pressure.
- Advance always targets the defender’s original position.
- Spatial movement is handled by the executor, not by combat logic.


Current Development Status
==========================

Completed:

- Close combat mechanics with deterministic RNG
- Assault rules including retreat, advance, and stalemate
- AssaultExecutor applying results to the hex map
- Direct Ranged Fire (DRF)
- Reaction / Opportunity Fire
- Zone of Control (ZOC) minimal implementation
- ZOC-gated Reaction Fire
- Advanced retreat logic (direction, ZOC, terrain)
- Basic movement
- Full deterministic test coverage
- Sphinx documentation for architecture and combat rules

Design Notes:

- Retreat occurs only if there is actual combat pressure
- Stalemate occurs when no effective hits happen
- Advance always targets the defender’s original hex
- Rules never move units directly; executors do

Next Steps
----------

- Integrate movement and combat into a turn runner
- Create a minimal training environment (Gym / PettingZoo)
- Add minimal renderer for debugging and perception-based agents
- Introduce Line of Sight (LOS) once agents are active
- Refine ZOC rules (suppression, unit type modifiers)


Stopping Point
--------------

We are currently at **D8‑B**.

The tactical core of the engine is complete and stable:

- All tests are green
- Movement, combat, reaction, ZOC and retreat are integrated
- Architecture cleanly separates rules, execution, and spatial queries
- The system is ready for simulation, visualization and learning environments

Architecture recap:

- ``CloseCombatResolver`` → combat mechanics
- ``AssaultAction`` → combat rules
- ``MovementAction`` → movement rules
- ``Executors`` → map application
