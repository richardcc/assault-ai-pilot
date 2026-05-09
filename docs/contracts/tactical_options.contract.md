# Tactical Options Contract

The RL agent may only select from the following options:

- ADVANCE
- FLANK
- ATTACK
- HOLD
- RETREAT

Options must:
- Be semantically meaningful
- Last multiple turns
- Not encode movement primitives
- Be executable by heuristics

The RL agent must never return engine-specific actions.
``