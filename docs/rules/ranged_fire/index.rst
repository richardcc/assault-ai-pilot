Ranged Fire
===========

This section formalizes the Ranged Fire rules as defined in the
*Assault Rulebook v2.0 (18/09/2024)*.

Ranged Fire represents combat resolved at distance using direct or indirect
fire actions. It includes standard attacks, reaction fire, and all distance-
based modifiers and restrictions.

All rules in this section are executable specifications and are traceable to
the corresponding implementation in the codebase.

Scope
-----

This section covers:

- Direct ranged fire resolution
- Indirect fire resolution
- Reaction Fire (Opportunity Fire)
- Line of sight and range constraints
- Special cases and modifiers

Architectural Context
---------------------

Ranged Fire rules are implemented across the following subsystems:

- Player actions:
  - ``/assault_model/actions/ranged_direct/RangedDirectAttack.py``
  - ``/assault_model/actions/ranged_indirect/RangedIndirectAttack.py``

- Reaction fire handling:
  - ``/assault_model/actions/reaction_fire/ReactionFireAction.py``
  - ``/assault_model/core/game_state_reactions/GameStateReactions.py``

- Rule execution and state mutation:
  - ``/assault_model/core/game_state_runtime/RuntimeGameState.py``

Rule Identification
-------------------

Rules in this section use the **RF-Rxx** identifier prefix.

Contents
--------

.. toctree::
   :maxdepth: 2

   rf_resolution
   rf_reaction_fire
   rf_special_cases
