The Environment
===============

AssaultEnv
----------

The core class of the reinforcement learning system is ``AssaultEnv``.

It provides a Gymnasium-compatible interface over the deterministic
Assault Engine and is designed explicitly for **self-play training**.

The environment exposes the following minimal API:

- ``reset()`` → observation, info
- ``step(action)`` → observation, reward, terminated, truncated, info

This interface is compatible with Gym-style reinforcement learning
libraries such as Stable-Baselines3.

The environment does **not** implement game rules or combat mechanics.
All game logic remains inside the Assault Engine.

---

Action Space
------------

The action space represents **agent intent**, not guaranteed outcomes.

Current action set:

- 0 — WAIT  
- 1 — MOVE_FORWARD  
- 2 — ASSAULT  
- 3 — RANGED_FIRE  

Actions are interpreted by the environment and translated into
engine-level executors.

The action space was expanded incrementally as part of curriculum
learning.

---

Curriculum Evolution of Actions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Level 1–2: WAIT, MOVE_FORWARD, ASSAULT
- Level 3+: RANGED_FIRE introduced
- Level 3c+: ASSAULT incentivized as a decisive terminal action

The environment ensures backward compatibility across levels by
keeping action semantics stable.

---

Observation Space
-----------------

Observations are returned as a dictionary of simple scalar values:

- ``my_strength``  
  Current strength of the controlled unit.

- ``enemy_strength``  
  Current strength of the opposing unit (0 if eliminated).

- ``enemy_distance``  
  Manhattan distance along the linear map.

- ``in_enemy_zoc``  
  Whether the controlled unit is inside enemy Zone of Control.

- ``can_assault``  
  Whether a melee attack is spatially possible in the current state.

Observations describe **world state only**.
They do not expose internal engine logic, dice rolls, or rule details.

---

Self-Play Turn Structure
------------------------

The environment operates in **alternating-turn self-play**.

- A single policy controls both sides.
- After each action, control switches to the opposing unit.
- Observations are always returned from the perspective of the
  current active unit.

This design avoids explicit opponent modeling while allowing
competitive behavior to emerge.

---

Rewards
-------

Rewards are computed exclusively from **state transitions**.

Base reward components:

- Positive reward for dealing damage.
- Negative reward for receiving damage.
- Positive reward for eliminating the enemy unit.
- Negative reward for losing the controlled unit.
- Small penalty for invalid actions.

The environment does not depend on engine-internal reports
(e.g. assault resolution details).

---

Assault Reward Shaping (Level 3c)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Empirical evaluation showed that agents avoided assault even when
tactically optimal.

To disambiguate terminal decisions, an additional reward is applied
when the enemy is eliminated **specifically via ASSAULT**.

This bonus:

- Is only applied on successful melee elimination.
- Does not remove penalties for premature assault.
- Does not affect ranged combat rewards.

The goal is to teach *when* to close combat, not to force it.

---

Terminal Conditions
-------------------

An episode terminates when:

- The enemy unit is eliminated.
- The controlled unit is eliminated.

Terminal observations are always valid and contain zeroed values
for missing units.

---

Scenario Integration
--------------------

The environment does not hardcode maps or starting positions.

Scenarios are defined externally and injected at reset time.

Examples:

- ``simple_duel_level3b`` — randomized positions, short map
- ``simple_duel_level4`` — larger map with increased spatial depth

Scenario selection is the primary mechanism for curriculum progression.

---

Evaluation Philosophy
---------------------

Environment-level rewards are **not** sufficient to validate learning.

Final validation is performed externally via:

- Win-rate against a heuristic baseline.
- Action usage distribution.
- Tactical coherence in longer engagements.

Internal PPO metrics are treated as diagnostic signals only.

---

Determinism
-----------

The environment inherits determinism from the Assault Engine.

- All randomness is explicit and localized.
- No global random state is accessed.
- Given identical seeds, behavior is reproducible.

This allows reliable evaluation and debugging across curriculum levels.