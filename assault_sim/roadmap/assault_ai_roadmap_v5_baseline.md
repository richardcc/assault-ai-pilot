# ASSAULT AI ROADMAP v5 (COMBAT-AWARE)

## STATUS LEGEND
- [ ] TODO
- [~] IN PROGRESS
- [x] DONE

---

# PHASE 1 — STABILIZATION ✅
- [x] PPO stable
- [x] No collapse after 500+ updates
- [x] Balanced action distribution

---

# PHASE 2 — BEHAVIOR CONSOLIDATION ⚠️ (IN PROGRESS)

## Tasks
- [x] Run 3000–4000 episodes
- [ ] Inspect replays manually
- [ ] Validate tactical behavior

## ✅ BASELINE SNAPSHOT (PRE-COMBAT MODELING)
Episodes:        500
win_rate:        0.512
damage_ratio:    0.568
RL dmg/atk:      0.67
ENEMY dmg/atk:   1.29
trade_mean:      0.672
bad_attack_rate: 0.000

## UNIT ANALYSIS
US_RIFLES_43 → 0.90 dmg/atk
GE_RIFLES_43 → 1.61 dmg/atk
US_BAZOOKA_TEAM → 0.06 dmg/atk
US_81MM_MORTAR → 0.44 dmg/atk
GE_50MM_MORTAR → 0.26 dmg/atk

## Done Criteria
- attack ∈ [25–50%]
- retreat < 25%
- damage_ratio ≥ 0.8

---

# PHASE 2.5 — COMBAT INTELLIGENCE 🔥
- [ ] Trade-based reward
- [ ] Penalize bad engagement
- [ ] Reward efficient combat

---

# PHASE 2.6 — COMBAT MODELING LAYER 🔥

## Core APIs (UnitInstance)
- [ ] get_attack_power_vs(target)
- [ ] get_expected_damage(target)
- [ ] get_combat_advantage(target)
- [ ] is_favorable_vs(target)

## Executor Upgrade
- [ ] Use combat_advantage in scoring
- [ ] Avoid bad trades
- [ ] Improve targeting

## Target Metrics
- damage_ratio ≥ 0.75
- win_rate ≥ 0.55

---

# PHASE 2.7 — GAME BALANCE VALIDATION ⚖️
- [ ] Analyze unit efficiency
- [ ] Detect imbalance

---

# PHASE 2.8 — GAME DESIGN FIXES 🔧
- [ ] Balance infantry
- [ ] Fix bazooka
- [ ] Adjust mortars

---

# PHASE 3 — REWARD QUALITY ⛔ BLOCKED

---

# GLOBAL TARGET
- winrate ≥ 60%
- damage_ratio ≥ 1.0
- intelligent engagements
