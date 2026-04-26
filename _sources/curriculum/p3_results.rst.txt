P3 – Global Force Awareness
===========================

This document reports the results of **P3**, the third stage
of the assault‑env curriculum.

P3 introduces **global force awareness** to resolve the
degenerate conservative behavior observed in P2.

---

Motivation
----------

In P2 (2 vs 1 without global information), the agent converged
to a safe but ineffective policy:

- constant movement
- maximum distance from the enemy
- zero assaults
- zero victory point pressure

This behavior was stable and reproducible, indicating a
**local optimum induced by incomplete information**
rather than a training failure.

---

P3 Modification
---------------

P3 adds **no reward shaping** and **no algorithmic changes**.

The only modification is extending the observation space with:

- total friendly strength
- total enemy strength

This provides global situational context while preserving
local action selection.

---

Training Results
----------------

After approximately 200k steps, the training process shows:

- explained variance stabilizing around ~0.4
- stable PPO updates (low KL divergence, controlled clipping)
- entropy reduction without policy collapse

These metrics indicate that the value function incorporates
the new information coherently.

---

Behavioral Evaluation
---------------------

Deterministic (greedy) evaluation remains conservative.

However, stochastic (non‑greedy) evaluation reveals:

- reduced average distance to enemies
- selective assaults
- intermittent victory point pressure
- non‑identical trajectories across episodes

This demonstrates that aggressive and risky behaviors
have entered the **policy distribution**, even if they are
not yet dominant under greedy execution.

---

Interpretation
--------------

P3 successfully breaks the P2 local optimum by enabling
**situational risk assessment** based on aggregate force.

However, P3 does **not** resolve coordination or dominance:

- Aggression is available but not consistently preferred
- Conservative greedy behavior remains rational
- No single policy dominates across all situations

This outcome is expected given the remaining asymmetry
and absence of strategic interaction.

---

Curriculum Role
---------------

P3 is considered:

- ✅ A successful corrective to P2
- ✅ Behaviorally meaningful and reproducible
- ✅ Informationally minimal

P3 is deliberately **frozen** after validation.

It serves as a **structural bridge** toward symmetric
multi‑unit scenarios, where risk‑taking can no longer
be avoided trivially.