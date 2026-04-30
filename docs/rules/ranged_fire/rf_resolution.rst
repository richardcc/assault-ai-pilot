Ranged Fire Resolution
======================

This document specifies how Ranged Fire attacks are resolved.

Rules are derived from *Assault Rulebook v2.0* §10.0–§10.3.

---

RF-R01 — Declaration of Ranged Fire
-----------------------------------

**Source:** Rulebook §10.0  
**Type:** Core Rule

### Condition

An active unit declares a ranged fire action against a valid target.

### Effect

- A Ranged Fire action is created.
- Target validity is checked before resolution.

### Implementation

- ``/assault_model/actions/ranged_direct/RangedDirectAttack.py``
- ``/assault_model/actions/ranged_indirect/RangedIndirectAttack.py``

---

RF-R02 — Target Validity
------------------------

**Source:** Rulebook §10.1  
**Type:** Core Rule

### Rule

A ranged attack is valid only if:

- Target is within weapon range
- Line of sight requirements are met (direct fire only)
- Target is not restricted by terrain or rules

---

RF-R03 — Direct Fire Resolution
-------------------------------

**Source:** Rulebook §10.2  
**Type:** Core Rule

### Procedure

1. Determine attack value
2. Apply terrain and unit modifiers
3. Resolve hit and damage
4. Apply results simultaneously

### Implementation

- ``/assault_model/actions/ranged_direct/RangedDirectAttack.py``

---

RF-R04 — Indirect Fire Resolution
---------------------------------

**Source:** Rulebook §10.3  
**Type:** Core Rule

### Rule

Indirect fire:

- Does not require line of sight
- May apply scatter or deviation rules
- Uses indirect fire modifiers

### Implementation

- ``/assault_model/actions/ranged_indirect/RangedIndirectAttack.py``

---

RF-R05 — Simultaneous Effects
-----------------------------

**Source:** Rulebook §10.0  
**Type:** Core Rule

### Rule

All damage and effects from ranged fire are applied simultaneously.

---

Constraints
-----------

- Ranged Fire does not move units
- Ranged Fire does not alter turn state directly
