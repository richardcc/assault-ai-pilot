Close Combat
============

This section formalizes the Close Combat rules as defined in the
*Assault Rulebook v2.0 (18/09/2024)*.

Close Combat represents a distinct resolution subsystem triggered by an
assault action and resolved through one or more simultaneous combat rounds.
All rules in this section are executable specifications and are traceable
to the corresponding implementation in the codebase.

Scope
-----

This section covers:

- Initiation of Close Combat
- Resolution of combat rounds
- Determination of attack sectors
- Special cases and modifiers
- Retreat, fallback, and elimination

Architectural Context
---------------------

Close Combat rules are implemented across the following subsystems:

- Player intention:
  - ``/assault_model/actions/assault/AssaultAction.py``

- Internal combat resolution:
  - ``/assault_model/actions/combat/CloseCombatAction.py``

- Rule execution and state mutation:
  - ``/assault_model/core/game_state_runtime/RuntimeGameState.py``

The ``GameState`` itself remains a passive data structure and does not
contain combat logic.

Rule Identification
-------------------

Rules in this section use the **CC-Rxx** identifier prefix.

Example::

   CC-R01 — Close Combat Initiation
   CC-R04 — Initial Attack Modifiers

These identifiers are referenced consistently in:

- Documentation
- Code comments
- Automated tests

Contents
--------

.. toctree::
   :maxdepth: 2

   cc_overview
   cc_resolution
   cc_attack_sectors
   cc_special_cases
   cc_retreat_and_elimination