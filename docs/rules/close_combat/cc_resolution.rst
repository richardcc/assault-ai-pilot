Close Combat Resolution
=======================

This document specifies how Close Combat is resolved once it has been initiated.
The rules in this section are normative and define the exact procedure used
by the game engine to resolve Close Combat rounds.

All rules are derived from *Assault Rulebook v2.0* §11.1.

Overview
--------

Close Combat is resolved through one or more **simultaneous combat rounds**.
During each round, both sides inflict damage at the same time based on their
respective attack and defense values.

A Close Combat continues until one of the following conditions is met:

- One or both units are eliminated
- A unit is forced to retreat or fallback
- A rule explicitly ends the combat

---

CC-R01 — Start of Close Combat Resolution
-----------------------------------------

**Source:** Rulebook §11.1  
**Phase:** Action Phase  
**Type:** Core Rule

### Condition

A Close Combat has been initiated between two opposing units occupying the same
hex.

### Procedure

1. Identify the two engaged units:
   - The **attacking unit** (active unit)
   - The **defending unit** (non-active unit)
2. Determine the attack sector for the attacking unit.
3. Resolve a Close Combat round following rules CC-R02 through CC-R06.

### Effect

- A Close Combat round is executed.
- Both units may suffer losses or be eliminated.
- If both units survive, another Close Combat round may be resolved.

### Implementation

- ``/assault_model/actions/assault/AssaultAction.py``  
- ``/assault_model/combat/close_combat_resolver.py``  

---

CC-R02 — Simultaneous Resolution
--------------------------------

**Source:** Rulebook §11.1  
**Type:** Core Rule

### Rule

All combat effects in Close Combat are applied **simultaneously**.

### Consequences

- Damage inflicted by either unit is calculated before applying any elimination.
- A unit that is eliminated still inflicts its damage for the current round.
- Mutual destruction is possible.

### Implementation

- ``/assault_model/combat/close_combat_resolver.py``  

---

CC-R03 — Multiple Rounds
------------------------

**Source:** Rulebook §11.1  
**Type:** Core Rule

### Rule

If both units remain in the same hex and neither is eliminated after a
Close Combat round, another Close Combat round may be resolved.

### Notes

- Close Combat may span multiple rounds within the same action.
- The exact continuation or termination conditions are defined by subsequent
  rules (see CC-R05, CC-R06).

### Implementation

- ``/assault_model/combat/close_combat_resolver.py``  

---

CC-R04 — Elimination Check Timing
---------------------------------

**Source:** Rulebook §11.1  
**Type:** Core Rule

### Rule

Unit elimination checks are performed **only after** all simultaneous combat
effects of the round have been applied.

### Effect

- No unit is removed from play during damage calculation.
- Elimination is a post-round step.

### Implementation

- ``/assault_model/combat/close_combat_resolver.py``  

---

CC-R05 — Mutual Destruction
---------------------------

**Source:** Rulebook §11.1  
**Type:** Special Case

### Condition

Both units meet the elimination criteria after a Close Combat round.

### Effect

- Both units are removed from play.
- The Close Combat immediately ends.

### Implementation

- ``/assault_model/combat/close_combat_resolver.py``  

---

CC-R06 — End of Close Combat
----------------------------

**Source:** Rulebook §11.1  
**Type:** Core Rule

### Rule

A Close Combat ends when:

- One unit is eliminated
- Both units are eliminated
- A rule forces a retreat or fallback

### Effect

- The Close Combat state is cleared.
- The hex is no longer considered a Close Combat hex.

---

Execution Model Clarification
-----------------------------

Close Combat resolution is executed exclusively by the combat resolver.

Responsibilities are split as follows:

- ``AssaultAction`` declares the intent to initiate Close Combat.
- ``close_combat_resolver`` executes all combat rounds, rolls dice, applies
  simultaneous effects, determines elimination and outcome.
- ``RuntimeGameState`` orchestrates action sequencing and turn progression
  but does **not** resolve Close Combat logic and does **not** emit combat results.

---

Domain Event Contract
---------------------

Each resolved Close Combat produces a domain event of type ``ACTION_EFFECT``
with ``action == "CloseCombat"``.

This event is the single authoritative representation of the resolved
Close Combat round and includes:

- Attacker and defender unit identifiers
- Final round attack and defense dice results
- Hit points before and after the round
- Combat outcome and winner

The runtime engine MUST NOT emit a ``COMBAT_RESULT`` event for Close Combat.
All presentation layers and observers MUST consume the ``ACTION_EFFECT`` event
when rendering Close Combat.

---

Notes and Constraints
---------------------

- Close Combat resolution is owned exclusively by the combat resolver.
- Player actions declare intent but do not directly resolve combat effects.
- ``GameState`` is not mutated during effect calculation within a round; state
  updates are applied only after the round is fully resolved.
- Runtime orchestration code must not reconstruct or duplicate Close Combat
  results.

---

Next Sections
-------------

Subsequent sections define:

- How attack sectors are determined (``cc_attack_sectors.rst``)
- Special cases and modifiers (``cc_special_cases.rst``)
- Retreat, fallback, and elimination details (``cc_retreat_and_elimination.rst``)