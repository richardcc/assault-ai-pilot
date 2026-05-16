P2 – Multi‑Unit VP Pressure
==========================

This scenario extends the baseline VP mission to **multiple friendly units**.

The goal is not micromanagement, but **force management and sustained
objective pressure**.

---

Configuration
-------------

Units
^^^^^

- Italy (PPO): 2 units
- Enemy (heuristic): 1 unit

Only friendly forces are increased to avoid introducing symmetric
coordination complexity.

---

Victory Points
--------------

Victory Points are identical to the P1 baseline:

========== ==========
VP         Coordinates
========== ==========
D5         (3,4)
F6         (5,5)
C9         (2,8)
========== ==========

Each VP remains worth 2 points.

---

Design Intent
-------------

This scenario introduces **strategic force usage**:

- One unit may contest VP while the other repositions
- Damaged units can be rotated out
- VP pressure can be maintained without suicidal tactics

The agent must learn **when to commit which unit**, not just where to go.

---

Enemy Behavior
--------------

The enemy remains VP‑aware and deterministic.

- Moves to recapture controlled VP
- Assaults whenever legally possible

Enemy strength is intentionally unchanged to preserve challenge.

---

Mission Outcome
---------------

Mission outcome is evaluated at end of time.

- ≥ 4 VP → Victory
- = 3 VP → Draw
- ≤ 2 VP → Defeat

Defeat remains a valid outcome.

---

Curriculum Justification
------------------------

Only **one new dimension** is introduced relative to P1:  
**multiple friendly units**.

- Victory Points unchanged
- Enemy behavior unchanged
- Reward structure unchanged

This preserves curriculum integrity and learning stability.

---

Status
------

P2 is an **active development scenario**.

It must not modify or replace the P1 baseline.