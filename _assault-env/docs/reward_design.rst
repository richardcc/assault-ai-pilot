Reward Design
=============

This section documents the **reward design philosophy and implementation**
used in **assault-env**.

Rewards are designed to guide learning **without encoding tactics directly**.
They shape behavior locally while preserving mission‑level decision making.

The reward function is intentionally conservative, interpretable,
and subordinate to scenario design.

---

Design Principles
-----------------

The reward system follows strict principles:

- Rewards guide **learning**, not tactics
- Tactical rules are never bypassed by reward logic
- Rewards depend only on **observable state transitions**
- Mission success is evaluated **externally** at episode end

The reward function exists solely to reduce search complexity during training.
Correct behavior must emerge from interaction with the scenario and the opponent.

---

Local Tactical Rewards
---------------------

Local rewards encourage basic competence and prevent degenerate behavior.

Movement
^^^^^^^^

- Valid movement: ``+0.01``
- WAIT action: ``-0.05``

Purpose:
Encourage purposeful movement while discouraging passivity and stalling.

---

Positioning
^^^^^^^^^^^

- Enter effective assault range: ``+0.5``
- Retreat when close to the enemy: ``-0.3``

Purpose:
Encourage correct spatial commitment without forcing combat.
The agent must still decide whether engagement is tactically sound.

---

Combat Rewards
--------------

Combat rewards are derived from **relative strength changes**.

- Inflicted damage: positive reward
- Received damage: negative reward
- Eliminating the enemy unit: bonus reward
- Losing the controlled unit: large penalty

Rewards are computed using **state differences only**.
Internal engine mechanics such as dice rolls or combat tables are never exposed.

This ensures interpretability and prevents reward hacking.

---

Victory Point Rewards
---------------------

Victory Points (VP) represent **mission objectives**, not tactical actions.

For each VP (worth 2 points):

- Capture VP: ``+0.4``
- Hold VP per turn: ``+0.2``
- Abandon VP: ``-0.3``

Purpose:
Encourage objective‑focused behavior without making VP capture risk‑free.

VP rewards are intentionally incremental and insufficient on their own
to guarantee mission success.

---

End‑of‑Mission Reward
---------------------

At the end of the episode (time limit reached), a terminal reward is applied
based on total VP controlled:

========== ============ ==========
VP Points  Outcome      Reward
========== ============ ==========
≥ 4        Victory      +10
= 3        Draw         +2
≤ 2        Defeat       -5
========== ============ ==========

This terminal reward:

- Anchors long‑horizon planning
- Stabilizes the value function
- Aligns training with mission semantics

The agent is not rewarded for *temporary* VP capture,
only for sustained control at mission end.

---

What Rewards Do NOT Do
----------------------

Rewards are explicitly **not** used to:

- Force assaults
- Encode specific tactics
- Guarantee victory
- Replace scenario or opponent design

Any behavior must emerge from the interaction between:

**agent policy × scenario structure × enemy behavior**

---

Summary
-------

The reward design in **assault-env** balances:

- Local guidance
- Strategic freedom
- Determinism
- Interpretability

Rewards assist learning while preserving the integrity of the tactical
problem defined by the scenario rather than solving it directly.
``