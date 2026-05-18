# LOS System Roadmap (Assault Engine)

## Phase 1 ✅ (DONE)
- Terrain-based LOS using terrain_config
- CLEAR / HINDERED / BLOCKED
- Integrated in combat resolver

---

## Phase 2 🔥 (Next)
### Ray Tracing (Core LOS)
- Evaluate all hexes between attacker and defender
- Accumulate LOS effects:
  - 1 hindrance → HINDERED
  - 3 hindrances → BLOCKED

---

## Phase 3 🔥🔥
### Terrain Interaction Improvements
- Multiple hindrance stacking
- Forest vs buildings vs walls interaction
- Directional LOS (walls, slopes)

---

## Phase 4 💥 (Gameplay Critical)
### Spotting System (Rule 10.5)
- LOS != visibility
- Add spotting roll
- Hidden units and ambush

---

## Phase 5 🚀 (Advanced Simulation)
- Elevation system (hills, buildings)
- Indirect fire LOS rules
- Smoke / dynamic LOS blockers

---

## Final Goal
Fully simulate Assault LOS:
- Realistic visibility
- Tactical positioning
- Emergent AI behaviour
