# 🚀 ROADMAP ENRIQUECIDO V2: ALPHAZERO++ (NEURO-SYMBOLIC TACTICAL SYSTEM)

## 🧠 OBJETIVO REAL
Construir un sistema que:
- aprende (CNN + MCTS)
- razona (planificador aprendido + explícito)
- usa conocimiento sin bloquear aprendizaje (overrides → bias)
- explica decisiones (telemetría profunda)
- mantiene compatibilidad con TODO tu sistema actual

---

# 🏗️ ARQUITECTURA GLOBAL FINAL

Game Logic
→ Planificador (explícito + aprendido)
→ Encoder (state + plan)
→ CNN multi-head
→ MCTS híbrido
→ Decision layer
→ Telemetry interna
→ Metrics engine existente
→ Dashboard existente

---

# 📦 STACK TECNOLÓGICO

## Core ML
- torch
- numpy

## Backend / Orquestación
- Prefect
- MLflow

## Datos
- JSON logs
- datasets (numpy / torch)

---

# 🔥 PRINCIPIOS DE DISEÑO

- nunca bloquear acciones válidas
- sustituir reglas por bias
- separación de módulos
- observabilidad > modelo
- aprendizaje progresivo

---

# 🟢 FASE 0 — BASELINE

- congelar sistema actual
- métricas clave (VP entry, capture funnel, alignment)
- guardar episodios

---

# 🟢 FASE 1 — DESACOPLAR PLANIFICADOR

- crear PlanContext
- eliminar control directo sobre acciones
- mantener métricas y explicación

---

# 🟢 FASE 2 — REFACTOR OVERRIDES

ANTES:
if X → bloquear

DESPUÉS:
value -= penalty
policy *= weight

Tipos:
- hard: legalidad
- soft: policy bias
- shaping: value

---

# 🟢 FASE 3 — ENCODER

Input:
(C_state + C_plan, H, W)

Incluye:
- unidades
- objetivos
- presión
- planificación

---

# 🟢 FASE 4 — RED BASE

CNN → policy + value

Entrenamiento:
imitation learning

---

# 🟢 FASE 5 — STRATEGY HEAD

Añadir:
strategy_head (CAPTURE, DENY, ...)

Entrenamiento supervisado

---

# 🟢 FASE 6 — MCTS

Implementación básica

---

# 🟢 FASE 7 — MCTS HÍBRIDO

UCB = Q + cP√N/(1+n) + bias − risk

---

# 🟢 FASE 8 — VALUE MULTI-HEAD

Outputs:
- win_prob
- vp_progress
- combat_adv

---

# 🟢 FASE 9 — SELF PLAY

(state, policy, outcome)

---

# 🟢 FASE 10 — PLANIFICADOR APRENDIDO

comparar planner vs modelo

---

# 🟢 FASE 11 — TELEMETRÍA TOTAL

Log:
- policy
- value
- MCTS
- plan
- override

---

# 🟢 FASE 12 — OPTIMIZACIÓN

- paralelización
- GPU
- tuning MCTS

---

# ✅ RESULTADO FINAL

Sistema capaz de:
- aprender ✅
- razonar ✅
- explicar ✅
- escalar ✅
