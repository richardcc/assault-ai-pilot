Rationale Contract
==================

This document defines the **contract for rationales** used in the Assault
explainable reinforcement learning system.

A rationale is a symbolic explanation associated with a concrete decision
executed by a specific unit at runtime.

Definition
----------

A **rationale** is a discrete semantic label representing
the agent's tactical intention **at decision time**.

It is stored as an integer identifier that maps to the canonical
``Rationale`` enumeration.

A rationale exists only in relation to:
- a specific acting unit
- a specific executed action
- a specific environment step

What a Rationale Is
-------------------

A rationale is:

- a symbolic category produced by the policy
- a discrete integer value
- aligned with an executed action
- aligned with the acting unit
- stable and serializable
- suitable for statistical analysis

What a Rationale Is NOT
----------------------

A rationale is **not**:

- an internal thought or belief
- a long-term plan
- a post-hoc inferred explanation
- a value reconstructed later
- a value obtained from ``model.predict()``

Rationales must never be guessed, inferred, or retroactively assigned.

Where It Is Computed
--------------------

Rationales are computed by the policy during forward evaluation:

::

   policy.forward(observation)
        → rationale logits
        → argmax → rationale_id

The rationale logits exist only transiently during this computation.

Where It Is Captured
--------------------

Rationales are captured **explicitly at decision time** by the RL runner.

The capture procedure is:

- call ``policy.forward()`` to obtain rationale logits
- convert logits to a discrete identifier
- associate the identifier with the chosen action
- associate the identifier with the acting unit

The system does not rely on training callbacks or learning loops
for rationale capture.

Where It Is Stored
------------------

Rationales are stored as part of the replay data.

They appear inside the decision structure:

::

   {
     "unit_id": "IT_1",
     "action": 4,
     "learned_rationale": 0,
     "heuristic_rationale": null
   }

Only the integer identifier is stored.
Semantic interpretation is deferred.

Where It Is Interpreted
-----------------------

Rationales are interpreted **only during offline analysis**.

Interpretation may include:

- mapping identifiers to semantic labels
- computing distributions and statistics
- correlating actions and intentions
- generating reports and visualizations

Offline analysis must never alter or recompute rationales.

Actor Alignment Requirement
----------------------------

Every rationale must be aligned with a concrete acting unit.

The acting unit is defined as:
- the unit selected by the environment to act
- exposed via ``info["unit_id"]`` in ``env.step()``

A rationale without a known acting unit is considered invalid.

Anti-Patterns
--------------

The following practices are explicitly forbidden:

- inferring rationales from environment states
- reconstructing rationales after execution
- reading rationales from policy attributes
- computing rationales during offline analysis
- assigning rationales without an acting unit

All rationales must be captured causally and recorded verbatim.

Canonical Rule
--------------

**If a rationale is not captured at the exact moment
a decision is executed by a specific unit,
it must be considered non-existent.**