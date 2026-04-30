# 🧭 Plan Maestro de Reconstrucción y Desarrollo
## Proyecto Assault (Model‑First, Simulation‑Driven)

Este documento describe el plan operativo completo para retomar el proyecto aunque se pierda el contexto.

---

## 📁 Arquitectura objetivo

assault_model/   ← Núcleo canónico (reglas, estado, acciones)
assault_sim/     ← Ejecución, simulación, entrenamiento
assault_ui/      ← Visualización, replay, juego humano (futuro)

Principios:
- assault_model no depende de nada
- assault_sim usa assault_model
- assault_ui usa assault_sim + assault_model

---

## ✅ Estado actual

En assault_model ya existen:
- GameState y RuntimeGameState
- Scenario, Map, Hex, geometría hex
- Acciones (Move, Ranged, Assault, ReactionFire)
- Combate con dados, perfiles, críticos
- HexState y Victory Points

El modelo es suficiente y no debe tocarse salvo nuevas reglas.

---

## 🎯 Estrategia decidida

- No mantener benchmarks legacy
- No compatibilidad forzada
- Empezar limpio en assault_sim
- Prioridad absoluta: train funcional

---

## 🧱 FASE 1 — assault_sim

### 1. SimEnv

Archivo: assault_sim/sim_env.py

Debe implementar:
- reset(scenario_name)
- step(action)

reset():
- carga scenario
- crea GameState
- envuelve en RuntimeGameState

step():
- aplica acción
- resuelve combate
- aplica reaction fire
- actualiza hex y VP
- devuelve (obs, reward, done, info)

---

### 2. ActionCatalog

Archivo: assault_sim/action_catalog.py

Responsabilidad:
- traducir acción discreta → Action del modelo

Implementación inicial mínima.

---

## 🧱 FASE 2 — Entrenamiento

Archivo sugerido:
assault_sim/train/train.py

Debe:
- crear SimEnv
- ejecutar episodios
- elegir acciones (aleatorio o heurístico)
- imprimir VP finales

---

## 🧱 FASE 3 — Snapshot y Replay

- GameStateSnapshot
- guardado por paso o turno

Vive en assault_sim, no en model.

---

## 🧱 FASE 4 — Stats

- VP por turno
- duración de partida
- métricas de combate

---

## ✅ Orden para retomar desde cero

1. Leer este documento
2. Revisar assault_model
3. Crear SimEnv
4. Implementar reset
5. Implementar step
6. Crear ActionCatalog
7. Crear train.py
8. Ejecutar un episodio
9. Añadir replay
10. Añadir UI

---

## 🏁 Estado final esperado

- Motor táctico ejecutable
- Train funcional
- Reglas centralizadas
- Sistema extensible
