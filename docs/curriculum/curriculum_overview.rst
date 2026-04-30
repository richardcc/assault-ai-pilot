Curriculum Design Overview
==========================

This document summarizes the staged curriculum used to train
agents in assault‑env.

The curriculum is designed to introduce **exactly one new
source of complexity per stage**, avoiding reward shaping and
algorithmic changes whenever possible.

---

P1 – Single Unit Duel
---------------------

Goal:
- Learn basic movement, distance control and assault timing.

Outcome:
- Conservative but functional policy.

---

P2 – Multi‑Unit without Global Context
--------------------------------------

Goal:
- Introduce unit rotation and redundancy.

Observed Failure:
- Agent converges to permanent evasion.
- No assaults, no objective pressure.

Interpretation:
- Rational behavior given incomplete information.
- Local optimum revealed by structural asymmetry.

---

P3 – Multi‑Unit with Global Force Awareness
-------------------------------------------

Goal:
- Enable the agent to recognize numerical advantage.

Change:
- Observation space only (no rewards, no PPO changes).

Outcome:
- Degenerate behavior resolved.
- Selective aggression appears.
- Value function stabilizes.

---

