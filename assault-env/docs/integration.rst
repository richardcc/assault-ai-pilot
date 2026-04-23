Integration
===========

Assault-engine
--------------

Assault-env depends on ``assault-engine`` and uses it in editable mode:

::

   pip install -e assault-engine

This allows real-time development of the environment without
duplicating or modifying core game logic.

The environment does not reimplement any mechanics, rules,
or state transitions.

---

Reinforcement Learning
----------------------

The environment is exposed as a ``gymnasium.Env`` without
modification to engine internals.

Reinforcement learning agents interact exclusively through:

- ``reset()``
- ``step(action)``

The RL layer is strictly limited to **decision-making**.
All combat resolution remains deterministic and engine-controlled.

---

Self-Play Integration
---------------------

Training is performed via **self-play**.

- A single policy controls both sides.
- Turns alternate deterministically.
- No explicit opponent modeling is required.

This design enables competitive behavior while keeping
the learning problem stationary.

---

Curriculum Integration
----------------------

Integration with reinforcement learning is driven by a
**scenario-based curriculum**.

Curriculum progression is achieved by:

- Modifying initial game states
- Expanding action availability
- Increasing spatial complexity

No changes to the learning algorithm are required between levels.

---

Evaluation Integration
----------------------

Learning is validated externally.

The environment is integrated with a heuristic baseline agent
used exclusively for evaluation.

Evaluation criteria include:

- Win-rate against the heuristic
- Action usage distribution
- Tactical coherence over longer engagements

Environment rewards are considered **training signals only**.

---

Perception Systems
------------------

Assault-env is compatible with perception-based agents.

A typical perception pipeline is:

::

   GameState → render → image → detector → observation

The learning agent never accesses engine internals.

This allows integration with computer vision systems
(e.g. YOLO-based detectors) without compromising determinism.

---

Determinism and Reproducibility
-------------------------------

All integration paths preserve determinism.

- Randomness is injected only at scenario initialization
- The engine does not depend on global random state
- Identical seeds produce reproducible outcomes

This guarantees reliable evaluation and debugging across
reinforcement learning experiments.