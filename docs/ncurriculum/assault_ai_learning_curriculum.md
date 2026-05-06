# Assault AI Learning Curriculum
**Design Document (Starting Point)**

## 1. Purpose of This Document

This document defines a structured learning curriculum for training an AI agent to play *Assault* using the existing simulation engine.

The goal is to:
- Train robust agents that generalize across unit variety and scenarios
- Preserve the game rules as-is
- Use Victory Points (VP) as the only final success criterion
- Introduce complexity gradually through a curriculum

This is an executable design: each phase can be directly mapped to scenarios, rewards, and training configuration.

---

## 2. Core Design Principles (Non‑Negotiable)

1. Game rules never change (movement, ranged fire, reaction fire, close combat are always enabled)
2. Victory Points (VP) are the sole final objective
3. Curriculum logic lives outside the engine (SimEnv and combat logic are immutable)
4. The agent never knows rules explicitly—only actions, observations, and consequences
5. Each curriculum phase introduces exactly one new learning question

---

## 3. What “Curriculum” Means in This Game

The curriculum is not about unlocking mechanics. It is about introducing decisions progressively.

The agent learns by answering these questions in order:

1. Should I act at all?
2. Where should my units be?
3. How do I deal damage efficiently?
4. What risks should I avoid?
5. Which units matter more?
6. How do I convert advantage into VP?

---

## 4. Curriculum Phases Overview

| Phase | Core Question |
|------|---------------|
| Phase 0 | Do actions matter? |
| Phase 1 | Where can I survive? |
| Phase 2 | How should I attack? |
| Phase 3 | What movements are dangerous? |
| Phase 4 | Which units are valuable? |
| Phase 5 | How do I win by VP? |

---

## 5. Phase 0 — Causality and Basic Control

**Learning Question**: If I do nothing, I do not gain VP.

### Baseline Heuristic (Pseudocode)
```
for unit in active_units:
    if enemy is adjacent:
        ASSAULT(enemy)
    else:
        target = nearest(enemy or VP)
        MOVE(step_towards(target))
```

### Rewards
- Final reward = total VP
- -0.01 per turn

### Validity Criteria
- 100% of games terminate
- Agent performs actions every turn
- Combat occurs in most matches

---

## 6. Phase 1 — Implicit Positioning

**Learning Question**: Where can I be without dying quickly?

### Heuristic
```
for unit in active_units:
    threats = enemies_within(2)
    if safe_to_assault(unit, threats):
        ASSAULT(best_enemy)
    else:
        MOVE(best_safe_hex_towards_objective)
```

### Rewards
- Final reward = total VP
- -0.2 per HP lost

### Validity Criteria
- Reduced early deaths vs Phase 0
- Use of indirect paths
- Less suicidal first contact

---

## 7. Phase 2 — Choosing How to Attack

**Learning Question**: Should I shoot or assault?

### Heuristic
```
for unit in active_units:
    score_fire = expected_fire_damage - expected_return_damage
    score_assault = expected_cc_damage - expected_cc_risk

    if max(score_fire, score_assault) > 0:
        choose higher score action
    else:
        MOVE(to_better_position)
```

### Rewards
- +1 enemy unit eliminated
- -1 friendly unit eliminated
- -0.2 per HP lost
- Final reward = VP

### Validity Criteria
- Mixed use of fire and CC
- Improved damage exchange ratio
- Assaults timed after weakening targets

---

## 8. Phase 3 — Risk and Reaction Fire

**Learning Question**: Which movements are dangerous?

### Heuristic
```
for unit in active_units:
    for move in legal_moves:
        danger = learned_reaction_damage(move)
        value = positional_gain(move) - danger
    MOVE(move with highest value)
```

### Rewards
- -0.3 damage from reaction fire
- Other rewards as in Phase 2

### Validity Criteria
- Reduced reaction-fire damage
- Less use of chokepoints
- Safer advances

---

## 9. Phase 4 — Unit Value and Asymmetry

**Learning Question**: Which units are more valuable?

### Heuristic
```
for unit in active_units:
    if unit_survival_value(unit) is high:
        play_conservatively(unit)
    else:
        use_aggressively(unit)
```

### Rewards
Same as Phase 3

### Validity Criteria
- Specialists survive longer
- Smarter unit prioritization

---

## 10. Phase 5 — VP‑Oriented Strategic Play

**Learning Question**: How do I win the game, not just fights?

### Heuristic
```
if VP_leading:
    consolidate_and_defend()
else:
    take_calculated_risks_toward_VP()
```

### Rewards
- Final reward = total VP
- Small event-based rewards for capturing or holding VP

### Validity Criteria
- VP prioritized over kills
- Proper endgame behavior
- Stable results across scenarios

---

## 11. Final Rule of the Curriculum

A phase is only completed when the agent demonstrates stable, repeatable behavior that correctly answers the phase’s core question without external heuristics.

---

## 12. Conclusion

- Curriculum progresses by decisions, not mechanics
- Unit variety is introduced gradually
- Positioning is learned implicitly via consequences
- VP remains the single source of truth for success
- The existing Assault architecture fully supports this approach
