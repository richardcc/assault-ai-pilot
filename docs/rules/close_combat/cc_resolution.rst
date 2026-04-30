Close Combat Resolution
=======================

This document specifies how Close Combat is resolved once it has been initiated.
The rules in this section are normative and define the exact procedure used
by the game engine to resolve close combat rounds.

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

- ``/assault_model/actions/combat/CloseCombatAction.py``
- ``/assault_model/core/game_state_runtime/RuntimeGameState.py``

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

- ``/assault_model/actions/combat/CloseCombatAction.py``

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

- ``/assault_model/core/game_state_runtime/RuntimeGameState.py``

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

- ``/assault_model/actions/resolution/ActionResolutionResult.py``

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

Notes and Constraints
---------------------

- Close Combat resolution is owned exclusively by the runtime rule engine.
- Player actions do not directly resolve combat effects.
- ``GameState`` remains immutable during a Close Combat round and is updated
  only through resolution results.

---

Next Sections
-------------

Subsequent sections define:

- How attack sectors are determined (``cc_attack_sectors.rst``)
- Special cases and modifiers (``cc_special_cases.rst``)
- Retreat, fallback, and elimination details (``cc_retreat_and_elimination.rst``)