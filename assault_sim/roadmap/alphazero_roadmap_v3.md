# 🚀 ROADMAP ENRIQUECIDO V3: ALPHAZERO++ (NEURO-SYMBOLIC TACTICAL SYSTEM)

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

# 🔥 PRINCIPIOS DE DISEÑO (AMPLIADOS)

- nunca bloquear acciones válidas
- sustituir reglas por bias
- separación estricta de módulos
- observabilidad > modelo
- aprendizaje progresivo

## ⚠️ CORE INMUTABLE

- ❗ EL CORE NUNCA SE TOCA
- ❗ TODA LA LÓGICA ESPECÍFICA VA EN LA CAPA DE INTEGRACIÓN
- ✅ el core depende SOLO de interfaces mínimas
- ✅ el objetivo es poder optimizar/reemplazar el core sin romper nada

Ejemplo:

core → usa GameInterface
integration → implementa assault_model_adapter

---

## 🌍 ESTÁNDAR DE CÓDIGO

- TODO el código debe estar en inglés
- TODOS los comentarios deben estar en inglés
- arquitectura y nombres consistentes
- esta conversación y explicaciones → en español ✅

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

---

# 🚀 PROMPT DE ARRANQUE

You are building a clean AlphaZero++ system from scratch.

Rules:
- DO NOT modify core logic once defined
- ALL integration must happen outside core
- CODE and COMMENTS in English
- architecture must be modular and testable
- NO hard-coded overrides
- ALL knowledge must be expressed as bias or features

Your first goal:
Implement a minimal working pipeline:
Game → PlanContext → Encoder → Model (stub) → Decision → Telemetry

Keep everything simple, observable and extensible.
