# 🧠 Roadmap: Migración de MLP a CNN en RL (SB3)

## 🎯 Objetivo
Pasar de un agente basado en features heurísticas (MLP) a uno con percepción espacial (CNN).

---

# ✅ Fase 0 — Estado actual
- SB3 con MlpPolicy
- Estado = vector de features
- Reward bien definido

👉 No cambiar nada aún

---

# ✅ Fase 1 — Diseño del nuevo estado

## 🔹 Objetivo
Construir input tipo imagen (C, H, W)

## 🔹 Acciones
- Definir grid (H, W)
- Definir canales:
  - unidades propias/enemigas (por tipo + HP)
  - objetivos
  - terreno (one-hot)
  - estado (activated, danger)

## 🔹 Resultado
```
obs.shape = (C, H, W)
```

---

# ✅ Fase 2 — Implementar encode_state

## 🔹 Objetivo
Convertir GameState → tensor CNN

## 🔹 Acciones
- Mapear cada hex a (i, j)
- Rellenar canales
- Normalizar valores (0–1)

---

# ✅ Fase 3 — Crear CNN en SB3

## 🔹 Objetivo
Sustituir MLP por CNN

## 🔹 Acción clave
Crear feature extractor:

```python
Conv(32)
Conv(64)
Conv(64)
FC(128)
```

---

# ✅ Fase 4 — Integrar en PPO

```python
model = PPO(
    "CnnPolicy",
    env,
    policy_kwargs=policy_kwargs,
    device="cuda"
)
```

---

# ✅ Fase 5 — Entrenamiento inicial

## 🔹 Estrategia
- Mantener reward actual
- Mantener algunas heurísticas si hace falta

---

# ✅ Fase 6 — Refinamiento

## 🔹 Acciones
- Quitar heurísticas poco a poco
- Ajustar canales
- Ajustar reward si es necesario

---

# 🚀 Fase 7 — Optimización

## 🔹 Opcional
- Multiprocessing en entornos
- Ajuste de hiperparámetros
- Añadir atención si escala

---

# 🧠 Resumen

```
MLP + heurísticas → CNN + estado espacial
```

✅ Más autonomía
✅ Mejor estrategia
✅ Mejor generalización

---

# 🔥 Checklist rápido

- [ ] encode_state → (C,H,W)
- [ ] canales definidos
- [ ] CNN implementada
- [ ] GPU activada
- [ ] entrenamiento estable

