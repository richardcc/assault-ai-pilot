Curriculum Conclusion
=====================

This document summarizes the findings of the assault‑env reinforcement
learning curriculum (P1–P4), including the exploratory extension P4‑B.

The objective of the curriculum was not to maximize task performance,
but to **understand which forms of tactical and strategic behavior
emerge naturally under controlled structural and informational
conditions**.

---

Overview of Curriculum Findings
-------------------------------

Across stages P1 through P4, the curriculum incrementally increased
environmental complexity while maintaining:

- A fixed reward function
- A fixed learning algorithm (PPO)
- Deterministic environment dynamics
- Minimal and isolated changes per stage

This design enabled direct attribution of behavioral transitions to
specific structural or informational modifications.

---

What Emerges
------------

The curriculum demonstrates that the following behaviors **do emerge**
under appropriate conditions:

- Basic tactical competence under purely local information (P1)
- Stable multi‑unit control without catastrophic failure (P2)
- Situation‑dependent risk assessment enabled by aggregate context (P3)
- Adaptive coordination in fully symmetric strategic settings (P4)
- Selective aggression present within stochastic policy distributions
- Flexible, context‑dependent coordination without rigid specialization

These behaviors arise **without reward shaping or role assignment**,
indicating that PPO can learn tactically and strategically meaningful
policies when sufficient information is provided.

---

What Does Not Emerge
-------------------

Equally important, the curriculum identifies behaviors that **do not
emerge naturally** under the tested conditions:

- Persistent or explicit role specialization in symmetric scenarios
- Dominant greedy policies in strategic multi‑agent environments
- Stable unit‑level task allocation without structural asymmetry
- Guaranteed aggression under numerical parity

The absence of these behaviors is not interpreted as failure, but as a
property of the underlying problem structure.

P4‑B explicitly demonstrates that **ally‑centric relational information
alone is insufficient** to induce stable role differentiation under
symmetry.

---

Key Interpretive Insights
------------------------

Several general insights emerge from the curriculum:

1. Conservative behavior is a rational baseline under uncertainty.
2. Structural redundancy without aggregate awareness induces stable
   evasion rather than coordination.
3. Minimal informational augmentation can resolve structural failure
   modes without altering incentives.
4. Symmetry eliminates trivial solutions and necessitates strategic
   adaptation.
5. Stochastic evaluation is essential for revealing the full policy
   distribution in strategic environments.
6. Oscillatory or variable value estimates in symmetric games reflect
   inherent strategic ambiguity, not learning instability.

---

Methodological Implications
---------------------------

The curriculum reinforces several methodological principles:

- Reward shaping is not required to induce complex behavior, but can
  obscure causal interpretation.
- Fixing algorithmic parameters across stages enhances interpretability.
- Controlled failure modes provide valuable diagnostic information.
- Strategy emergence should be evaluated behaviorally, not solely via
  scalar metrics.

These principles guided all design decisions and are reflected
consistently across stages.

---

Curriculum Status
-----------------

The curriculum is considered **complete and frozen** with respect to
stages P1–P4.

P4‑B is retained as an exploratory extension documenting a negative but
informative result.

No further curriculum stages are introduced in this work.

Future extensions (e.g., explicit asymmetry, task differentiation, or
long‑horizon incentives) are considered **separate research questions**
rather than continuations of the present curriculum.

---

Final Remark
------------

The assault‑env curriculum demonstrates that meaningful coordination
and strategic behavior can emerge from minimal assumptions, provided
that structural and informational conditions are made explicit.

Equally, it shows that not all desirable behaviors—such as persistent
role allocation—should be expected to arise in the absence of explicit
pressure.

Understanding **why behaviors do or do not emerge** is the central
contribution of this curriculum.
