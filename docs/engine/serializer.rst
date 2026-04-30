Replay Serialization
====================

The Replay Serializer is responsible for converting Replay objects
into a persistent, portable representation.

Purpose
-------

- persist game executions
- enable offline analysis
- decouple execution from visualization
- ensure reproducibility

Responsibilities
----------------

The serializer:
- converts Replay objects to JSON
- preserves ordering of ReplaySteps
- preserves all explicit information
- remains backward‑compatible

Non‑Responsibilities
--------------------

The serializer **does NOT**:
- compute rewards
- evaluate policies
- execute gameplay logic
- infer or validate rationales
- access the PPO model
- access the environment

Schema Stability
----------------

The JSON schema must be:
- explicit
- versionable
- stable across releases

Any semantic meaning is defined by:
- engine documentation
- evaluator logic
- viewer interpretation

Serialization is a **pure I/O layer**.