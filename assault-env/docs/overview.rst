Overview
========

**assault-env** is a training and simulation environment that wraps the
deterministic ``assault-engine`` tactical core.

It is designed to expose tactical decision‑making problems in a form suitable
for:

- Reinforcement learning
- Deterministic simulation
- Adversarial evaluation
- Integration with perception‑based agents

The environment itself does **not** implement game rules or combat mechanics.
All validation, resolution, and tactical constraints are delegated to
``assault-engine``.

This explicit separation is a foundational design choice.

---

Purpose
-------

The purpose of this project is to provide a controlled and executable
environment for studying tactical decision‑making under realistic constraints.

Specifically, **assault-env** exists to:

- Provide a Gymnasium‑compatible interface for tactical scenarios
- Enable reinforcement learning via self‑play and adversarial setups
- Support curriculum learning through controlled scenario progression
- Allow integration with perception systems (e.g. YOLO‑based pipelines)
- Enable deterministic simulation and reproducible evaluation

The environment is intentionally **minimal and explicit in scope**.
Any logic that does not directly relate to *decision, observation, reward, or
episode flow* is handled elsewhere.

---

Design Philosophy
-----------------

Assault‑env is built around the principle that **learning should only occur at
the decision level**.

The environment is responsible for:

- Selecting and applying actions
- Observing the current world state
- Computing reward signals
- Managing episode boundaries and outcomes

It never bypasses, alters, or replaces engine logic.

This ensures that learning agents are forced to operate under the same tactical
constraints as a deterministic rule‑based player.

---

Separation of Concerns
----------------------

The system is structured into three clearly separated layers:

``assault-engine``
~~~~~~~~~~~~~~~~~
- Rules and constraints
- Combat and movement resolution
- Terrain and map logic
- Zone of control calculations

The engine is fully deterministic and independent of reinforcement learning.

``assault-env``
~~~~~~~~~~~~~~~
- Action selection interface
- Observation construction
- Reward shaping
- Episode control and termination

The environment acts as a translation layer between the tactical engine and
learning agents.

``Agent``
~~~~~~~~~
- Decision‑making logic
- Learning algorithms (e.g. PPO)
- Policy evaluation and exploration

Agents have **no direct access** to engine internals.

This separation guarantees reproducibility, testability, and extensibility.

---

Curriculum‑Oriented Design
--------------------------

The environment is explicitly designed for **curriculum learning**.

Scenario complexity is introduced incrementally by:

- Modifying objective structure (e.g. Victory Points)
- Increasing spatial complexity
- Scaling the number of units
- Introducing stronger or more reactive opponents

Each curriculum level is validated and frozen before progressing to the next.
Completed scenarios are treated as stable baselines and are not modified
retroactively.

---

Evaluation Philosophy
---------------------

Internal reward signals exist **only for training purposes**.

Learning success is evaluated externally through:

- Mission outcomes (victory / draw / defeat)
- Win‑rate against heuristic baselines
- Action usage distributions
- Tactical coherence observed in deterministic replays

This approach reduces reward overfitting and emphasizes interpretable behavior
over raw reward maximization.

---

Summary
-------

In summary, **assault-env** provides:

- A clean separation between rules and learning
- Deterministic and reproducible environments
- Mission‑oriented tactical problems
- A foundation for scalable curriculum‑based training

It is designed to support *analysis*, not merely training, and to produce agents
whose behavior can be inspected, replayed, and reasoned about.