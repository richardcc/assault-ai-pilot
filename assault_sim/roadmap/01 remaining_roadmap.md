# Remaining Roadmap (Post-Refactor)

## PHASE 1 — Stabilization
- Run long training (1000–2000 updates)
- Verify no policy collapse
- Monitor:
  - Action distribution
  - Reward trend
  - Attack mode usage

---

## PHASE 2 — Behavior Validation
- Inspect matches manually
- Verify:
  - Coordinated attacks
  - Movement before engagement
  - Reduced random behavior

---

## PHASE 3 — L2 Scoring Refinement
- Replace procedural logic with scoring
- Standardize:
  - Distance weight
  - HP weight
  - Objective weight

---

## PHASE 4 — Reduce HOLD Bias (if needed)
- Adjust L2 scores only (not reward)
- Ensure HOLD < ~15%

---

## PHASE 5 — Attack Mode Learning
- Check indirect / close usage
- Ensure diversity in attack modes

---

## PHASE 6 — Self-Play (Major Upgrade)
- Replace heuristic opponent
- Train RL vs RL
- Monitor divergence and stability

---

## PHASE 7 — Performance Optimization
- Improve rollout throughput
- Consider vectorized env (replace multiprocessing)

---

## PHASE 8 — DSL Preparation
- Convert L2 scoring into config schema
- Externalize weights

---

## FINAL TARGET
STATE → L3 → L2 (scoring) → L1 → Reward

