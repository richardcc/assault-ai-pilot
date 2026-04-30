P4‑B – Implicit Role Exploration
===============================

This document reports the results of **P4‑B**, an exploratory extension
of the symmetric 2 vs 2 scenario (P4) designed to study **implicit role
emergence** under minimal relational information.

P4‑B does not modify rewards, PPO hyperparameters, or environment
dynamics. Only additional ally‑centric observations are introduced.

---

Motivation
----------

In P4 (2 vs 2 symmetric), the learned policy exhibits strategic maturity
without collapsing to trivial evasion or forced aggression.

However, no persistent coordination roles emerge, and the greedy policy
remains conservative.

P4‑B investigates whether **limited relational information** is
sufficient to induce role‑like differentiation without explicit
assignment or incentive manipulation.

---

Observation Extension
---------------------

Two additional observation fields are added to the P4 state space:

- ``ally_distance``:
  Manhattan distance to the nearest friendly unit.

- ``ally_strength_diff``:
  Difference between the agent’s strength and the ally’s strength.

No explicit role labels, asymmetries, or reward changes are introduced.

---

Training Results
----------------

P4‑B is trained for approximately 200,000 steps using the same PPO
configuration as P4.

Training dynamics remain stable throughout:

- Low KL divergence
- No clipping saturation
- Moderate policy entropy
- No policy collapse or oscillation

The value function does not converge to a stable explanation of returns,
and explained variance remains low or negative.

---

Greedy vs Stochastic Evaluation
-------------------------------

Deterministic (greedy) evaluation yields:

- Fully reproducible behavior
- Zero assaults across episodes
- Stable control of minimal victory points
- Mean enemy distance ≈ 5.5

Stochastic (non‑greedy) evaluation reveals:

- Occasional assaults (0–3 per episode)
- Reduced mean enemy distance (≈ 3–4)
- Variable victory point outcomes
- High inter‑episode variability

This contrast confirms that aggressive and coordinating behaviors
exist within the **policy distribution**, but are not selected as
dominant actions by the greedy policy.

---

Interpretation
--------------

The results indicate that:

- Minimal relational information enables **flexible, situational
  coordination**
- Role‑like behaviors appear transient and context‑dependent
- No stable or persistent role specialization emerges
- Conservative greedy behavior remains rational under symmetry

These findings suggest that, in symmetric strategic environments,
adaptive coordination is favored over rigid role allocation.

---

Curriculum Conclusion
---------------------

P4‑B demonstrates that **implicit role emergence cannot be assumed**
from ally‑centric information alone.

The experiment is considered:

- ✅ Methodologically sound
- ✅ Behaviorally informative
- ✅ Negative in outcome, but conclusive

P4‑B is therefore **frozen** as an exploratory curriculum extension.

Inducing persistent roles would require additional asymmetry or task‑level
pressure, which lies beyond the scope of the present curriculum.