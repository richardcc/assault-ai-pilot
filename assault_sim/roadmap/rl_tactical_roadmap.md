# 🧭 RL Tactical Simulator Roadmap (Progressive HRL + Self-Play)

## 🎯 Goal
Build a realistic tactical simulator with hierarchical RL and evolving opponents.

---

# 🥇 PHASE 1 — FOUNDATION (COMPLETED / CURRENT)

## Architecture
- PPO (tactical intent)
- Heuristic (execution + opponent)

## Setup
```
PPO (L2 TacticalOption)
    ↓
Heuristic executor (L1)

vs

Heuristic opponent (L1)
```

## Objectives
- Learn combat fundamentals
- Stabilize training
- Validate engine

---

# 🥈 PHASE 2 — SCALE UNITS (IN PROGRESS)

## Changes
- Increase units: 3 → 5–7
- Introduce formations (data-level first)

## Required fixes
- Target diversification
- Reward normalization (per unit)
- Anti-clustering (spacing penalty)

## Expected behavior
- Temporary instability
- Emergent coordination

---

# 🥉 PHASE 3 — ROLE AWARE HEURISTIC

## Add roles
- Rifle
- MG
- Mortar
- Bazooka

## Modify executor
- MG → holds + suppresses
- Mortar → indirect fire, no advance
- Rifle → captures, assaults

## Goal
Unlock combined arms behavior

---

# 🧠 PHASE 4 — FORMATION STRATEGY LAYER (NEW)

## Add L3
```
L3 → Formation Strategy
L2 → TacticalOption (PPO)
L1 → Heuristic
```

## Example strategies
- PRESSURE_VP
- HOLD_VP
- ELIMINATE
- SPREAD

## Implementation
- Start hardcoded
- Later learnable (PPO L3)

---

# ⚔️ PHASE 5 — EVOLVING OPPONENTS

## Current opponent
- Heuristic only

## Upgrade
- Add PPO snapshots

## Opponent pool
```
[
  Heuristic,
  PPO_snapshot_1,
  PPO_snapshot_2
]
```

## Sampling
- Random per episode

## Goal
- Increase robustness
- Avoid overfitting

---

# 🔁 PHASE 6 — SELF-PLAY CONTROLLED

## Setup
```
PPO_current vs PPO_snapshot
```

## Rules
- Use frozen models
- Maintain heuristic fallback

## Goal
- Continuous improvement
- No collapse

---

# 🚀 PHASE 7 — FULL HRL STACK

## Final architecture
```
L3 → PPO (formation strategy)
L2 → PPO (tactical options)
L1 → Heuristic / partial learned
```

## Optional
- Replace parts of heuristic with learned policies

---

# 📊 METRICS TO TRACK

- Win rate
- VP per episode
- Damage efficiency
- Formation spread (distance between units)
- VP control time

---

# ⚠️ RULES (CRITICAL)

- Never remove heuristic baseline
- Scale complexity gradually
- Normalize reward by unit count
- Use snapshot-based opponents

---

# 💥 FINAL VISION

```
From:
PPO learner vs scripted opponent

To:
Self-improving tactical ecosystem
```

---

# 🧠 KEY INSIGHT

Not building a model.

Building a learning system.
