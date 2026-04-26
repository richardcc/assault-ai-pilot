Evaluator
=========

The Evaluator is an **offline analysis component**.

Purpose
-------

The evaluator determines whether one policy is better than another
according to a predefined **criterion of success**.

It exists to answer questions such as:
- Has the agent achieved the scenario objectives?
- Does this policy outperform another?
- Is performance stable across independent runs?

The evaluator:
- consumes Replay objects
- produces quantitative metrics
- compares outcomes across runs

The evaluator is **policy‑agnostic** and **training‑agnostic**.

---

Typical Metrics
---------------

Typical evaluation metrics include:

- number of Victory Points captured
- duration of VP control
- total VP score at the end of the game
- casualty ratios (own vs enemy losses)
- time to first VP capture
- consistency of outcomes across episodes

Metrics may be aggregated:
- per episode
- per seed
- per policy version

The choice of metrics defines the **success criterion**.

---

Design Constraints
------------------

The evaluator:

- does NOT modify the Replay
- does NOT influence training
- does NOT access policy internals
- does NOT execute environment steps
- does NOT depend on PPO or RL mechanics

All evaluator logic operates on **recorded data only**.

---

Role in the Pipeline
--------------------

The evaluator is part of the **analysis and validation phase**.

Training optimizes:
- a reward function
- via gradient‑based learning

Evaluation measures:
- fulfillment of objectives
- overall effectiveness
- comparative performance

Training and evaluation are intentionally decoupled.

---

Key Design Principle
--------------------

The evaluator defines **success**, not learning.

Reward is a proxy signal used during training.
Success is measured offline using explicit metrics.

This separation ensures:
- reproducibility
- interpretability
- comparability
- stable experimentation