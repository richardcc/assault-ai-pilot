# Phase 01 — Heuristic and Combat Systems Interaction

## Scope

This document specifies **how the Phase 01 heuristic interacts with combat subsystems**, in particular **Ranged Fire** and **Reaction Fire**. It is a normative companion to the main Phase 01 specification.

---

## 1. Design Principle

> **In Phase 01, systems exist, but they do not teach.**

All combat subsystems are enabled in the engine, but the heuristic is intentionally blind to tactical considerations. The goal of the phase is **causality and activity**, not combat optimization.

---

## 2. Enabled Systems (Engine Level)

The Assault engine runs with **all rules enabled**:

- Movement
- Ranged Fire
- Reaction Fire
- Close Combat

No mechanic is disabled or simplified.

---

## 3. Phase 01 Heuristic Responsibilities

The Phase 01 policy (`Phase01_InitialContactPolicy`) has exactly one responsibility:

> **Guarantee action and inevitable contact.**

It must **never** attempt to reason tactically.

Formal responsibilities:

1. Request legal actions from the engine (`ActionCatalog`)
2. Avoid WAIT when a legal action exists
3. Prefer immediate contact (Assault when adjacent)
4. Otherwise advance toward a VP or enemy target

---

## 4. Ranged Fire — Heuristic Treatment

### Engine Behavior
- Ranged fire actions are generated normally by the engine
- Fire may cause damage or elimination

### Heuristic Behavior

- ✅ The heuristic **may select** a ranged fire action **incidentally**
- ❌ The heuristic does **not** prioritize ranged fire
- ❌ The heuristic does **not** score distance, cover, or damage
- ❌ The heuristic does **not** wait to improve fire conditions

**Interpretation:**

If ranged fire occurs in Phase 01, it is **emergent noise**, not instructed behavior.

---

## 5. Reaction Fire — Heuristic Treatment

### Engine Behavior
- Reaction fire is resolved automatically by the engine
- It may cause damage or elimination

### Heuristic Behavior

- ❌ The heuristic has **no awareness** of reaction fire
- ❌ The heuristic does **not** avoid possible reaction zones
- ❌ The heuristic does **not** modify movement to mitigate risk

**Interpretation:**

Reaction fire exists only to reinforce that **actions have consequences**. It must not yet influence decision-making.

---

## 6. Explicit Prohibitions (Phase 01)

The Phase 01 heuristic MUST NOT:

- Compare assault vs fire effectiveness
- Estimate damage or survival
- Model reaction triggers or danger zones
- Delay actions waiting for better conditions
- Coordinate multiple units tactically

Presence of any of the above indicates the policy is **no longer Phase 01 compliant**.

---

## 7. Correct Mental Model

From the agent's perspective:

- Fire sometimes helps
- Fire sometimes hurts
- Reaction sometimes kills
- None of this is explainable yet

The **only consistent signal** is that acting advances the game toward resolution.

---

## 8. Phase Transitions (Preview)

| System | Phase where it becomes instructional |
|------|---------------------------------------|
| Ranged Fire | Phase 02 — Survival & Efficiency |
| Reaction Fire | Phase 03 — Risk Awareness |

Phase 01 prepares the ground by ensuring the agent experiences consequences.

---

## 9. Summary

- Ranged fire and reaction fire are **enabled but not taught**
- The heuristic ignores tactical combat reasoning
- All combat outcomes are treated as causal noise
- This restriction is essential for curriculum stability

Breaking these constraints collapses the learning ladder.
