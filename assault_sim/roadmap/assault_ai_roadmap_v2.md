# ASSAULT AI ROADMAP v4 (PRODUCTION READY)

## STATUS LEGEND
- [ ] TODO
- [~] IN PROGRESS
- [x] DONE

---

# PHASE 1 — STABILIZATION ✅

## Tasks
- [x] PPO stable
- [x] No collapse after 500+ updates
- [x] Balanced action distribution

## Metrics
- action_distribution
- reward_mean
- entropy

## Done Criteria
- ALL actions > 10%
- Attack > 25%

---

# PHASE 2 — BEHAVIOR CONSOLIDATION ⚠️

## Tasks
- [x] Run 3000–4000 episodes
- [ ] Inspect replays manually
- [ ] Validate tactical behavior

## Checks
- [ ] Attacks happen in range
- [ ] No retreat spam
- [ ] No oscillation patterns
- [ ] Units do not suicide blindly ❗

## Metrics
- win_rate
- damage_ratio
- avg_reward

## Done Criteria (REAL)
- attack ∈ [25–45%]
- retreat < 25%
- damage_ratio >= 0.9 ✅ (CRITICAL)

---

# 🔥 PHASE 2.5 — COMBAT INTELLIGENCE (NEW - CRITICAL)

## Purpose
Fix decision quality in combat (WHEN to attack / NOT attack).

## Tasks
- [ ] Add trade-based reward (damage - damage_taken)
- [ ] Penalize bad engagements
- [ ] Reward efficient combat

## Metrics
- damage_per_attack
- kills_per_attack
- damage_ratio

## Done Criteria
- damage_ratio >= 0.95 ✅
- kills_per_attack improves
- winrate >= 45% ✅

---

# PHASE 3 — REWARD QUALITY

## Tasks
- [ ] Remove redundant signals
- [ ] Normalize reward scale
- [ ] Align reward with actual winning behavior

## Checks
- [ ] No conflicting incentives
- [ ] No action accidentally over-rewarded

## Done Criteria
- reward stable
- no single action dominates reward
- smooth learning curve

---

# PHASE 4 — STRATEGY-CONDITIONED POLICY

## Tasks
- [ ] Add strategy context (L3) to observation
- [ ] Modify PolicyNet (concatenate strategy)
- [ ] Remove manual action bias

## Done Criteria
- behavior adapts to strategy
- strategy → different action profiles

---

# PHASE 5 — IMITATION LEARNING

## Tasks
- [ ] Integrate DecisionEngine as teacher
- [ ] Add imitation loss
- [ ] Mix PPO + supervised loss

## Done Criteria
- faster convergence
- more stable early training

---

# PHASE 6 — OPPONENT EVOLUTION

## Tasks
- [ ] Snapshot pool of past models
- [ ] Random opponent sampling

## Done Criteria
- agent robust to multiple playstyles
- avoids overfitting to one opponent

---

# PHASE 7 — SELF-PLAY

## Tasks
- [ ] Train vs frozen snapshots
- [ ] PPO vs PPO

## Done Criteria
- continuous improvement vs past versions
- higher skill ceiling

---

# PHASE 8 — FEATURES (STATE IMPROVEMENT)

## Tasks
- [ ] Add:
    - ally_distance
    - enemy_count_near
    - threat_level
    - local advantage (#allies vs enemies)
    - line_of_sight

## Done Criteria
- improved combat decisions
- better positioning

---

# PHASE 9 — DSL (CONFIGURABLE REWARD)

## Tasks
- [ ] Move reward weights to config
- [ ] Enable quick tuning

## Done Criteria
- reward editable without code changes

---

# PHASE 10 — VECTORIZED ENV

## Tasks
- [ ] Parallel rollout environments

## Done Criteria
- faster training
- higher sample throughput

---

# PHASE 11 — FULL HRL (OPTIONAL ADVANCED)

## Tasks
- [ ] L3 PPO (strategy level)
- [ ] L2 PPO (tactical level)
- [ ] L1 learned (actions)

## Done Criteria
- hierarchical behavior
- better long-term planning

---

# ✅ GLOBAL TARGET

- winrate ≥ 50%
- damage_ratio ≥ 1.0
- non-collapsing behavior
- multiple tactics used meaningfully

---

# 🔥 KEY LESSONS

- Stability ≠ intelligence
- Exploration ≠ good decisions
- Reward must encode decision quality (not just action outcome)

---

# ✅ CURRENT STATUS (PROJECT)

- Phase 1: ✅ DONE
- Phase 2: ⚠️ PARTIAL (fails in combat)
- Phase 2.5: ❌ REQUIRED NEXT STEP
- Phase 3+: ⛔ BLOCKED until combat is fixed

---

# NOTE

Do NOT proceed to Phase 3+  
until damage_ratio and winrate improve.

Combat intelligence is the real bottleneck.