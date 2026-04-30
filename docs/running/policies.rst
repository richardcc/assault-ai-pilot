Policies and Controllers
========================

This module defines the **external decision‑making components** used
during match execution.

Two policy types are provided:

- A reinforcement learning policy used by the agent under study
- A deterministic heuristic policy used by the environment

These policies are functionally and conceptually separate.

ExplainableActorCriticPolicy (RL)
---------------------------------

The ``ExplainableActorCriticPolicy`` is a PPO policy compatible with
dictionary‑based observations.

It extends a standard actor‑critic architecture with an **auxiliary
rationale head**.

Key properties:

- Compatible with Stable‑Baselines3 PPO
- Accepts ``Dict`` observations
- Produces standard action outputs
- Exposes internal rationale logits for analysis

Explainability mechanism
^^^^^^^^^^^^^^^^^^^^^^^^

The rationale head is computed from the same latent representation
used to select actions.

This ensures:

- No interference with action selection
- No additional forward passes
- Consistency between behavior and explanation signals

Rationale outputs are:

- Not used as rewards
- Not used for training control
- Exposed purely for inspection and visualization

The policy remains fully homogeneous and single‑agent.

HeuristicPolicy (Environment Opponent)
--------------------------------------

The ``HeuristicPolicy`` implements a deterministic, aggressive opponent
used internally by the environment.

It is **not a learning agent** and has no internal state.

Behavioral characteristics:

- Forces adjacency when enemies are nearby
- Applies persistent spatial pressure
- Moves toward victory point objectives
- Breaks symmetry deterministically

Robustness considerations
^^^^^^^^^^^^^^^^^^^^^^^^^

The heuristic policy is designed to operate safely across:

- Older observation formats
- Partial observation dictionaries
- Environments without explicit enemy distance signals

When required signals are missing, conservative defaults are used to
guarantee stable execution.

Role in experimentation
-----------------------

Separating the learning agent from opponent behavior ensures:

- Reduced variance across runs
- Improved interpretability of outcomes
- Isolation of learning dynamics
- Clear attribution of emergent behavior

The heuristic opponent serves as **structural pressure**, not as a
competing learner.

Summary
-------

The policy module cleanly separates:

- Learning‑based decision making (RL)
- Deterministic environmental opposition (heuristic)

This separation is foundational to reproducible experimentation and
the study of emergent coordination under fixed tactical constraints.