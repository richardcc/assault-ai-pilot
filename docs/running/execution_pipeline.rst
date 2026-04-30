Execution and Analysis Pipeline
===============================

This page describes the **end‑to‑end execution and analysis pipeline**
used in the Assault‑Env project.

The goal is not to document implementation details, but to explain
**how experiments are executed, observed, and analyzed in a reproducible
and auditable way**.

The pipeline is designed explicitly for the study of
**emergent coordination and soft role allocation**, under strict control
of execution and evaluation conditions.

Conceptual overview
-------------------

The project adopts a **layered experimental architecture** in which
each component has a single, clearly defined responsibility.

At a high level, the workflow is:

.. code-block:: text

   Trained RL policy (PPO)
            |
            v
   Single‑match execution (RLRunner)
            |
            v
   Batch match execution (series runner)
            |
            v
   Engine‑level diagnostics collection
            |
            v
   Outcome aggregation and persistence
            |
            v
   Replay visualization and offline analysis

This structure ensures that **execution, observation and interpretation
are never conflated**.

Pipeline architecture diagram
-----------------------------

.. graphviz::

   digraph pipeline {
       rankdir=TB;
       node [shape=box, style="rounded,filled", fillcolor="#EFEFEF"];

       PPO [label="Trained PPO Model"];
       RLRunner [label="RLRunner\n(Single Match Execution)"];
       Series [label="Batch Match Execution"];
       Diagnostics [label="Engine Diagnostics"];
       Outcomes [label="Episode & Series Outcomes"];
       Replays [label="Replay Artifacts"];
       Analysis [label="Offline Analysis\n& Visualization"];

       PPO -> RLRunner;
       RLRunner -> Series;
       Series -> Diagnostics;
       Series -> Outcomes;
       RLRunner -> Replays;
       Diagnostics -> Analysis;
       Outcomes -> Analysis;
       Replays -> Analysis;
   }

The diagram makes explicit the separation between **execution**,
**observation**, and **analysis**, and highlights replay artifacts
as first‑class experimental evidence.

Separation of responsibilities
-------------------------------

The pipeline enforces a strict separation between the following roles:

Engine
^^^^^^

- Defines all tactical rules and dynamics
- Resolves combat, movement and turn structure
- Acts as the **single source of truth** for game state

The engine is fully deterministic given the same initial conditions.

Agent (Policy)
^^^^^^^^^^^^^^

- Receives observations from the environment
- Selects actions according to a trained PPO policy
- Has no visibility into diagnostics or evaluation logic

The agent is treated as a **black‑box decision system** during execution.

Execution layer
^^^^^^^^^^^^^^^

- Executes complete matches from start to terminal state
- Couples engine and agent through a narrow adapter interface
- Produces engine‑native replays

This layer is responsible only for *running games*, not for evaluating them.

Diagnostics layer
^^^^^^^^^^^^^^^^^

- Observes engine state at each activation step
- Records available tactical opportunities and risks
- Never modifies game state or agent behavior

Diagnostics are **passive, non‑intrusive observers** of the engine.

Outcome and analysis layer
^^^^^^^^^^^^^^^^^^^^^^^^^^

- Computes per‑episode outcomes from final engine state
- Aggregates results across match series
- Persists all outputs as structured JSON

No interpretation or learning occurs at this stage.

Offline execution guarantees
-----------------------------

All batch evaluation and analysis is performed **offline**.

Key guarantees:

- Evaluation never attaches to a live training process
- PPO models are loaded exclusively from disk
- Active model snapshots are never read
- No shared state exists between training and analysis

This allows:

- Continuous training and evaluation in parallel
- Reproducible experiments
- Safe long‑running batch analysis

Determinism and reproducibility
-------------------------------

Reproducibility is ensured through:

- Deterministic engine rules
- Explicit episode boundaries
- Structured replay recording
- Immutable persisted results

Given:

- the same engine version
- the same model snapshot
- the same scenario configuration

the system will reproduce identical game trajectories.

Replay‑driven validation
------------------------

Replays are first‑class experimental artifacts.

They allow:

- Visual validation of emergent behavior
- Step‑by‑step inspection of tactical decisions
- Decoupling of visualization from execution
- Post‑hoc explanation of outcomes

Replays can be consumed without loading any reinforcement learning code,
ensuring long‑term inspectability.

Summary
-------

The execution and analysis pipeline is designed to:

- Support rigorous experimental methodology
- Prevent accidental coupling between components
- Enable reproducible study of emergent behavior
- Provide transparent, auditable evidence for conclusions

Subsequent sections document each layer in detail.