Curriculum Learning
===================

**assault-env** is explicitly designed for **curriculum learning**.

The tactical core (``assault-engine``) remains stable and deterministic,
while the environment progressively exposes more complex
decision‑making problems to the learning agent.

Curriculum progression is achieved **without modifying game rules,
combat mechanics, or learning algorithms**.

Only the *context and structure of the problem* change.

---

Curriculum Principles
---------------------

The curriculum follows strict and conservative principles:

- Only **one new concept** is introduced per level
- Previously learned behavior is preserved
- Learning complexity is controlled via scenarios and rewards
- Each level is validated before progressing

These constraints are enforced to avoid:

- Catastrophic forgetting
- Policy collapse
- Over‑fitting to transient reward signals

Curriculum progression is therefore **explicit, deliberate, and reversible**.

---

Stable Engine Principle
-----------------------

Curriculum learning is built on a strict separation of responsibilities:

- The engine **does not learn**
- The environment **does not change rules**
- Only the agent learns

Specifically:

- ``assault-engine`` remains immutable
- Tactical rules are never specialized for learning
- Reward shaping never bypasses engine constraints

This principle guarantees determinism, reproducibility, and clean
experimentation across curriculum stages.

---

Curriculum Dimensions
---------------------

Curriculum progression is achieved by modifying **problem dimensions**,
not algorithms.

Typical curriculum dimensions include:

- Initial conditions (scenario layout and unit placement)
- Map size and spatial depth
- Available action set
- Objective structure (e.g. Victory Points)
- Opponent reactivity and pressure
- Reward shaping emphasis

Learning algorithms, hyperparameters, and training procedures remain
unchanged throughout curriculum progression.

---

Curriculum Levels (Historical Progression)
------------------------------------------

The following levels describe the *historical curriculum* that led to the
frozen baseline scenario.

They are documented for reproducibility and design traceability.

---

Level 1 – Fixed Duel
^^^^^^^^^^^^^^^^^^^

- Minimal map
- Fixed starting positions
- Close combat only

Purpose:
Introduce basic movement and assault decisions with no ambiguity.

---

Level 2 – Increased Distance
^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Larger map
- Fixed starting positions
- Delayed engagement

Purpose:
Teach approach timing and positional patience before assault.

---

Level 3 – Ranged Combat
^^^^^^^^^^^^^^^^^^^^^^

- ``RANGED_FIRE`` action introduced
- Same spatial structure as Level 2

Purpose:
Introduce ranged preparation and discourage premature close combat.

---

Level 3b – Positional Generalization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Randomized starting positions
- Same action set and map size

Purpose:
Prevent memorization and enforce distance‑dependent decision‑making.

---

Level 3c – Decisive Closure
^^^^^^^^^^^^^^^^^^^^^^^^^^

- Same scenarios as Level 3b
- Assault‑specific reward shaping

Purpose:
Teach when decisive close combat is tactically correct rather than optional.

---

Level 4 – Spatial Tactics
^^^^^^^^^^^^^^^^^^^^^^^^

- Increased spatial depth
- Randomized starting positions
- Same actions and reward structure

Purpose:
Introduce sustained positioning, maneuver, and delayed commitment.

---

Frozen Baseline – P1 VP Defended
-------------------------------

**P1 – Baseline VP Defended (1 vs 1)** is the first scenario that represents a
**complete tactical mission** rather than an isolated skill test.

Characteristics:

- Persistent Victory Points
- Enemy explicitly defends and recaptures objectives
- Mission outcome determined at end of time
- Unclear optimal policy without risk

This scenario is treated as **frozen**:

- It is considered validated
- It is not tuned further
- It serves as a stable reference point

Subsequent curriculum progression must occur in new scenarios.

---

Validation Strategy
-------------------

Curriculum progression is validated **externally**, not via raw reward.

Each level is evaluated using:

- Mission outcome (victory / draw / defeat)
- Win‑rate against heuristic baselines
- Action usage distribution
- Tactical coherence in deterministic replays

Internal PPO metrics (loss, KL, entropy) are used diagnostically only.

Progression to the next curriculum stage requires **observable behavioral
improvement**, not numerical reward increase alone.

---

Future Curriculum Extensions
----------------------------

Future curriculum stages may introduce:

- Aggregate force metrics (strategic context)
- Multi‑unit coordination
- Terrain and cover exploitation
- Overwatch and suppression mechanics
- Deployment and operational phases

These extensions are explicitly deferred until
single‑unit spatial tactics and mission reasoning are mastered.

---

Summary
-------

The curriculum in **assault-env** is:

- Conservative by design
- Explicitly validated
- Deterministic and reproducible

Each stage builds on the previous one without invalidating learned behavior,
allowing systematic scaling from tactical primitives to full mission control.
