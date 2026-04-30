Running and Reproducibility
===========================

This section documents the **canonical execution and analysis workflows**
used in the Assault‑Env project.

The purpose of this section is to describe **how experiments are run,
evaluated, and reproduced**, not how agents are trained internally.

The focus is on:

- Deterministic execution of complete matches
- Offline‑safe evaluation of trained agents
- Engine‑level diagnostics and outcome analysis
- Reproducible replay generation and visualization

This section serves as the **single source of truth** for all
execution‑ and analysis‑related procedures.

Design philosophy
-----------------

The execution and analysis pipeline is intentionally designed around the
following principles:

- **Strict separation of concerns**  
  Execution, evaluation, diagnostics and analysis are isolated components.

- **Offline reproducibility**  
  Evaluation never attaches to the training process or shared state.

- **Engine‑centric observation**  
  Diagnostics observe the tactical engine, not the policy internals.

- **Auditability**  
  All outputs are persisted as structured JSON suitable for inspection.

High‑level workflow
-------------------

At a high level, experimental execution follows this structure:

.. code-block:: text

   Trained PPO model
          |
          v
     RLRunner (single match)
          |
          v
     GameSession (single external agent)
          |
          v
     Engine‑level diagnostics collection
          |
          v
     Outcome aggregation and persistence
          |
          v
     Replay visualization and offline analysis

Each stage has a **single, well‑defined responsibility**.

The opposing side of the match is controlled internally by the
environment and is not represented as a second external agent
during single‑match execution.

Scope and limitations
---------------------

This section does **not** document:

- PPO training algorithms
- Neural network architectures
- Reward shaping details
- Engine rule definitions

Those topics are covered in the **engine** and **curriculum**
documentation sections.

Contents
--------

.. toctree::
   :maxdepth: 2

   execution_pipeline
   rl_runner
   game_session
   policies
   offline_analysis
   diagnostics
   outcomes
