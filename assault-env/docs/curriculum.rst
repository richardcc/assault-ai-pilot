Curriculum Learning
===================

Assault-env is explicitly designed for **curriculum learning**.

The tactical core (``assault-engine``) remains stable while the
environment progressively exposes more complex decision-making problems
to the learning agent.

Curriculum progression is achieved without modifying game rules,
mechanics, or learning algorithms.

---

Curriculum Principles
---------------------

The curriculum follows strict principles:

- Only one new concept is introduced per level
- Previously learned behavior is preserved
- Learning complexity is controlled via scenarios and rewards
- Each level is validated before progressing

This avoids catastrophic forgetting and unstable learning.

---

Stable Engine Principle
-----------------------

- The engine does not learn
- The environment does not change rules
- Only the agent learns

This guarantees determinism, reproducibility, and clean experimentation.

---

Curriculum Dimensions
---------------------

Curriculum progression is achieved by modifying:

- Initial conditions (scenarios)
- Available actions
- Reward structure
- Spatial complexity

Learning algorithms and hyperparameters remain unchanged.

---

Curriculum Levels
-----------------

Level 1 – Fixed Duel
^^^^^^^^^^^^^^^^^^^

- Minimal map
- Fixed starting positions
- Close combat only

Purpose:
Introduce basic movement and assault decisions.

---

Level 2 – Increased Distance
^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Longer linear map
- Fixed starting positions

Purpose:
Teach approach timing before assault.

---

Level 3 – Ranged Combat
^^^^^^^^^^^^^^^^^^^^^^

- RANGED_FIRE action introduced
- Same spatial structure as Level 2

Purpose:
Introduce preparation via ranged combat and discourage premature assault.

---

Level 3b – Generalization
^^^^^^^^^^^^^^^^^^^^^^^^

- Randomized starting positions
- Same action set and map size

Purpose:
Prevent memorization and force distance-dependent decision-making.

---

Level 3c – Decisive Closure
^^^^^^^^^^^^^^^^^^^^^^^^^^

- Same scenarios as Level 3b
- Reward shaping for assault victories

Purpose:
Teach when to close combat decisively.

---

Level 4 – Spatial Tactics
^^^^^^^^^^^^^^^^^^^^^^^^

- Larger linear map (7 hexes)
- Randomized starting positions
- Same actions and reward structure

Purpose:
Introduce spatial reasoning, positioning, and delayed commitment.

---

Validation Strategy
-------------------

Curriculum progression is validated externally.

Each level is evaluated via:

- Win-rate against a heuristic baseline
- Action usage distribution
- Tactical coherence across multiple episodes

Internal training metrics are used diagnostically only.

Progression to the next level requires demonstrable behavioral improvement.

---

Future Curriculum Extensions
----------------------------

Future curriculum stages may include:

- Lateral and backward movement
- Terrain and cover mechanics
- Overwatch and suppression
- Multi-unit coordination
- Deployment and strategic phases

These extensions are intentionally deferred until
spatial tactics are fully mastered.