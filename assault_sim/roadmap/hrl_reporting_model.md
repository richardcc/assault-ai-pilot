# HRL Reporting Data Model (Assault AI)

## Overview
This document defines a professional data model for logging and analyzing HRL (Hierarchical Reinforcement Learning) behavior.

The model captures:
- Macro performance (episodes)
- Decision-level behavior (HRL layers L3 → L2)
- Outcomes (L1 execution results)

---

## Core Principle

STATE → DECISION → OUTCOME

---

## Tables

### 1. experiments.csv
Defines experiment configuration.

Columns:
- experiment_id
- model_type
- opponent
- scenario
- seed
- num_episodes

---

### 2. episodes.csv
One row per episode.

Columns:
- experiment_id
- episode_id
- winner
- final_vp
- steps
- rl_damage
- enemy_damage

---

### 3. decisions.csv (CORE TABLE)
One row per decision.

Columns:
- experiment_id
- episode_id
- turn
- unit_id
- L3_strategy
- L2_option
- attack_mode
- confidence
- value_estimate
- enemy_distance
- terrain
- hp

---

### 4. outcomes.csv
Execution result of each decision.

Columns:
- experiment_id
- episode_id
- turn
- unit_id
- action
- result
- damage
- kills
- unit_alive_after

---

## Relationships

Experiment → Episode → Decision → Outcome

---

## Key Insights Enabled

- Strategy to option mapping (L3 → L2)
- Context-aware decisions (terrain, distance)
- Action effectiveness (success rate)
- Tactical behavior patterns

---

## Usage

Data can be exported to CSV and analyzed using:
- Power BI
- Excel
- Python (pandas)

---

## Summary

This model enables full analysis of:
- Performance (macro)
- Behavior (micro)
- Explainability (HRL layers)

