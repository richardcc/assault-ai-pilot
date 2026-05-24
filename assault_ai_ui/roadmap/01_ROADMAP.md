# 🧠 Assault Engine - Roadmap Arquitectura (Activaciones Flexibles)

## 🎯 Objetivo

Implementar sistema de:

- ✅ Alternating activations (flexible)
- ✅ Runtime-driven turn system (no hardcoded)
- ✅ Compatible con:
  - Training (RL)
  - Match runner
  - Web UI

---

# 🏗️ 1. PRINCIPIOS FUNDAMENTALES

## ✅ Reglas de diseño

- ❌ NO hardcodear lados ("US", "GE")
- ❌ NO lógica de reglas en frontend
- ✅ TODO basado en GameState
- ✅ Runtime gestiona flujo
- ✅ Model es la verdad absoluta

---

# 🧠 2. DISTRIBUCIÓN DE RESPONSABILIDADES

## 🔴 assault_model (engine)

Responsabilidades:

- reglas del juego
- acciones (Move, Attack…)
- combate
- GameState

❌ NO turnos complejos  
❌ NO IA  
❌ NO UI  

---

## 🟠 RuntimeGameState (NÚCLEO NUEVO)

Responsabilidades:

- active_side
- activated_units
- alternancia de lados
- fin de turno

👉 ESTE ES EL CAMBIO PRINCIPAL

---

## 🔵 SimEnv

Responsabilidades:

- ejecutar acciones
- emitir eventos

❌ NO lógica de activaciones

---

## 🟣 Controller / Runner

Responsabilidades:

- AI vs Human
- elegir acción

❌ NO reglas de turno

---

## 🟢 Frontend

Responsabilidades:

- mostrar estado
- permitir input válido

❌ NO reglas

---

# 🔧 3. IMPLEMENTACIÓN PASO A PASO

---

## ✅ PASO 1 — RuntimeGameState

### Añadir estado

```python
self.sides = self._extract_sides()
self.active_side = self.sides[0]
self.activated_units = set()