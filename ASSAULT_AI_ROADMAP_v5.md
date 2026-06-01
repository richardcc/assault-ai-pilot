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
- [x] Run 3000–4000 episodes (parallel evaluations + JSON export)
- [ ] Inspect replays manually (sample ~200)
- [ ] Validate tactical behavior (L2/L3 metrics + manual review)
- [ ] Add periodic validation during training (every 500 updates)

## ✅ BASELINE SNAPSHOT (PRE-COMBAT MODELING)
Episodes:        500
win_rate:        0.512
damage_ratio:    0.568
RL dmg/atk:      0.67
ENEMY dmg/atk:   1.29
trade_mean:      0.672
bad_attack_rate: 0.000

## UNIT ANALYSIS (SAMPLE)
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
- [x] Trade-based reward prototype (`ShapedReward`)
- [x] Penalize bad engagement (zero-damage penalty)
- [x] Reward efficient combat (extra good-trade bonus)
- [ ] Tune shaping parameters (grid/Optuna)

---

# PHASE 2.6 — COMBAT MODELING LAYER 🔥

## Core APIs (UnitInstance)
- [x] `get_attack_power_vs(target)`
- [x] `get_expected_damage(target)`
- [x] `get_combat_advantage(target)`
- [x] `is_favorable_vs(target)`

## Executor Upgrade
- [x] Use `combat_advantage` in scoring
- [~] Avoid bad trades using model predictions
- [ ] Improve targeting and prioritization

## Target Metrics
- damage_ratio ≥ 0.75 (intermediate)
- win_rate ≥ 0.55

---

# PHASE 2.7 — GAME BALANCE VALIDATION ⚖️
- [ ] Analyze unit efficiency
- [ ] Detect imbalance and propose fixes

---

# PHASE 2.8 — GAME DESIGN FIXES 🔧
- [ ] Balance infantry
- [ ] Fix bazooka
- [ ] Adjust mortars

---

# PHASE 3 — REWARD QUALITY ⛔ BLOCKED
- [ ] Complete reward-quality audit and deploy final reward function

---

# GLOBAL TARGET
- winrate ≥ 60%
- damage_ratio ≥ 1.0
- intelligent engagements

---

# NOTES & ACTIONS (May 31, 2026)
- `ShapedReward` prototype added: `assault_sim/rewards/shaped_reward.py`.
- Grid 3×3 performed; summary: `models/grid_search_summary_20260531T151216Z.json`.
- Evaluation reports saved as `metrics_report_*.json` in repo root.
- Next recommended actions:
  - Export 200 replays and perform manual tagging.
  - Increase exploration for `attack_mode` (entropy_coef / mode bonus experiment).
  - Prototype `get_expected_damage()` and integrate into executor scoring.
  - Restore fallback attack behavior in `OptionExecutor` and re-evaluate short runs.

- Recent update: `avoid_bad_trades` is temporarily disabled in `OptionExecutor` for baseline recovery.
- Short eval (200 eps) after disabling the filter shows:
  - win_rate = 0.63
  - damage_ratio = 0.59
  - trade_mean = 0.824
  - good_trade_rate = 0.414
- This indicates RL recovers attack behavior; the next step is tuning the bad-trade filter rather than leaving it off.

---

# CHANGELOG
- 2026-05-31: Added ShapedReward prototype, grid search script, and ran experiments. Metrics saved.
