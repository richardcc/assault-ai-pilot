The Environment
===============

AssaultEnv
----------

The core class of the reinforcement learning system is ``AssaultEnv``.

It provides a Gymnasium-compatible interface over the deterministic
``assault-engine`` tactical core and is designed explicitly for
**self-play and adversarial training**.

The environment exposes the following minimal API:

- ``reset()`` → ``(observation, info)``
- ``step(action)`` → ``(observation, reward, terminated, truncated, info)``

This interface is compatible with Gym-style reinforcement learning
libraries such as Stable-Baselines3.

The environment does **not** implement game rules or combat mechanics.
All movement validation, combat resolution, and tactical constraints
remain entirely inside the ``assault-engine``.

---

Action Space
------------

The action space represents **agent intent**, not guaranteed outcomes.

The current action set is:

- ``0`` — WAIT  
- ``1`` — MOVE_FORWARD  
- ``2`` — ASSAULT  
- ``3`` — RANGED_FIRE  
- ``4`` — MOVE_LEFT  
- ``5`` — MOVE_RIGHT  
- ``6`` — MOVE_BACKWARD  

Actions are interpreted by the environment and translated into
engine-level executors.

The environment applies penalties for invalid or tactically unsound
actions but never overrides engine rules.

---

Curriculum Evolution of Actions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The action space was expanded incrementally as part of curriculum design:

- **Early levels**: WAIT, MOVE, ASSAULT
- **Intermediate levels**: RANGED_FIRE introduced
- **Later levels**: Fine-grained movement and assault shaping

Action semantics are **never changed retroactively**, ensuring that
policies remain compatible across scenario levels.

---

Observation Space
-----------------

Observations are returned as a dictionary of simple scalar values
describing the current tactical situation:

- ``my_strength``  
  Current strength of the controlled unit.

- ``enemy_strength``  
  Current strength of the opposing unit (0 if eliminated).

- ``enemy_distance``  
  Manhattan distance to the opposing unit.

- ``enemy_dx`` / ``enemy_dy``  
  Relative spatial offset to the opposing unit.

- ``in_enemy_zoc``  
  Whether the controlled unit is inside enemy Zone of Control.

- ``can_assault``  
  Whether a melee attack is spatially possible in the current state.

Observations intentionally describe **state, not rules**.
They do not expose internal engine logic, random draws, or resolution steps.

---

Self-Play Turn Structure
------------------------

The environment operates in **alternating-turn self-play**.

- A single policy instance may control both sides.
- After each executed action, control switches to the opposing unit.
- Observations are always returned from the perspective of the
  currently active unit.

This design avoids explicit opponent modeling while still allowing
competitive and adversarial behavior to emerge naturally.

---

Rewards
-------

Rewards are computed exclusively from **state transitions and outcomes**.

The environment does not rely on engine-internal diagnostics or reports
(e.g. combat resolution details).

Reward components include:

- Positive reward for valid movement.
- Penalty for WAIT actions.
- Positive reward for entering effective assault range.
- Penalty for tactically unsound retreat.
- Combat rewards based on relative strength loss.
- Mission-level rewards based on Victory Point control.

Reward shaping is intentionally conservative and interpretability-focused.

---

Victory Points
--------------

Victory Points (VP) represent mission objectives rather than tactical
events.

In the baseline scenario:

- Each VP is worth **2 points**.
- VP are **persistent map locations**.
- Capturing and maintaining VP generates incremental reward.
- Abandoning VP produces a penalty.

VP control is evaluated throughout the episode and serves as the primary
mission signal.

---

Terminal Conditions
-------------------

An episode terminates under one of the following conditions:

- The opposing unit is eliminated.
- The controlled unit is eliminated.
- The maximum number of turns is reached.

When the episode ends due to time limit, mission outcome is determined
by Victory Points:

- ≥ 4 VP → Victory
- = 3 VP → Draw
- ≤ 2 VP → Defeat

This ensures that the episode has a clear semantic outcome even in the
absence of unit elimination.

---

Scenario Integration
--------------------

The environment does not hardcode maps, objectives, or starting positions.

All scenarios are defined externally and injected during ``reset()``.

Examples include:

- ``simple_duel_level7_P1_from_json`` — baseline VP-defended mission

Scenario selection is the primary driver of curriculum progression and
complexity scaling.

Frozen scenarios are never modified retroactively.

---

Evaluation Philosophy
---------------------

Environment-level rewards exist **only to guide learning**.

Learning success is evaluated externally through:

- Mission outcome (victory / draw / defeat)
- Victory Point control consistency
- Action usage distributions
- Tactical coherence observed in deterministic replays

Internal PPO metrics are treated as diagnostic signals rather than final
performance indicators.

---

Determinism
-----------

The environment inherits full determinism from the ``assault-engine``.

- All randomness is explicit and controlled.
- No global random state is accessed implicitly.
- Given identical seeds, behavior is fully reproducible.

Determinism is a core requirement for:

- Debugging
- Curriculum validation
- Comparative evaluation across training runs