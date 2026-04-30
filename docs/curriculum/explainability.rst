Explainability in Training
==========================

Explainability in Assault‑Env is **not post‑hoc inference**.

Rationales are:
- produced by the policy
- learned end‑to‑end
- part of the model itself

Principle
---------

The system does not attempt to reconstruct why a decision was made
after the fact.

Instead:
- the agent explicitly emits a rationale
- that rationale is trained together with the policy

Policy‑Level Explainability
---------------------------

The PPO policy includes:
- a standard actor‑critic structure
- an auxiliary rationale head

This head:
- predicts a discrete rationale
- shares features with the action policy
- reflects the agent’s internal representation

Training Implications
---------------------

Rationales:
- are learned implicitly during PPO training
- are NOT enforced by heuristics
- are NOT backpropagated separately
- are NOT optimized via an auxiliary optimizer

Observation vs Explanation
--------------------------

The system distinguishes between:
- **what the agent observes**
- **what the agent does**
- **what the agent claims as rationale**

All three are recorded explicitly and can be compared offline.

Comparison with Heuristics
--------------------------

Heuristic rationales can be computed post‑hoc
for comparison and analysis.

They are never used as ground truth for training.

Explainability is therefore:
- endogenous
- auditable
- comparable
- non‑invasive