# 🧭 Plan Maestro de Reconstrucción y Desarrollo
## Proyecto Assault (Model‑First · Simulation‑Driven · Training‑Ready)

Este documento **actualizado** describe el estado REAL del proyecto y cómo continuar sin perder contexto.

---

## 📁 Arquitectura actual

```
assault_model/        ← Núcleo canónico del juego (reglas puras)
assault_sim/          ← Motor de simulación + observabilidad
assault_training/     ← Capa de entrenamiento (Gym‑like wrapper)
assault_ui/           ← Visualización / replay (futuro)
```

**Principios no negociables**:
- `assault_model` NO depende de nada
- `assault_sim` usa `assault_model`
- `assault_training` envuelve `assault_sim`
- No existen dos motores del juego

---

## ✅ Estado actual (verificado)

### assault_model
✔ GameState / RuntimeGameState
✔ Escenarios, mapas hex, geometría
✔ Acciones (Move, Ranged, Assault, Reaction)
✔ Victory Points y HexState

⚠️ No debe modificarse salvo nuevas reglas.

---

### assault_sim (motor estable)

✔ `SimEnv`
- reset()
- step(action)
- control de turnos
- cálculo de VP

✔ Sistema de **debug / observability**:
- DebugConfig (YAML)
- EventBus
- ConsoleObserver

✔ Configuración activa:
```
assault_sim/config/sim_config.yaml
```

Ejecuta el motor con:
```bash
python -m assault_sim.train.train
```

---

### assault_training (nuevo, no invasivo)

✔ `env_config.json`
- define escenario
- define bandos (N bandos)
- define roles (RL, heurístico, script, humano)
- define reward

✔ `TrainingEnv`
- wrapper Gym‑like
- NO implementa reglas
- llama a SimEnv internamente

⚠️ Aún sin RL conectado (siguiente fase).

---

## 📄 Configuraciones clave

### 1️⃣ sim_config.yaml (motor)

- assets
- escenario
- debug

### 2️⃣ scenario.json (mundo)

- mapa
- unidades
- bandos
- VP

### 3️⃣ env_config.json (entrenamiento)

- quién controla cada bando
- políticas
- recompensa

Cada archivo tiene una sola responsabilidad.

---

## 🧱 Fases del proyecto (reales)

### ✅ Fase 1 — Motor
✔ COMPLETADA
- SimEnv funcional
- Debug detallado

### ✅ Fase 2 — Observabilidad
✔ COMPLETADA
- Eventos: RESET, ACTION, TURN_END, VP_APPLIED, DONE

### ⏳ Fase 3 — TrainingEnv
⚠️ En progreso
- Multi‑bando
- RewardCalculator
- Controllers

### 🔜 Fase 4 — RL
- integración Gym
- self‑play

### 🔜 Fase 5 — Replay / UI

---

## 🏁 Estado final esperado

- Un solo motor
- N bandos configurables
- Entrenamiento reproducible
- Observabilidad completa
- Modular y extensible

Este documento es la **fuente de verdad** para retomar el proyecto.
