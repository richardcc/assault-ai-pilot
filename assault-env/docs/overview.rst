Overview
========

Assault-env is a **training and simulation environment** that wraps the
deterministic ``assault-engine`` tactical core.

It is designed to expose tactical decision-making problems in a form
suitable for reinforcement learning, simulation, and perception-based agents.

The environment does not implement game rules or combat mechanics.
All rules are delegated to ``assault-engine``.

---

Purpose
-------

The purpose of this project is to:

- Provide an executable environment for tactical decision-making
- Enable reinforcement learning via self-play
- Support curriculum learning through controlled scenario progression
- Allow integration with perception systems (e.g. YOLO-based pipelines)
- Enable deterministic simulation and evaluation

The environment is intentionally minimal and explicit in scope.

---

Design Philosophy
-----------------

Assault-env is built around the principle that **learning should only
occur at the decision level**.

The environment:

- Selects actions
- Observes world state
- Computes rewards
- Controls episode flow

It never bypasses or alters engine logic.

---

Separation of Concerns
----------------------

The system is structured into three clearly separated layers:

- ``assault-engine``  
  Rules, combat resolution, and map logic.  
  Fully deterministic and independent of learning.

- ``assault-env``  
  Action selection, observations, rewards, and episode control.  
  Acts as a translation layer between the engine and learning agents.

- ``agent``  
  Learning and decision-making logic (e.g. PPO policies).  
  No direct access to engine internals.

This separation ensures reproducibility, testability, and extensibility.

---

Curriculum-Oriented Design
--------------------------

The environment is explicitly designed for **curriculum learning**.

Complexity is introduced incrementally by:

- Expanding the action space
- Randomizing initial conditions
- Increasing spatial depth of scenarios

Each curriculum level is validated before progressing to the next.

---

Evaluation Philosophy
---------------------

Internal reward signals are used exclusively for training.

Learning success is validated externally through:

- Win-rate against a heuristic baseline
- Action usage distributions
- Tactical coherence in longer engagements

This prevents reward overfitting and ensures meaningful behavior.