# Hierarchical Reinforcement Learning Architecture

## 1. Purpose

This document describes the Hierarchical Reinforcement Learning (HRL) architecture
used in assault_sim for tactical AI decision-making.

The goal is to build a realistic, stable, and explainable tactical AI system,
aligned with practices used in professional games and simulations.

The AI must:
- Decide tactical intentions (not low-level movements)
- Execute those intentions using deterministic heuristics
- Learn *when* to apply a tactic, not *how* to execute it

---

## 2. Core Principle

**Strict separation between decision and execution.**

- Reinforcement Learning decides *what to do*
- Heuristics decide *how to do it*
- The engine enforces rules and resolves combat
- Rewards evaluate tactical outcomes, not micro-actions

This architecture avoids common RL problems such as:
- the credit assignment problem
- unstable behavior due to reward shaping
- unexplainable decisions

---

## 3. Architecture Layers

### 3.1 Strategic Layer (High-Level RL)

**Responsibility**
- Select a tactical option valid for several turns

**Characteristics**
- Small, semantic action space
- No map geometry knowledge
- No rule execution
- Operates at a lower frequency than game turns

**Example options**
- ADVANCE
- FLANK
- ATTACK
- HOLD
- RETREAT

---

### 3.2 Tactical Layer (Heuristics)

**Responsibility**
- Execute a tactical option as concrete game actions

**Characteristics**
- Deterministic
- Human-designed
- Uses pathfinding, geometry, and doctrinal rules
- Does not learn

---

### 3.3 Engine Layer

**Responsibility**
- Validate actions
- Resolve combat
- Apply rules
- Produce observable outcomes

This layer is authoritative and independent of AI logic.

---

## 4. Decision Flow

1. A unit becomes active
2. The HRL controller checks if an option is active
3. If not, RL selects a new tactical option
4. The heuristic executes the option
5. The engine resolves the action
6. Reward evaluates the option’s outcome

---

## 5. Temporal Abstraction

Each tactical option has a duration (horizon):

| Option   | Typical Duration |
|---------|------------------|
| ADVANCE | 4–6 turns |
| FLANK   | 5–7 turns |
| ATTACK  | 1–3 turns |
| HOLD    | 1 turn |
| RETREAT | 2–4 turns |

This allows RL to reason over multi-turn effects.

---

## 6. Reward Philosophy

Rewards evaluate:
- Effectiveness of the chosen option
- Tactical success or failure
- Costs and benefits of the decision

Rewards do **not** evaluate:
- Individual moves
- Path optimality
- Micro positioning

---

## 7. Benefits

- Interpretable decisions
- Stable learning
- Domain realism
- Scalable design
- Easy debugging

---

## 8. Alignment with Real Systems

This architecture matches:
- Tactical games
- Military simulators
- Hierarchical planners
- Hybrid AI systems

The RL agent governs intent, not mechanics.