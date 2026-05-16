Scenarios
=========

Scenarios define the **initial state** of the environment.

They are the primary mechanism used to:

- Control difficulty
- Introduce new tactical concepts
- Implement curriculum learning

A scenario configures *what the agent is facing*,
not *how the agent learns*.

All learning behavior emerges from interaction between the agent and
scenario constraints.

---

Scenario Definition
-------------------

A scenario is responsible for constructing the **initial tactical state**.

Specifically, a scenario must:

- Create a ``GameState``
- Define the map layout (hex grid and terrain)
- Place all units with initial positions and strength
- Define objective locations (e.g. Victory Points)
- Return unit identifiers required by the environment

Scenarios contain:

- **No reward logic**
- **No learning logic**
- **No agent behavior logic**

They represent *initial conditions only*.

---

Curriculum-Oriented Design
--------------------------

Scenarios are the core mechanism for implementing a **strict curriculum**.

Each curriculum level corresponds to a scenario (or a family of scenarios)
that introduces **exactly one new dimension of complexity**.

Typical curriculum dimensions include:

- Initial distance between units
- Size and depth of the map
- Available action set
- Randomization of starting conditions
- Objective structure (e.g. Victory Points)
- Opponent responsiveness

Learning complexity is increased **only by changing scenarios**.
Reward functions and learning algorithms remain stable within a phase.

---

Scenario Levels (Historical Progression)
----------------------------------------

The following levels describe the *historical curriculum* that led to the
final baseline scenario.

These levels are documented for completeness and reproducibility.

---

Level 1 – Fixed Duel
^^^^^^^^^^^^^^^^^^^

- Minimal map
- Fixed starting positions
- Single close combat engagement

Purpose:
Introduce basic movement and assault decisions.

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
Introduce ranged preparation and discourage premature assault.

---

Level 3b – Positional Generalization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Randomized starting positions
- Same map size and action set

Purpose:
Prevent memorization and enforce distance‑dependent decision making.

---

Level 3c – Decisive Closure
^^^^^^^^^^^^^^^^^^^^^^^^^^

- Same scenarios as Level 3b
- Assault‑specific reward shaping

Purpose:
Teach when decisive close combat is tactically correct.

---

Level 4 – Spatial Tactics
^^^^^^^^^^^^^^^^^^^^^^^^

- Larger map (increased spatial depth)
- Randomized starting positions
- Same action space and reward structure

Purpose:
Introduce sustained positioning, maneuver, and delayed commitment.

---

Baseline Scenario – P1 VP Defended (Frozen)
------------------------------------------

**P1 – Baseline VP Defended (1 vs 1)** is the first *mission‑complete*
scenario and is treated as a **frozen baseline**.

### Configuration

- Italy (PPO): 1 unit
- Enemy (heuristic): 1 unit
- Alternating‑turn self‑play
- Deterministic evaluation

### Victory Points

Victory Points are fixed map locations worth 2 points each:

========== ==========
VP         Coordinates
========== ==========
D5         (3,4)
F6         (5,5)
C9         (2,8)
========== ==========

### Enemy Behavior

The enemy is explicitly VP‑aware:

- Moves to recapture player‑controlled VP
- Otherwise converges toward the nearest VP
- Assaults whenever legally possible

This ensures that objectives are **actively contested**.

### Mission Outcome

The episode ends at a fixed time limit.

Victory is determined by Victory Points:

- ≥ 4 VP → Victory
- = 3 VP → Draw
- ≤ 2 VP → Defeat

This scenario represents a **pressure defensive mission**.
Defeat is an expected and valid outcome under conservative play.

The scenario is **frozen** and must not be modified.

---

Modular Map Design
------------------

Scenarios are designed to be **composable**.

Future scenarios may be constructed from reusable map components such as:

- Terrain patches
- Urban blocks
- Forest sections
- Chokepoints
- Objective clusters

This structure supports:

- Systematic scaling of complexity
- Procedural generation
- Robust policy generalization

---

Scenario Selection
------------------

The environment does not hardcode scenario selection.

Scenarios are injected during ``reset()`` and are used to:

- Select the current curriculum level
- Control difficulty and mission type
- Enable controlled experimentation

Changing scenarios is the **preferred method** of extending the learning
problem without modifying algorithms or rewards.

---

Determinism
-----------

All scenarios preserve determinism.

- Randomization is explicit and seed‑controlled
- Scenario construction is reproducible
- No hidden or implicit randomness exists

This guarantees consistency across training runs,
curriculum levels, and evaluation phases.
