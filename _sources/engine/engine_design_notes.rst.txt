Engine Design Notes
===================

Reward Shaping
--------------

Rewards were intentionally left unchanged after P1.

All behavioral changes observed throughout the curriculum are driven by
information availability and task structure, not by incentive
manipulation or reward engineering.

This ensures that emergent coordination and soft role allocation arise
from learning dynamics rather than from shaped objectives.

Deterministic Evaluation
------------------------

Greedy policy evaluation masks learned stochastic behaviors.

This effect was expected and explicitly verified through stochastic
rollouts, which reveal behavior distributions that greedy evaluation
cannot capture.

All evaluation conclusions regarding coordination and role allocation
are therefore based on stochastic execution traces, not on deterministic
policy collapse.

Algorithm Stability
-------------------

PPO hyperparameters were kept constant throughout the entire curriculum.

This constraint ensures that all observed behavioral differences arise
from environmental structure and curriculum progression, not from
algorithmic tuning.

Any deviation in behavior can therefore be causally attributed to task
design rather than training instability.

Curriculum Principle
--------------------

Each curriculum stage introduces exactly **one new difficulty dimension**.

Local optima are resolved structurally (through state and information
changes), not by applying additional rewards, penalties, or heuristics.

This design enforces interpretability and supports causal analysis of
learning progression.

Rendering and Visualization Boundaries
--------------------------------------

The Assault engine is **rendering-agnostic**.

It does not encode assumptions about:
- visual layout
- coordinate systems
- terrain projection
- rendering layers (e.g. S2 / S3)
- alpha composition or presentation concerns

All visualization-related constraints are handled **outside the engine**
through the replay contract and viewer implementations.

The engine guarantees only:
- deterministic state transitions
- complete and immutable replay snapshots
- sufficient information for faithful rendering

Any rendering system (Python viewer, web viewer, or future renderers)
must comply with the replay format and may not impose requirements on
engine internals.