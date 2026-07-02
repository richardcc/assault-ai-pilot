# 🚀 ROADMAP COMPLETO: MIGRACIÓN A ALPHAZERO CON TELEMETRÍA AVANZADA

## 🧠 Objetivo
Construir un sistema AlphaZero SIN perder:
- tu telemetría actual ✅
- tu dashboard ✅
- tu lógica de evaluación ✅

Y añadir:
- policy (intención)
- value (riesgo)
- MCTS (decisión real)

---

# 🏗️ ARQUITECTURA GLOBAL

Game Logic (reutilizar)
→ Encoder (nuevo)
→ CNN (policy + value)
→ MCTS
→ Self-play
→ Telemetry interna
→ Sistema de métricas actual
→ Dashboard existente

---

# 📦 STACK TECNOLÓGICO

## ML
- torch
- numpy

## Orquestación
- Prefect ✅
- MLflow ✅

## Datos
- json logs
- numpy / torch datasets

## Visualización
- dashboard actual ✅

---

# 🔵 FASE 0 — BASELINE

- congelar resultados actuales
- guardar métricas clave
- fijar escenarios test

---

# 🔵 FASE 1 — PROYECTO NUEVO

Estructura:

alphazero_core/
  game/ (reutilizado)
  encoder/
  model/
  mcts/
  training/
  telemetry/

No copiar:
- encode_state antiguo
- heurísticas internas

---

# 🔵 FASE 2 — ENCODER

Input: (C,H,W)

Canales:
- unidades propias (por tipo, con HP)
- unidades enemigas
- objetivos
- terreno
- danger map
- density maps
- estado turno

Valores normalizados 0-1

---

# 🔵 FASE 3 — RED

Conv2d( C → 32 )
ReLU
Conv2d( 32 → 64 )
ReLU
Conv2d( 64 → 64 )
ReLU
Flatten
Linear( → 128 )

Policy head:
Linear → acciones
Softmax

Value head:
Linear → 1
Tanh

---

# 🔵 FASE 4 — TELEMETRÍA INTERNA

Schema JSON:

{
  "turn": 0,
  "policy": {
    "top_actions": [...],
    "entropy": 0.0
  },
  "value": 0.0,
  "mcts": {
    "simulations": 0,
    "actions": []
  }
}

---

# 🔵 FASE 5 — MCTS

Proceso:
- selection
- expansion
- evaluation (CNN)
- backprop

Fórmula:
UCB = Q + c * P * sqrt(N) / (1+n)

---

# 🔵 FASE 6 — SELF PLAY

loop:
state → MCTS → action → next

Guardar:
(state, policy_target, outcome)

---

# 🔵 FASE 7 — TRAINING

loss:
- policy cross entropy
- value MSE

pipeline:
self-play → dataset → train

---

# 🔵 FASE 8 — INTEGRACIÓN

Conectar con dashboard:
- policy → decisiones VP
- value → evaluación riesgo
- MCTS → explicación decisiones

---

# 🔵 FASE 9 — DEBUG

consultas:
- baja prob entry VP
- correlación policy vs success

---

# 🔵 FASE 10 — OPTIMIZACIÓN

- paralelización
- batch self-play
- GPU entrenamiento

---

# 🔥 PRINCIPIOS

- no perder telemetría actual
- añadir capas internas
- observabilidad > modelo

---

# ✅ Resultado

Sistema final:
- aprende ✅
- explica ✅
- se puede mejorar ✅

Overrides layer
│
├── Hard rules (constraints)
├── Soft rules (bias)
├── Value modifiers
├── Policy modifiers
└── Telemetry hooks (CRÍTICO)


Planificador (alto nivel)
→ guía CNN + MCTS
→ no bloquea
→ no fuerza
