P4-B – Soft Role Allocation under Minimal Relational Information
================================================================

This document reports the results of **P4-B**, an exploratory extension
of the symmetric 2 vs 2 scenario (P4) designed to study **soft role
allocation** (SRT) under minimal relational information.

P4-B does not modify rewards, PPO hyperparameters, or environment
dynamics. The only intervention consists of introducing limited
ally-centric observations.

---

Motivation
----------

In the baseline P4 setting (2 vs 2 symmetric), the learned policy
exhibits strategic maturity without collapsing into trivial evasion
or forced aggression.

However, no persistent coordination roles emerge, and the deterministic
(greedy) policy remains strongly conservative.

P4-B investigates whether **minimal relational information** is
sufficient to induce role-like differentiation *without* explicit role
assignment, asymmetry, or reward shaping.

---

Observation Extension
---------------------

Two additional observation fields are added to the P4 state space:

- ``ally_distance``:
  Manhattan distance to the nearest friendly unit.

- ``ally_strength_diff``:
  Difference between the agent's current strength and the ally's
  strength.

No explicit role labels, asymmetries, or incentive modifications are
introduced.

---

Training Results
----------------

P4-B is trained for approximately 200,000 steps using the same PPO
configuration as P4.

Training dynamics remain stable throughout:

- Low KL divergence
- No clipping saturation
- Moderate policy entropy
- No policy collapse or oscillatory behavior

The value function does not converge to a stable explanatory regime,
and explained variance remains low or negative, consistent with high
return variability and weak state-value predictability.

---

Greedy vs Stochastic Evaluation
-------------------------------

Deterministic (greedy) evaluation yields:

- Fully reproducible behavior
- Zero assaults across episodes
- Stable control of minimal victory points
- Mean enemy distance of approximately 5.5 hexes

Stochastic (non-greedy) evaluation reveals:

- Occasional assaults (0–3 per episode)
- Reduced mean enemy distance (approximately 3–4 hexes)
- Variable victory point outcomes
- High inter-episode variability

This contrast indicates that aggressive and coordinating behaviors
*exist within the policy distribution*, but are not selected as dominant
actions by the greedy policy.

---

Interpretation
--------------

The results indicate that:

- Minimal relational information enables **flexible, situational
  coordination**
- Role-like behaviors remain transient and context-dependent
- No stable or persistent role specialization emerges
- Conservative greedy behavior remains rational under symmetric
  conditions

These findings suggest that, in symmetric strategic environments,
adaptive coordination is favored over rigid or persistent role
allocation.

---

Curriculum Conclusion
---------------------

P4-B demonstrates that **soft role allocation cannot be assumed**
from ally-centric information alone.

The experiment is therefore considered:

- ✅ Methodologically sound
- ✅ Behaviorally informative
- ✅ Negative in outcome, but conclusive

P4-B is frozen as an exploratory curriculum extension.

Inducing persistent role specialization would require additional
asymmetry or task-level pressure, which lies outside the scope of the
present curriculum.