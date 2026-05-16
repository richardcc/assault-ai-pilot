Evaluation
==========

This section describes how learning performance in **assault-env**
is evaluated and interpreted.

Evaluation is intentionally separated from training rewards to ensure
that learned behavior is meaningful, robust, and interpretable.

---

Evaluation Philosophy
---------------------

Reward accumulation during training is **not** treated as a performance metric.

Evaluation focuses on **mission‑level outcomes** and qualitative behavior,
not raw reward maximization.

A policy is considered improved only if it demonstrates:

- Tactical coherence
- Objective awareness
- Robustness across episodes
- Reasonable risk management

---

Deterministic Evaluation
------------------------

Evaluation is performed in a fully deterministic setting.

- Exploration is disabled (``deterministic=True``)
- Identical seeds produce identical trajectories
- No randomness is introduced during evaluation

This ensures reproducible comparisons between policies and curriculum stages.

---

Evaluation Modes
----------------

Evaluation typically consists of:

- Single deterministic episodes
- Short batches of repeated runs
- Replay‑based qualitative inspection

No learning occurs during evaluation.

---

Mission Outcome Metrics
-----------------------

The primary evaluation signal is the **mission outcome**:

- ``victory``
- ``draw``
- ``defeat``

In the baseline scenario (P1 – VP Defended), victory is determined by
Victory Points controlled at the end of time.

Outcomes are treated as **semantic results**, not numeric scores.

---

Auxiliary Metrics
-----------------

Additional metrics are collected for behavioral analysis:

- ``vp_points`` – VP controlled at mission end
- ``assaults`` – number of assault actions executed
- ``moves`` – number of movement actions
- ``waits`` – passivity indicator
- ``avg_distance`` – average distance to enemy

These metrics are used to understand *how* the outcome was achieved.

---

Heuristic Baseline
-----------------

Evaluation is conducted against a deterministic heuristic opponent.

The heuristic:

- Defends Victory Points
- Attempts to recapture lost objectives
- Assaults whenever legally possible

This provides a consistent and interpretable reference behavior.

Win‑rate against the heuristic is meaningful only within the same scenario.

---

Replay‑Based Analysis
---------------------

Every evaluation run generates a deterministic replay.

Replays are used for:

- Tactical inspection
- Debugging reward shaping
- Identifying pathological behaviors
- Comparing curriculum stages

Replays are considered first‑class artifacts of the evaluation process.

---

Interpreting Defeat
-------------------

Defeat is a **valid and expected outcome**, particularly in difficult missions.

In the baseline scenario, a typical learned policy may:

- Secure a single VP safely
- Avoid high‑risk engagement
- Lose the mission by design

This behavior is rational and consistent with the scenario structure.

Defeat does not imply learning failure.

---

Summary
-------

Evaluation in **assault-env** prioritizes:

- Mission semantics over reward totals
- Determinism over stochastic averaging
- Behavioral coherence over numeric optimization

A scenario is considered solved only when the behavior aligns with
design intent, not when victory is guaranteed.
