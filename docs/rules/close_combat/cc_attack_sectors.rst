Attack Sectors in Close Combat
==============================

This document defines how the attack sector is determined during Close Combat
and how it affects combat resolution.

These rules are derived from *Assault Rulebook v2.0* §11.3.

Overview
--------

In Close Combat, the relative position and facing of the attacking unit
determines the **attack sector**. The sector influences attack and defense
values and may enable special modifiers or restrictions.

Attack sectors are determined **at the start of each Close Combat round**.

---

CC-R07 — Definition of Attack Sectors
-------------------------------------

**Source:** Rulebook §11.3  
**Type:** Core Rule

### Rule

The following attack sectors are defined:

- **FRONT**
- **FLANK LEFT**
- **FLANK RIGHT**
- **REAR**

No other attack sector definitions are valid.

### Notes

- There is no generic or undirected *FLANK* sector.
- Left and right flanks are distinct and must be evaluated independently.

### Implementation

- ``/assault_model/map/combat_geometry.py``
- ``determine_attack_sector(attacker, defender)``

---

CC-R08 — Sector Determination
-----------------------------

**Source:** Rulebook §11.3  
**Type:** Core Rule

### Condition

A Close Combat round is about to be resolved.

### Procedure

1. Identify the facing of the defending unit.
2. Identify the hex from which the attacking unit enters or attacks.
3. Determine the relative direction between attacker and defender.
4. Map the relative direction to one of the valid attack sectors.

### Effect

- The attack sector for the current round is established.
- Sector-dependent modifiers may be applied during combat resolution.

### Constraints

- Sector determination is purely geometric.
- Unit status, strength, or combat results do not influence sector selection.

---

CC-R09 — Sector Immutability Within a Round
-------------------------------------------

**Source:** Rulebook §11.3  
**Type:** Core Rule

### Rule

Once determined, the attack sector remains **fixed for the entire Close Combat
round**.

### Effect

- All attack and defense calculations for the round use the same sector.
- Sector changes may only occur between rounds, if permitted by rules.

---

CC-R10 — Sector Reevaluation Between Rounds
-------------------------------------------

**Source:** Rulebook §11.3  
**Type:** Core Rule

### Rule

At the start of a new Close Combat round, the attack sector may be reevaluated
if the relative facing or position of the units has changed.

### Notes

- If no facing or positional change occurred, the sector remains unchanged.
- Rules governing facing changes are defined elsewhere.

---

CC-R11 — Rear Attacks
---------------------

**Source:** Rulebook §11.3  
**Type:** Special Case

### Condition

The attack sector is determined to be **REAR**.

### Effect

- Rear attack modifiers are applied as defined in the relevant combat rules.
- Certain defensive bonuses may be ignored.

### Implementation Note

Exact modifiers are defined in the Close Combat modifiers section
(see ``cc_special_cases.rst``).

---

Constraints and Invariants
--------------------------

- Attack sector determination does not modify game state.
- Sector logic is deterministic and side-effect free.
- The same inputs must always produce the same sector.

Attack sector logic must not:

- Apply combat modifiers directly
- Remove or modify units
- Trigger reactions

---

Next Section
------------

The next document defines special cases and modifiers applied during Close
Combat resolution:

- ``cc_special_cases.rst``
