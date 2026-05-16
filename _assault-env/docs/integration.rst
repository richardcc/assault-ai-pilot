Integration
===========

Assault‑engine
--------------

**assault-env** depends on the deterministic ``assault-engine`` tactical core
and uses it in editable (development) mode:

::

   pip install -e assault-engine

This setup allows real‑time development of the environment without
duplicating, forking, or modifying core game logic.

The environment does **not** reimplement:

- Game rules
- Combat mechanics
- Movement validation
- State transitions

All tactical authority remains inside ``assault-engine``.

---

Reinforcement Learning Integration
----------------------------------

The environment is exposed as a standard ``gymnasium.Env`` without any
modification to engine internals.

Reinforcement learning agents interact exclusively through:

- ``reset()``
- ``step(action)``

The RL layer is strictly limited to **decision-making**:

- Selecting actions
- Observing state
- Receiving rewards
- Determining episode termination

All tactical resolution remains deterministic and engine‑controlled.

This guarantees that learning agents operate under the same constraints as
rule‑based or scripted players.

---

Self‑Play Integration
---------------------

Training is performed via **self‑play**.

Key properties:

- A single policy instance may control both sides
- Turns alternate deterministically
- No explicit opponent modeling is required

This design choice:

- Reduces problem dimensionality
- Avoids non‑stationary opponent distributions
- Allows competitive behavior to emerge naturally

Opponent behavior can be replaced with heuristic agents for evaluation
without modifying the learning pipeline.

---

Curriculum Integration
----------------------

Integration with reinforcement learning is driven by a
**scenario‑based curriculum**.

Curriculum progression is achieved by:

- Modifying initial game states
- Expanding or restricting action availability
- Increasing map size and spatial depth
- Introducing objective structures (e.g. Victory Points)

Importantly:

- The learning algorithm is unchanged across levels
- Hyperparameters remain fixed
- The engine remains immutable

This makes curriculum progression explicit, controlled, and reversible.

---

Evaluation Integration
----------------------

Learning success is validated **externally**.

The environment integrates with heuristic baseline agents used exclusively
for evaluation.

Typical evaluation criteria include:

- Mission outcome (victory / draw / defeat)
- Win‑rate against the heuristic baseline
- Action usage distribution
- Tactical coherence observed in deterministic replays

Environment rewards are considered **training signals only** and are not
used directly as performance metrics.

---

Replay and Analysis Integration
-------------------------------

The environment supports deterministic replay generation.

After evaluation runs:

- Each engine state is snapshotted
- Replays are serialized to JSON
- Behavior is inspected visually via the replay viewer

This allows:

- Qualitative tactical analysis
- Debugging of reward shaping
- Verification of learned behavior
- Comparison between curriculum levels

Replays are treated as first‑class analysis artifacts.

---

Perception System Integration
-----------------------------

**assault-env** is compatible with perception‑based agents.

A typical perception pipeline follows this structure:

::

   GameState → render → image → detector → observation → policy

In this setup:

- The learning agent never accesses engine internals
- Observations are derived from perception output
- Determinism is preserved at the engine level

This design supports integration with computer vision systems
(e.g. YOLO‑based detectors) without compromising core guarantees.

---

Determinism and Reproducibility
-------------------------------

All integration paths preserve **full determinism**.

Specifically:

- Randomness is injected only during scenario initialization
- All randomization is seed‑controlled
- No global random state is accessed implicitly
- Identical seeds produce identical trajectories

This guarantees:

- Reliable debugging
- Reproducible evaluation
- Fair comparison across training runs and curriculum stages

Determinism is treated as a non‑negotiable system property.