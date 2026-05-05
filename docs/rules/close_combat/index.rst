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
  Declares the intent to initiate a Close Combat through an assault.

- Combat resolution (domain logic):
  - ``/assault_model/combat/close_combat_resolver.py``  
  Owns the complete Close Combat resolution process, including:
  
  - Combat round execution
  - Dice rolling
  - Simultaneous effect application
  - Hit point tracking
  - Elimination and outcome determination
  - Emission of the Close Combat domain event

- State orchestration and turn progression:
  - ``/assault_model/runtime/game_state_runtime.py``  
  Orchestrates action sequencing, activation consumption, and turn
  progression, but does **not** resolve Close Combat logic and does **not**
  emit Close Combat results.

The ``GameState`` itself remains a passive data structure and does not
contain combat logic.

Domain Event Contract
---------------------

A resolved Close Combat produces a domain event of type ``ACTION_EFFECT``
with ``action == "CloseCombat"``.

This event is the authoritative, single-source representation of a resolved
Close Combat and contains, at minimum:

- Attacker and defender unit identifiers
- Final round attack and defense dice results
- Hit points before and after the round
- Combat outcome and winner

The runtime engine MUST NOT emit a ``COMBAT_RESULT`` event for Close Combat.
Presentation layers and observers MUST exclusively consume the
``ACTION_EFFECT`` event when rendering Close Combat.

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
