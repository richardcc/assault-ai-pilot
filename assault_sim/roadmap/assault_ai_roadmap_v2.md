# ASSAULT AI ROADMAP v3 (OPERABLE)

## STATUS LEGEND
- [ ] TODO
- [~] IN PROGRESS
- [x] DONE

---

# PHASE 1 — STABILIZATION

## Tasks
- [x] PPO stable
- [x] No collapse after 500 updates
- [x] Balanced action distribution

## Metrics
- action_distribution
- reward_mean
- entropy

## Done Criteria
- ALL actions >10%
- Attack >25%

---

# PHASE 2 — BEHAVIOR CONSOLIDATION

## Tasks
- [~] Run 1000+ updates
- [ ] Inspect replays
- [ ] Validate tactics

## Checks
- [ ] Attacks in range
- [ ] No retreat spam
- [ ] No oscillations

## Metrics
- win_rate
- damage_ratio
- avg_reward

## Done Criteria
- attack ∈ [25–40%]
- retreat <20%

---

# PHASE 3 — REWARD QUALITY

## Tasks
- [ ] Remove redundant signals
- [ ] Normalize reward scale
- [ ] Align reward with strategy

## Done Criteria
- reward stable
- no action dominates reward

---

# PHASE 4 — STRATEGY-CONDITIONED POLICY

## Tasks
- [ ] Add strategy to observation
- [ ] Modify PolicyNet
- [ ] Remove manual bias

## Done Criteria
- strategy → behavior learned

---

# PHASE 5 — IMITATION LEARNING

## Tasks
- [ ] Integrate DecisionEngine teacher
- [ ] Add imitation loss

## Done Criteria
- faster convergence

---

# PHASE 6 — OPPONENT EVOLUTION

## Tasks
- [ ] Add snapshot pool
- [ ] Random sampling

## Done Criteria
- robust vs all opponents

---

# PHASE 7 — SELF-PLAY

## Tasks
- [ ] PPO vs snapshot
- [ ] freeze opponent

## Done Criteria
- improving vs past versions

---

# PHASE 8 — FEATURES

## Tasks
- [ ] ally_distance
- [ ] threat_level
- [ ] line_of_sight

---

# PHASE 9 — DSL

## Tasks
- [ ] move scoring to config

---

# PHASE 10 — VECTORIZED ENV

## Tasks
- [ ] parallel envs

---

# PHASE 11 — FULL HRL

## Tasks
- [ ] L3 PPO
- [ ] L2 PPO
- [ ] L1 learned

---

# GLOBAL TARGET

- stable winrate increase
- damage_ratio >=1.0
- no collapse

---

# NOTE

This file is meant to be actively updated during development.
Mark progress continuously.

