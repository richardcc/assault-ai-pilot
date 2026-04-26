Design Notes
============

Reward Shaping
--------------

Rewards were intentionally left unchanged after P1.
All behavior changes are driven by information availability,
not incentive manipulation.

Deterministic Evaluation
------------------------

Greedy policy evaluation masks learned stochastic behaviors.
This was expected and confirmed via stochastic rollouts.

Algorithm Stability
-------------------

PPO hyperparameters were kept constant throughout the curriculum
to ensure behavioral differences arise from task structure alone.

Curriculum Principle
--------------------

Each stage introduces exactly one new difficulty dimension.
Local optima are resolved structurally, not by force.