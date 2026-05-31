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

## Done Criteria
- attack ∈ [25–50%]
- retreat < 25%
- damage_ratio ≥ 0.8

---

# PHASE 2.5 — COMBAT INTELLIGENCE 🔥 (IN PROGRESS)

## Tasks
- [ ] Trade-based reward
- [ ] Penalize bad engagements
- [ ] Reward efficient combat

---

# PHASE 2.6 — COMBAT MODELING LAYER 🔥 (CRITICAL NEW)

## Core APIs (UnitInstance)
- [ ] get_attack_power_vs(target)
- [ ] get_expected_damage(target)
- [ ] get_combat_advantage(target)
- [ ] is_favorable_vs(target)

## Executor Upgrade
- [ ] Use combat_advantage in scoring
- [ ] Avoid bad trades
- [ ] Better target selection

## Done Criteria
- damage_ratio ≥ 0.75
- win_rate ≥ 0.55

---

# PHASE 2.7 — GAME BALANCE VALIDATION ⚖️

## Tasks
- [ ] Analyze UNIT TYPE SUMMARY
- [ ] Detect imbalance
- [ ] Compare per-unit efficiency

## Done Criteria
- No unit < 0.3 dmg/atk
- No unit > 1.5 dmg/atk

---

# PHASE 2.8 — GAME DESIGN FIXES 🔧

## Tasks
- [ ] Balance Infantry (GE vs US)
- [ ] Fix Bazooka team
- [ ] Adjust Mortars

## Done Criteria
- damage_ratio ≥ 0.9
- win_rate ≥ 0.5

---

# PHASE 3 — REWARD QUALITY ⛔ BLOCKED

---

# PHASE 4 — FEATURES (UPDATED)

## Add Features
- [ ] combat_advantage
- [ ] expected_damage
- [ ] local advantage

---

# GLOBAL TARGET
- winrate ≥ 60%
- damage_ratio ≥ 1.0
- intelligent engagements


