P2 – Multi‑Unit VP Pressure
===========================

This document records the training results and behavioral analysis of
**P2 – Multi‑Unit VP Pressure**, the second stage of the assault‑env
reinforcement learning curriculum.

P2 introduces **multiple friendly units** while keeping all other
dimensions identical to the frozen P1 baseline.

---

Scenario Overview
-----------------

- Friendly units (learning agent): 2
- Enemy units: 1 (heuristic)
- Victory Points: 3 (2 points each)
- Turn structure: alternating, sequential unit activation
- Episode length: fixed turn limit
- Mission resolution: Victory Points evaluated at episode end

The scenario is designed to represent a **pressure‑based defensive
mission**, where numerical redundancy *should* enable risk reduction.

---

Training Configuration
----------------------

- Algorithm: Proximal Policy Optimization (PPO)
- Policy: ``MultiInputPolicy``
- Total training steps: ~200,000
- Hyperparameters: identical to P1
- Reward function: unchanged from P1
- Engine: deterministic, unchanged

No curriculum shortcuts, rule changes, or hyperparameter tuning
were introduced for P2.

---

Observed Converged Behavior
---------------------------

After convergence, the learned policy consistently exhibits:

- Continuous movement activity (no WAIT loops)
- Sequential activation of both friendly units
- Persistent avoidance of the enemy
- No sustained control of victory points
- No assaults in deterministic or stochastic evaluation

This behavior is highly stable, reproducible, and insensitive to
extended training.

---

Interpretation
--------------

The converged P2 policy represents **rational permanent evasion**.

Despite having two units, the agent:

- Possesses no explicit awareness of aggregate friendly force
- Evaluates engagement risk locally and conservatively
- Prefers survival over contestation under uncertainty

Given the available information, this behavior is optimal.

---

Rotation Without Coordination
-----------------------------

Although the environment supports multiple friendly units,
the policy does **not** coordinate them strategically.

Unit rotation occurs mechanically due to turn structure, but:

- No unit commits to holding victory points
- No unit assumes a protective or aggressive role
- Units behave as independent tactical actors

Redundancy exists structurally, but not informationally.

---

Comparison with P1
------------------

Relative to P1, P2 demonstrates:

- Greater movement diversity
- Reduced immediate retreat
- Slightly increased positional tolerance

However, the fundamental conservative bias remains unchanged.

The presence of a second unit alone is insufficient to
produce strategic pressure.

---

Curriculum Role
---------------

P2 is considered:

- ✅ Structurally well‑designed
- ✅ Deterministic and reproducible
- ✅ A controlled failure
- ✅ A diagnostic curriculum stage

The failure of P2 is **intentionally preserved** rather than corrected.

It directly motivates the introduction of global force awareness
in the next curriculum stage.

---

Next Curriculum Direction
-------------------------

P2 reveals that **multi‑unit interaction without aggregate context**
is insufficient to escape conservative local optima.

This insight motivates:

- P3: global force awareness
- P4: symmetric strategic interaction