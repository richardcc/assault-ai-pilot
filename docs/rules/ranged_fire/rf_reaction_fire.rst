Reaction Fire
=============

This document specifies when and how Reaction Fire is triggered and resolved.

Derived from *Assault Rulebook v2.0* §10.4.

---

RF-R06 — Reaction Fire Trigger
------------------------------

**Source:** Rulebook §10.4  
**Type:** Core Rule

### Condition

A non-active unit observes an enemy unit performing a triggering action
within its reaction conditions.

### Effect

- A Reaction Fire action may be generated.

### Implementation

- ``/assault_model/actions/reaction_fire/ReactionFireAction.py``
- ``/assault_model/core/game_state_reactions/GameStateReactions.py``

---

RF-R07 — Reaction Fire Resolution
--------------------------------

**Source:** Rulebook §10.4  
**Type:** Core Rule

### Rule

Reaction Fire is resolved as a normal Ranged Fire attack with any applicable
reaction modifiers.

---

RF-R08 — Reaction Fire Limits
-----------------------------

**Source:** Rulebook §10.4  
**Type:** Restriction

### Rule

- A unit may only perform Reaction Fire if eligible
- Reaction Fire is suppressed during Close Combat initiation

---

RF-R09 — Priority and Ordering
-------------------------------

**Source:** Rulebook §10.4  
**Type:** Core Rule

### Rule

Reaction Fire is resolved immediately when triggered, before the original
action completes.