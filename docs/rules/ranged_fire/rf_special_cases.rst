Special Cases and Modifiers in Ranged Fire
==========================================

This document defines exceptions and modifiers applied during Ranged Fire.

Derived from *Assault Rulebook v2.0* §10.5–§10.7.

---

RF-R10 — Terrain Modifiers
--------------------------

**Source:** Rulebook §10.5  
**Type:** Modifier

### Rule

Terrain may modify attack or defense values during Ranged Fire.

---

RF-R11 — Suppression Effects
----------------------------

**Source:** Rulebook §10.6  
**Type:** Special Case

### Effect

A unit hit by ranged fire may receive suppression instead of or in addition
to damage.

---

RF-R12 — Minimum Range Weapons
-------------------------------

**Source:** Rulebook §10.7  
**Type:** Restriction

### Rule

Weapons with a minimum range may not fire at targets closer than that range.

---

RF-R13 — Area Fire Weapons
--------------------------

**Source:** Rulebook §10.7  
**Type:** Special Case

### Rule

Area fire weapons may affect multiple units or hexes as defined by their
ruleset.

### Implementation

- ``/assault_model/rulesets/``

---

Constraints
-----------

- Special cases do not override simultaneous resolution
- Modifiers must be applied before resolving effects
