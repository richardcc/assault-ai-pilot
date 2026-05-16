\# PPO Assault – Level 1 Solved



This model solves the initial 1v1 duel scenario.



\## Properties

\- Algorithm: PPO (Stable-Baselines3)

\- Observation: Dict (my\_strength, enemy\_strength, zoc, can\_assault)

\- Self-play: Yes

\- Reward: +10 for enemy elimination

\- Mean episode length: 1

\- Mean reward: 10



\## Status

✅ Level 1 curriculum solved.



This model should NOT be further trained.

Use it as:

\- baseline

\- opponent

\- warm-start for next curriculum levels



