Retreat, Fallback, and Elimination in Close Combat
==================================================

This document specifies how retreat, fallback, and unit elimination are handled
during and after Close Combat resolution.

These rules are derived from *Assault Rulebook v2.0* §11.2, §11.4, and related
elimination rules.

The rules in this section are normative and must be applied strictly after
each Close Combat round.

---

CC-R18 — Post-Round Resolution Order
------------------------------------

**Source:** Rulebook §11.2  
**Type:** Core Rule

### Rule

After each Close Combat round, the following steps are executed in order:

1. Apply all simultaneous combat effects.
2. Perform elimination checks.
3. Apply retreat or fallback effects, if any.
4. Determine whether Close Combat continues or ends.

### Constraint

No step may be skipped or reordered.

---

CC-R19 — Unit Elimination
-------------------------

**Source:** Rulebook §11.2  
**Type:** Core Rule

### Condition

A unit meets its elimination criteria after a Close Combat round.

### Effect

- The unit is removed from play.
- The unit is removed from the hex.
- Any markers or temporary states associated with the unit are cleared.

### Implementation

- ``/assault_model/core/game_state_runtime/RuntimeGameState.py``

---

CC-R20 — Mutual Elimination
---------------------------

**Source:** Rulebook §11.2  
**Type:** Special Case

### Condition

Both engaged units meet elimination criteria after the same Close Combat round.

### Effect

- Both units are removed from play.
- The Close Combat immediately ends.
- The hex becomes empty.

### Notes

This rule reaffirms the simultaneous resolution principle.

---

CC-R21 — Retreat from Close Combat
----------------------------------

**Source:** Rulebook §11.4  
**Type:** Core Rule

### Condition

A unit is forced to retreat as the result of a Close Combat round and is not
eliminated.

### Procedure

1. Determine the retreat destination according to movement and map rules.
2. Move the unit to the retreat hex.
3. Apply any retreat-related status effects.

### Effect

- The retreating unit leaves the Close Combat hex.
- The Close Combat ends.

### Implementation

- ``/assault_model/core/game_state_runtime/RuntimeGameState.py``
- ``/assault_model/map/map/Map.py``

---

CC-R22 — Fallback from Close Combat
----------------------------------

**Source:** Rulebook §11.4  
**Type:** Special Case

### Condition

A unit is forced into **Fallback** as a result of Close Combat.

### Effect

- The unit exits the Close Combat.
- Fallback status is applied immediately.

### Notes

- A unit already in Fallback is eliminated when Close Combat is initiated
  (see CC-R13).
- Fallback effects beyond Close Combat are defined in the morale rules.

---

CC-R23 — Continuation of Close Combat
-------------------------------------

**Source:** Rulebook §11.2  
**Type:** Core Rule

### Condition

After a Close Combat round:

- Both units survive
- Neither unit retreats or falls back
- Both units remain in the same hex

### Effect

- A new Close Combat round may be resolved.
- Attack sector may be reevaluated (see CC-R10).

---

CC-R24 — End State of the Hex
-----------------------------

**Source:** Rulebook §11.2  
**Type:** Core Rule

### Rule

When Close Combat ends, the hex state is updated as follows:

- If one unit remains, it occupies the hex normally.
- If no units remain, the hex becomes empty.
- The hex is no longer considered a Close Combat hex.

### Implementation

- ``/assault_model/map/hex_state/HexState.py``

---

Constraints and Invariants
--------------------------

- Elimination always takes precedence over retreat and fallback.
- No unit may participate in more than one Close Combat at a time.
- Close Combat termination must be explicit and final.

Close Combat resolution must not:

- Leave units in an undefined or partial state
- Modify turn or activation state directly
- Bypass elimination checks

---

Close Combat Complete
---------------------

This document concludes the Close Combat ruleset.

The full Close Combat specification consists of:

- ``cc_overview.rst``
- ``cc_resolution.rst``
- ``cc_attack_sectors.rst``
- ``cc_special_cases.rst``
- ``cc_retreat_and_elimination.rst``