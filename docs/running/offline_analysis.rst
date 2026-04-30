Offline Batch Analysis
======================

Offline batch analysis is the **canonical method** for evaluating trained
agents in the Assault‑Env project.

Its purpose is to measure **behavioral outcomes and engine dynamics**
across multiple complete matches, without interacting with the
training process or the agent internals.

This layer replaces all earlier rollout‑based or online evaluation
pipelines.

Purpose and scope
-----------------

Offline analysis is designed to:

- Execute batches of complete matches (N games)
- Compare different controller types (RL vs RL, RL vs heuristic, etc.)
- Collect outcomes and diagnostics safely
- Produce reproducible and auditable results

Offline analysis does **not**:

- Train reinforcement learning agents
- Modify model parameters
- Attach to running training processes
- Interpret results beyond aggregation

All interpretation is left to downstream analysis.

Canonical entry point
---------------------

The canonical entry point for offline analysis is the
``offline_series_orchestrator`` module.

This module is responsible for:

- Discovering trained PPO model snapshots on disk
- Loading models safely and offline
- Executing complete match series
- Collecting per‑game diagnostics and outcomes
- Persisting structured results to disk

No other entry point is considered authoritative for batch evaluation.

Offline safety guarantees
--------------------------

Offline analysis enforces strict safety guarantees to prevent
interference with training:

- **Disk‑only model loading**  
  Models are loaded exclusively from serialized snapshot files.

- **Snapshot age thresholds**  
  Only model files older than a fixed minimum age are eligible for loading.

- **Process isolation**  
  Analysis always runs in a separate process from training.

- **No shared state**  
  No PPO or environment state is shared between training and evaluation.

These guarantees allow long‑running training and evaluation
to proceed in parallel without risk.

Batch execution
---------------

During batch execution, the orchestrator:

1. Selects the appropriate controller for each side
2. Initializes a fresh engine session for each game
3. Executes the match until a terminal state is reached
4. Extracts the final game outcome
5. Collects engine‑level diagnostics

Each game is treated as a **fully independent experiment**.

Controller configurations
-------------------------

The batch analysis system supports mixed controller configurations,
including:

- Reinforcement learning vs reinforcement learning
- Reinforcement learning vs heuristic
- Heuristic vs heuristic

All controllers implement a common interface, ensuring that
comparison logic remains policy‑agnostic.

Model discovery and selection
-----------------------------

Model selection during offline analysis is automated.

The orchestrator:

- Scans the ``models/`` directory for compatible snapshots
- Applies filename patterns and age constraints
- Selects a single stable snapshot for evaluation

This design prevents accidental evaluation of partially written files
and ensures consistent experimental conditions.

Produced artifacts
------------------

Each offline analysis run produces a structured output directory
containing:

- Aggregated series outcomes
- Per‑game engine diagnostics
- A configurable number of saved replays

All artifacts are serialized as JSON and are independent of
the execution process.

These outputs serve as the primary input for
visualization, debugging and interpretation.

Relation to reproducibility
---------------------------

Offline batch analysis is a central component of the project’s
reproducibility guarantees.

Because:

- The engine is deterministic
- Models are immutable snapshots
- Execution is fully offline
- Results are persisted structurally

the same analysis can be repeated at any time to reproduce
identical outcomes, given the same inputs.

Summary
-------

Offline batch analysis provides a safe, deterministic and
reproducible way to evaluate trained agents across many games.

It separates execution from interpretation and ensures that
observed behavior reflects genuine interactions between
policy and engine, rather than artifacts of the training process.