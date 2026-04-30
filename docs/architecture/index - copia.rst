Architecture Overview
=====================

This section documents the **system-level architecture** of the Assault AI
project, describing how decisions are defined, executed, recorded, and later
analyzed or visualized.

The focus is not on individual algorithms, but on **causal structure**:
where decisions originate, how they are applied, how ground-truth data is
captured, and how all downstream analysis remains aligned with executed
behavior.

The primary goals of this documentation are to make explicit:

- where decisions are computed
- where acting units are selected
- where explanatory information is captured
- where data is persisted as ground truth
- where offline analysis and visualization occur

The architecture emphasizes **causal alignment** between the acting unit,
the executed action, and any associated explanation or rationale.

Separation of Concerns
---------------------

The system is structured into clearly separated layers with strictly defined
responsibilities:

- **Engine layer**  
  Defines game semantics, rules, deterministic state transitions, and replay
  generation.

- **Runner layer**  
  Executes policies, selects acting units, applies actions, and records
  decision metadata.

- **Replay layer**  
  Stores immutable, state-based ground truth describing world evolution.

- **Analysis layer**  
  Interprets replay data offline to study behavior, coordination patterns,
  and soft role allocation (SRT).

- **Rendering layer**  
  Visualizes replay data without mutating or inferring state.

No layer is permitted to infer, reconstruct, or modify information owned by
another layer. All communication occurs through explicit data artifacts.

Architecture Documents
----------------------

The following documents define the **system-level architectural contracts**
and data flows used across all subsystems:

.. toctree::
   :maxdepth: 2

   engine_definition
   rationale_flow
   generated_artifacts
