Replay JSON Contract
====================

This document defines the **logical JSON contract** of a Replay file.

The Replay format is a **stable interface** between:
- execution (Runner / RLRunner)
- visualization (web viewer)
- evaluation
- offline analysis

The Replay format is **not an internal runtime structure**.
It is a **public, persistent contract**.

Design Principles
-----------------

The Replay format is:

- deterministic
- immutable
- append-only
- replayable offline
- independent of RL algorithms
- independent of environment implementation

It explicitly DOES NOT contain:

- rewards
- gradients
- neural network parameters
- logits
- tensors
- training metadata

All values must be JSON-serializable.

Top-Level Structure
-------------------

A Replay JSON document has the following top-level keys:

.. code-block:: text

   {
     "initial_state": { ... },
     "steps": [ ... ],
     "final_state": { ... }
   }

Initial State
-------------

``initial_state`` is a snapshot of the game before any action is taken.

It has the same logical structure as a ``GameState`` and is duplicated
for convenience and semantic clarity.

Steps
-----

``steps`` is an ordered list of replay entries.

Each element corresponds to **one decision cycle**.

.. code-block:: text

   {
     "state": { ... },
     "decision": { ... }   # optional
   }

The order of steps defines the temporal progression of the game.

GameState
---------

A ``GameState`` describes the entire board at one moment in time.

.. code-block:: text

   {
     "units": [ ... ]
   }

It does not include:
- current player
- reward
- hidden information
- rules or dynamics

It is a pure snapshot of world state.

UnitState
---------

Each unit in the GameState is represented by a ``UnitState``.

.. code-block:: text

   {
     "id": "IT_1",
     "counter_id": "US_RIFLES_43",
     "hex": "C5",
     "strength": 8,
     "status": ["pinned"]
   }

Field definitions
~~~~~~~~~~~~~~~~~

- ``id``: unique unit identifier
- ``counter_id``: rendering / counter reference
- ``hex``: board position (viewer convention)
- ``strength``: remaining strength points
- ``status``: list of string flags (may be empty)

Decision
--------

``decision`` is OPTIONAL.

It exists only if the step was driven by an agent action.

.. code-block:: text

   {
     "unit_id": "IT_1",
     "action": 2,
     "learned_rationale": "CAPTURE_OBJECTIVE",
     "heuristic_rationale": "ADVANCE_TO_CONTACT"
   }

Decision semantics
~~~~~~~~~~~~~~~~~~

- ``unit_id``: identifier of the acting unit
- ``action``: discrete action executed (agent output)
- ``learned_rationale``:
  - produced by the policy
  - human-readable string
  - may be ``null``
- ``heuristic_rationale``:
  - optional baseline explanation
  - used only for comparison
  - may be ``null`` or omitted

The Replay NEVER interprets or validates decisions.

Final State
-----------

``final_state`` is the last GameState of the replay.

It enables:
- quick inspection of outcomes
- evaluation without replay traversal

It MUST be consistent with the last replay step.

Backward Compatibility
----------------------

Future Replay versions must:

- preserve existing fields
- only add optional fields
- never change semantic meaning

Versioning (if required) is handled
outside the Replay payload.

Consumer Responsibilities
-------------------------

Consumers of Replay JSON must:

- assume immutability
- not attempt to repair missing data
- treat Replay as the single source of truth
- avoid inferring data not explicitly stored

Replay as a Contract
--------------------

The Replay format is the **boundary of trust** between systems.

If information is not present in the Replay,
it must not be assumed implicitly.

This guarantees:

- reproducibility
- debuggability
- explainability
- long-term stability