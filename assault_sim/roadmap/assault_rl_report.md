# ASSAULT SIM — RL / PPO / HRL ENGINEERING REPORT

## CONTEXTO
Simulador táctico hexagonal con activaciones alternas por unidad y entrenamiento mediante PPO + HRL.

---

## PROBLEMA FUNDAMENTAL
El entorno es multi-agente secuencial (GE ↔ US), pero PPO asume single-agent.

Consecuencia:
- Reward contaminado
- Credit assignment incorrecto
- Inestabilidad en el aprendizaje

---

## PROBLEMAS PRINCIPALES

1. Reward mezcla acciones de ambos jugadores
2. Control parcial del agente
3. Reward demasiado local
4. Escalas desbalanceadas
5. Reward discontinuo (VP)
6. Penalización WAIT excesiva
7. Horizonte HRL incorrecto
8. Executor desacoplado
9. Overrides rompen policy

---

## SOLUCIONES

### NIVEL 1 (CRÍTICO)
- Reward solo cuando actúa RL
- Reducir magnitudes
- Reward continuo para VP
- Movimiento basado en delta
- WAIT suave

### NIVEL 2 (ALTA CALIDAD)
- Reward por bloque de turno
- Horizonte por acciones propias
- Eliminar overrides rígidos

### NIVEL 3 (PRO)
- PPO opera sobre opciones
- Reward por opción
- Mejorar executor

---

## PPO SETTINGS RECOMENDADOS

ROLLOUT_STEPS = 256
ENTROPY_COEF = 0.08
CLIP_EPS = 0.2

---

## MÉTRICAS

Añadir:
- win_rate
- avg_turns
- vp_control_time
- units_alive_ratio

---

## ROADMAP

FASE 1 (1–2 días)
- Filtrado reward
- Normalización

FASE 2 (3–5 días)
- Reward por turno
- Métricas

FASE 3 (1–2 semanas)
- HRL completo
- PPO sobre opciones

FASE 4
- Self-play
- Curriculum

---

## CONCLUSIÓN

El problema principal NO es el modelo,
sino la desalineación entre entorno y agente.

Corregido esto:
- mejora masiva de estabilidad
- aparición de estrategia real
