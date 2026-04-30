Rationale Statistics
===================

The rationale statistics module analyzes the **explanatory output**
of trained policies.

Purpose
-------

It answers the question:

**How does the agent explain its own behavior?**

This module focuses exclusively on rationales emitted by the policy.

---

Metrics Extracted
-----------------

Typical rationale metrics include:

- frequency of each learned rationale
- dominance or collapse of explanations
- transitions between rationales
- alignment with heuristic rationales
- rationale diversity across episodes

---

Inputs
------

- Replay files containing Decision entries
- learned rationales stored in Replay

Optional inputs:
- heuristic rationales (for comparison only)

---

Outputs
-------

- rationale frequency tables
- comparative distributions
- divergence indicators between learned and heuristic reasoning

---

Design Constraints
------------------

This module:

- does NOT infer rationales
- does NOT supervise learning
- does NOT assume correctness of explanations
- does NOT modify Replays

Rationale analysis is descriptive, not prescriptive.
``