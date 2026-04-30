Rollout Collection
==================

The rollout collection module is responsible for **executing trained
policies** and generating Replay data for offline analysis.

Purpose
-------

This module bridges the gap between training and analysis.

Its responsibilities are:

- load a trained policy
- execute evaluation episodes
- record complete Replay objects
- persist Replay JSON files

Rollout collection does NOT perform learning or evaluation.

---

Inputs
------

- trained policy checkpoints
- evaluation configuration (episodes, seeds)
- environment scenario

---

Outputs
-------

- one or more Replay files
- stored in a reproducible, analysis‑ready format

These Replay files are later consumed by:
- behavior analysis
- rationale analysis
- evaluators
- report generation

---

Design Constraints
------------------

The module:

- does NOT affect training
- does NOT compute metrics
- does NOT modify policies
- does NOT inspect PPO internals

It uses only:
- policy.predict
- environment execution
- replay recording

---

Role in the Pipeline
--------------------

Training → Rollout Collection → Replay → Analysis

This separation ensures:
- reproducibility
- clean experiment boundaries