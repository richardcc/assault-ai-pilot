# 🚀 ROADMAP ENRIQUECIDO: ALPHAZERO++ (NEURO-SYMBOLIC TACTICAL SYSTEM)

## 🧠 OBJETIVO
Construir un sistema que:
- aprende (CNN + MCTS)
- razona (planificador)
- usa conocimiento (overrides)
- explica decisiones (telemetría)
- mantiene compatibilidad con el sistema actual

---

# 🏗️ ARQUITECTURA GLOBAL

Game Logic
→ Planificador
→ Encoder (state + plan)
→ CNN multi-head
→ MCTS híbrido
→ Decision layer
→ Telemetry interna
→ Metrics engine existente
→ Dashboard existente

---

# 📦 STACK TECNOLÓGICO

- torch
- numpy
- Prefect
- MLflow
- JSON logs

---

# 🔵 FASE 0 — BASELINE

- congelar sistema actual
- guardar métricas (VP entry, capture, alignment)
- guardar episodios

---

# 🔵 FASE 1 — PROYECTO NUEVO

Estructura:

alphazero_core/
  game/
  encoder/
  model/
  mcts/
  planner_adapter/
  override_engine/
  decision/
  training/
  selfplay/
  telemetry/
  integration/

---

# 🔵 FASE 2 — ENCODER

Input:
(C_state + C_plan, H, W)

Canales:
- unidades (propias/enemigas)
- objetivos
- terreno
- density
- danger
- plan (strategy maps)

Normalización: [0,1]

---

# 🔵 FASE 3 — RED

CNN Backbone:
Conv → ReLU → Residual blocks

Outputs:
- Policy jerárquica
- Value multi-head
- Risk head

---

# 🔵 FASE 4 — PLANIFICADOR (GUIDANCE)

- convertir a features
- no bloquear decisiones
- influir en policy/value

---

# 🔵 FASE 5 — OVERRIDES (REDISEÑO)

Tipos:
- Hard constraints (illegal actions)
- Soft bias (ajustes de policy)
- Value shaping

---

# 🔵 FASE 6 — MCTS HÍBRIDO

UCB:
Q + c*P*sqrt(N)/(1+n) + bias

Incluye:
- knowledge bias
- risk awareness

---

# 🔵 FASE 7 — SELF PLAY

Generar datos:
(state, improved_policy, outcome)

---

# 🔵 FASE 8 — TRAINING

Loss:
- policy CE
- value MSE
- auxiliary (opcional)

---

# 🔵 FASE 9 — TELEMETRÍA

Log:
- policy
- value
- MCTS
- overrides
- plan

---

# 🔵 FASE 10 — INTEGRACIÓN

Mantener dashboard
Añadir:
- policy insights
- value breakdown
- MCTS traces

---

# 🔵 FASE 11 — DEBUG

Analizar:
- plan vs acción
- policy vs resultado
- overrides impacto

---

# 🔵 FASE 12 — OPTIMIZACIÓN

- paralelización
- GPU
- tuning MCTS

---

# 🔥 PRINCIPIOS

- modularidad
- observabilidad
- no romper sistema actual

---

# ✅ RESULTADO FINAL

Sistema capaz de:
- aprender ✅
- razonar ✅
- explicar ✅
- escalar ✅

