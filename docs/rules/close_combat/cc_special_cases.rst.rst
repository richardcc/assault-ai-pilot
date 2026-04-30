Special Cases and Modifiers in Close Combat
===========================================

This document defines special cases, restrictions, and modifiers that apply
during Close Combat resolution.

These rules are derived from *Assault Rulebook v2.0* §11.4 and §11.5.

The rules in this section modify or constrain the standard Close Combat
resolution procedure defined in ``cc_resolution.rst``.

---

CC-R12 — No Reaction Fire
-------------------------

**Source:** Rulebook §11.4  
**Type:** Restriction

### Rule

No Reaction Fire may be triggered when a unit enters a hex occupied by an enemy
unit and initiates Close Combat.

### Effect

- Reaction Fire actions are suppressed.
- The Close Combat proceeds directly to resolution.

### Implementation

- ``/assault_model/actions/reaction_fire/ReactionFireAction.py``
- ``/assault_model/core/game_state_reactions/GameStateReactions.py``

---

CC-R13 — Fallback Units
-----------------------

**Source:** Rulebook §11.4  
**Type:** Special Case

### Condition

The defending unit is in **Fallback** status at the moment Close Combat is
initiated.

### Effect

- The defending unit is immediately eliminated.
- No Close Combat rounds are resolved.

### Implementation

- ``/assault_model/core/game_state_runtime/RuntimeGameState.py``

---

CC-R14 — Infantry vs Vehicles
-----------------------------

**Source:** Rulebook §11.5  
**Type:** Special Case

### Rule

When Infantry units engage Vehicles in Close Combat, special resolution rules
apply.

### Constraints

- Only eligible Infantry units may attack Vehicles in Close Combat.
- Certain Vehicles may be immune or partially immune to Close Combat attacks.

### Notes

Exact attack and defense values are defined by unit attributes and rulesets.

### Implementation

- ``/assault_model/units/unit_type/UnitType.py``
- ``/assault_model/rulesets/``

---

CC-R15 — Multiple Units in a Hex
--------------------------------

**Source:** Rulebook §11.4  
**Type:** Restriction

### Rule

Once Close Combat is initiated, the hex is considered a **Close Combat hex**.

### Effect

- Only one unit per side may occupy the hex.
- Additional units may not enter the hex until Close Combat ends.

### Implementation

- ``/assault_model/map/hex_state/HexState.py``

---

CC-R16 — Artillery Restrictions
--------------------------------

**Source:** Rulebook §11.5  
**Type:** Restriction

### Rule

Artillery units may not initiate Close Combat.

### Effect

- Any AssaultAction issued by an Artillery unit is invalid.
- The action must be rejected during action validation.

### Implementation

- ``/assault_model/actions/assault/AssaultAction.py``
- ``/assault_model/units/unit_type/UnitCategory.py``

---

CC-R17 — Modifier Application Order
-----------------------------------

**Source:** Rulebook §11.4  
**Type:** Core Rule

### Rule

All applicable Close Combat modifiers are applied **before** resolving combat
effects for the round.

### Order

1. Base attack and defense values
2. Sector-based modifiers
3. Unit-type modifiers
4. Special case modifiers

### Effect

- The final combat values are established before damage resolution.

### Implementation

- ``/assault_model/actions/combat/CloseCombatAction.py``

---

Constraints
-----------

The rules in this section:

- Modify the standard Close Combat procedure
- Do not initiate combat independently
- Must not override simultaneous resolution

No special case may:

- Cancel simultaneous damage application
- Cause partial resolution of a combat round

---

Next Section
------------

The next document specifies retreat, fallback, and elimination handling in Close
Combat:

- ``cc_retreat_and_elimination.rst``
