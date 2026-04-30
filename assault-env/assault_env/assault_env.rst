Environment control model
-------------------------

``AssaultEnv`` implements a single‑agent interaction model.

- One side of the match is controlled by an external reinforcement learning policy
- The opposing side is controlled internally by the environment using a deterministic heuristic
- Turn order, activation, and termination are fully managed by the environment

The external agent proposes one action per activation step.
All legality checks, enemy responses and combat resolution are performed by the engine.

This design isolates learning dynamics while preserving tactical pressure,
allowing behavioral patterns to emerge without explicit coordination signals.