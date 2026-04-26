Heuristic Baseline
=================

The heuristic is a **deterministic, rule‑based baseline policy**.

It represents a minimal, hand‑crafted strategy used for
comparison, validation, and analysis.

The heuristic is **not** an optimal policy and does not define
desired or correct behavior.

---

Purpose
-------

The heuristic serves as a **reference point** for evaluation.

Its main purposes are:

- provide a baseline for comparison with learned policies
- validate that environments and scenarios are solvable
- support debugging and sanity checks
- enable qualitative comparisons during analysis

The heuristic allows answering questions such as:

- Is the learned policy strictly better than simple rules?
- Does reinforcement learning outperform a naive strategy?
- Where does the learned policy diverge from intuitive tactics?

---

Characteristics
---------------

The heuristic is:

- deterministic
- non‑adaptive
- non‑learning
- rule‑based
- explicit in its logic

It depends only on:

- the observable game state
- simple tactical rules
- local information

It does NOT depend on:

- reward signals
- training history
- long‑term planning
- neural networks
- past episodes

---

Role in the System
------------------

The heuristic participates in the system only as a:

- baseline policy
- comparison reference
- diagnostic tool

The heuristic:

- does NOT influence training
- does NOT participate in PPO optimization
- does NOT act as ground truth
- does NOT supervise the agent

Reinforcement learning is never trained to imitate the heuristic.

---

Heuristic vs Reinforcement Learning
-----------------------------------

| Aspect | Heuristic | RL Policy |
|-------|-----------|-----------|
| Adaptation | None | Learned |
| Planning | Local, myopic | Emergent |
| Generalization | Limited | Learned |
| Flexibility | Fixed rules | Policy‑driven |
| Explainability | Explicit rules | Learned rationales |

The heuristic provides **interpretability by design**,
while the RL policy provides **interpretability via learned rationales**.

---

Heuristics and Explainability
-----------------------------

Heuristic rationales may be inferred **post‑hoc** from state transitions.

These inferred rationales:

- are deterministic
- reflect predefined rules
- are used only for comparison

Learned rationales produced by the policy:

- are part of the model
- are learned end‑to‑end
- may diverge from heuristic explanations

Comparing heuristic rationales with learned rationales enables:

- analysis of strategic differences
- detection of emergent behaviors
- identification of non‑intuitive solutions

---

Design Principle
----------------

The heuristic defines **what a simple agent would do**.

It does not define:
- optimal play
- correct strategy
- learning targets

The learned policy is free to outperform, ignore,
or contradict the heuristic.

This separation ensures:
- clean experimentation
- unbiased learning
- meaningful evaluation
