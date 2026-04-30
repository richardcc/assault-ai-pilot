Design Notes
============

This document records the **design decisions** taken during the
development of the assault‑env reinforcement learning curriculum.

The objective of these notes is to make explicit *why* certain choices
were made, especially when alternative approaches were intentionally
rejected.

---

Why No Reward Shaping
---------------------

Reward shaping was intentionally avoided beyond the minimal task
definition established in P1.

Although reward shaping can accelerate convergence, it often obscures
the origin of observed behaviors by embedding designer intent directly
into the optimization target.

Instead, the curriculum relies on:

- Structural changes (number of units, symmetry)
- Informational changes (observation space)
- Fixed learning algorithm (PPO)

This ensures that behavioral transitions can be attributed to
environmental structure rather than handcrafted incentives.

---

Why PPO Was Not Tuned
--------------------

Proximal Policy Optimization (PPO) hyperparameters were kept constant
across all curriculum stages.

This choice serves two purposes:

1. Comparability:
   Differences in behavior across P1–P4 can be compared directly.

2. Diagnostic clarity:
   When failures occur (e.g., P2 evasion), they can be interpreted as
   meaningful signals rather than artifacts of poor tuning.

The curriculum design assumes that a stable PPO configuration is
preferable to optimized but opaque behavior.

---

Deterministic vs Stochastic Evaluation
--------------------------------------

A key distinction throughout the curriculum is the separation between
deterministic (greedy) and stochastic policy execution.

Deterministic evaluation reflects the **most conservative action**
preferred by the policy, while stochastic evaluation samples from the
learned action distribution.

In later stages (P3, P4):

- Aggressive or risky behaviors often exist in the distribution
- These behaviors are not always selected by the greedy policy

This divergence is interpreted as **strategic maturity**, not failure.

Greedy evaluation alone is therefore insufficient to assess learning
progress in symmetric or strategic environments.

---

Interpreting Failure as Information
-----------------------------------

Certain stages of the curriculum are explicitly designed to *fail* in a
controlled way.

For example:

- In P2, permanent evasion emerges naturally
- This behavior is rational given asymmetric information
- The failure reveals a structural limitation of the scenario

Such failures are used diagnostically to motivate the next curriculum
stage rather than corrected directly.

---

Symmetry and Strategy
---------------------

The transition from asymmetric (P2, P3) to symmetric (P4) scenarios
marks the shift from tactical optimization to strategic interaction.

In symmetric settings:

- No single policy dominates universally
- Outcomes are more sensitive to coordination patterns
- Value estimation becomes inherently noisier

As a result, classical convergence indicators (e.g. explained variance)
must be interpreted differently.

Behavioral analysis becomes more informative than scalar metrics.

---

Implicit Roles vs Explicit Roles
--------------------------------

Role differentiation is explored through **implicit role emergence**
rather than explicit assignment.

By providing limited relational information (e.g., ally distance),
the agent can learn to differentiate behavior without any predefined
labels such as "attacker" or "support".

This approach preserves generality and avoids enforcing brittle role
schemas.

---

Summary
-------

Across the entire curriculum:

- Changes are minimal and incremental
- Rewards and algorithms remain fixed
- Structural and informational shifts drive behavior

This design allows the curriculum to function as a controlled study of
emergent coordination and strategy.