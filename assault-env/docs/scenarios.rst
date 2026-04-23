Scenarios
=========

Scenarios define the **initial state** of the environment.

They are the primary mechanism used to control difficulty,
introduce new concepts, and implement curriculum learning.

A scenario configures *what the agent is facing*,
not *how the agent learns*.

---

Scenario Definition
-------------------

A scenario is responsible for:

- Creating a ``GameState``
- Adding hexes and terrain
- Placing units
- Returning unit identifiers for the environment

Scenarios contain **no reward logic** and **no learning logic**.
They define *initial conditions only*.

---

Curriculum-Oriented Design
--------------------------

Scenarios are used to implement a **strict curriculum**.

Each curriculum level corresponds to a scenario (or family of scenarios)
that introduces **one new dimension of complexity**.

Typical dimensions include:

- Initial distance between units
- Available action set
- Randomization of starting positions
- Spatial depth of the map

Learning complexity is increased **only by changing scenarios**.

---

Scenario Levels
---------------

Level 1 – Fixed Duel
^^^^^^^^^^^^^^^^^^^

- Minimal linear map
- Fixed starting positions
- Single close combat engagement

Purpose:
Introduce basic movement and assault decisions.

---

Level 2 – Increased Distance
^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Longer linear map
- Fixed starting positions
- Delayed engagement

Purpose:
Teach approach timing before assault.

---

Level 3 – Ranged Combat
^^^^^^^^^^^^^^^^^^^^^^

- RANGED_FIRE action available
- Same spatial structure as Level 2

Purpose:
Introduce ranged preparation and discourage premature assault.

---

Level 3b – Generalization
^^^^^^^^^^^^^^^^^^^^^^^^

- Randomized starting positions
- Same map size and actions

Purpose:
Prevent memorization and force distance‑dependent decision making.

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
- Same action space and reward structure

Purpose:
Introduce spatial reasoning, positioning, and delayed commitment.

---

Level 5 – Terrain and Cover
^^^^^^^^^^^^^^^^^^^^^^^^^^

Terrain with defensive modifiers introduces positional tactics.
The agent learns to seek cover before ranged engagement and
closes combat once positional advantage is achieved.

---

Modular Map Pieces
------------------

Scenarios are designed to be **composable**.

Future scenarios may be constructed from reusable map fragments such as:

- Terrain patches
- Urban blocks
- Forest sections
- Chokepoints

This design supports:

- Procedural generation
- Robust generalization
- Systematic scaling of tactical complexity

---

Scenario Selection
------------------

The environment does not hardcode scenarios.

Scenario selection occurs at reset time and is used to:

- Select the current curriculum level
- Control difficulty progression
- Enable controlled experimentation

Changing the scenario is the **preferred method** for extending the
learning problem without modifying the learning algorithm.

---

Determinism
-----------

Scenarios preserve determinism.

- Randomization is explicit and bounded
- Scenario parameters are reproducible via seeding
- No hidden randomness is introduced

This ensures consistent evaluation across curriculum levels.