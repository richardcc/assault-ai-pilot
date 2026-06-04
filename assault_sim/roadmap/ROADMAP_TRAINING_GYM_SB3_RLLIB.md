# ROADMAP Training 2026 (Gym -> SB3 -> RLlib Ready)

## Contexto y objetivo

Este roadmap define la evolucion del modulo de entrenamiento para un juego por turnos con multiples activaciones por turno, con horizonte de escalado a mapas 4x y 20 unidades por bando.

Objetivos principales:
- estabilidad PPO y reproducibilidad
- interfaz de entorno estandar (Gymnasium)
- baseline solido con libreria externa
- arquitectura preparada para migrar a RLlib sin reescritura costosa
- guardrails de calidad para promover modelos automaticamente

---

## Lo que se rescata de roadmaps previos

De `assault_ai_roadmap_v5*.md`:
- foco en calidad de combate (trade, damage_ratio, behavior)
- metas cuantitativas de winrate/damage_ratio
- necesidad de validacion de balance por unidad

De `01_ROADMAP.md`:
- principio clave: no hardcodear lados ni reglas fuera del motor
- responsabilidades claras por capa (engine/runtime/controller/ui)
- runtime como fuente de verdad del flujo de activaciones

Aplicacion en este roadmap:
- mantenemos esas metas tacticas como KPI
- consolidamos separacion por capas en training/env/evaluation
- evitamos acoplar trainer con internals de simulacion

---

## Estado actual (resumen)

Completado recientemente:
- Fase 1 hardening: seeds, checkpoints con metadata, rutas/config robustas
- Fase 2: consistencia PPO accion sampleada/ejecutada con `ActionBridge`
- Fase 2 extra + Fase 3 inicial: trazas de alineacion, update secuencial LSTM, guardrails KL, evaluacion periodica y promocion de best checkpoint
- Fase B: adapter Gymnasium formal (`GymAssaultEnv`) operativo
- Fase C: baseline SB3 oficial (`train_sb3.py`, `eval_sb3.py`) con export JSON/CSV
- Integracion inferencia SB3 en backend (`SB3AIService`) con fallback heuristico

Pendiente estructural:
- contratos tipados de rollout/dataset
- pipeline RLlib-ready
- escalado y tuning para mapas x4 / 20v20

---

## Arquitectura objetivo

Capas y contratos:
- `train_app`: orquestacion run, workers, eval gate, checkpoints
- `env_adapter`: `GymAssaultEnv` (decision step = activacion RL)
- `action_bridge`: sampled/resolved/executed + trace
- `rollout_contracts`: DTO versionado de transiciones y lotes
- `learner`: PPO update secuencial con guardrails
- `metrics/eval`: evaluador unico reusable por trainer custom/SB3/RLlib
- `artifact_store`: latest/best + metadata completa

Principio de oro:
- el trainer nunca asume reglas del juego; solo consume contratos estables

---

## Roadmap por fases

## Fase A - Consolidacion tecnica (1 semana)

Objetivo:
- cerrar deuda tecnica inmediata antes de introducir Gym/SB3

Entregables:
- [x] normalizar rutas absolutas en todos los scripts de train/eval
- [ ] extraer helpers comunes de checkpoint/load/save en modulo unico
- [x] agregar validaciones de shape en ingreso a PPO update (fail-fast)
- [x] agregar smoke tests minimos: reset/step/training one-batch/eval one-episode
- [x] registrar config efectiva al inicio de cada run (seed, scenario, max_steps, paths)

KPI salida:
- 0 errores de rutas relativas en train/eval
- arranque reproducible (misma seed -> misma metrica inicial en tolerancia definida)

---

## Fase B - Gymnasium adapter formal (1 semana)

Objetivo:
- crear interfaz estandar sin romper trainer actual

Diseño:
- 1 `step()` de Gym = 1 activacion RL completa
- `action_space`: `MultiDiscrete([num_options, num_attack_modes])`
- `observation_space`: vector continuo actual (Box), documentado y versionado
- `info`: incluir alignment trace (`sampled/resolved/executed/forced`)

Entregables:
- [x] `assault_sim/envs/gym_assault_env.py`
- [x] wrapper de conversion action tuple -> action bridge
- [x] mapping `terminated/truncated` correcto
- [x] test de contrato Gym (`reset` y `step`) y determinismo con seed

KPI salida:
- `GymAssaultEnv` usable por script de random policy sin errores
- paridad de reward/episodio vs `TrainingEnv` legacy en smoke test

---

## Fase C - Baseline SB3 PPO (1 semana)

Objetivo:
- tener baseline externo robusto para comparar con trainer custom

Entregables:
- [x] dependencia `stable-baselines3` + script `train_sb3.py`
- [x] script `eval_sb3.py` reutilizando evaluator/metrics del proyecto
- [x] callbacks de checkpoint + eval periodica + TensorBoard
- [x] comparador de resultados custom vs SB3 en formato unico

KPI salida:
- baseline SB3 estable sin NaNs
- reporte comparativo con:
  - win_rate
  - damage_ratio
  - forced_ratio
  - zero_dmg_rate
  - samples/sec

Decision gate:
- si SB3 >= custom en calidad y mantenimiento, SB3 pasa a ruta recomendada

---

## Fase D - RLlib readiness (1-2 semanas)

Objetivo:
- dejar el sistema preparado para migrar a RLlib con costo medio-bajo

Entregables:
- [ ] contratos tipados `Trajectory`/`Batch` en modulo dedicado
- [ ] desacople final de evaluacion (runner agnostico)
- [ ] configuracion centralizada `TrainConfig` (archivo + dataclass)
- [ ] callbacks neutrales (checkpoint/eval/metric export)
- [ ] guia de migracion RLlib (mapping config + policy + env registration)

KPI salida:
- checklist RLlib-ready completada
- prueba de integracion minima con RLlib (entorno registrado + rollout corto)

---

## Fase E - Escalado a mapas x4 y 20v20 (2-4 semanas)

Objetivo:
- mantener throughput y estabilidad en escenarios grandes

Lineas de trabajo:
- [ ] optimizacion de simulador (hotspots de action generation/path/combat)
- [ ] curriculum de complejidad (tamano mapa, densidad de unidades, horizonte)
- [ ] control de varianza (multi-seed sistematico, evaluacion por bandas)
- [ ] tuning distribuido (actores, fragment length, minibatches)

KPI salida:
- throughput minimo objetivo definido y alcanzado
- estabilidad de entrenamiento en 3 seeds
- mejora tactica sostenida en escenarios grandes

---

## Backlog tecnico detallado (archivo por archivo)

`assault_sim/train/train_ppo.py`
- [ ] mover utilidades de checkpoint/eval a modulos dedicados
- [ ] separar orchestration del loop de update
- [ ] logging estructurado (JSONL opcional)

`assault_sim/train/ppo_trainer.py`
- [x] minibatching secuencial real (no solo full sequence batch)
- [ ] masks explicitas para attack head segun opcion
- [x] early-stop por KL sostenido y alertas de gradiente

`assault_sim/training_env.py`
- [ ] mantener como legacy adapter interno
- [ ] extraer traduccion de action_type y info en helper compartido

`assault_sim/decision/action_bridge.py`
- [x] versionar trace schema
- [ ] exposicion explicita de reglas de resolve para train vs eval

`assault_sim/evaluation/*`
- [x] unificar export de metricas en formato comun (json report + csv)
- [ ] agregar panel de alignment por opcion y por unidad

`assault_sim/envs/gym_assault_env.py` (nuevo)
- [x] contrato Gym completo
- [ ] wrappers de observacion/reward opcionales
- [x] validacion de spaces

---

## Guardrails y SLO de entrenamiento

Guardrails online:
- `approx_kl <= MAX_KL` (con early-stop de update)
- `clip_fraction` en rango estable
- `grad_norm` sin explosiones
- `nan/inf` detector en batch y loss

Gates de promocion:
- score compuesto (win_rate + damage_ratio ponderado)
- mejora minima `EVAL_MIN_IMPROVEMENT`
- no degradar forced_ratio por encima del umbral

SLO minimos:
- entrenamiento corre 24h sin crash por rutas/shape
- evaluacion 500 episodios sin excepciones

---

## Plan operativo por semanas (propuesto)

Semana 1:
- Fase A + inicio Fase B (Gym contract basico)

Semana 2:
- cerrar Fase B + Fase C (SB3 baseline completo)

Semana 3:
- Fase D (RLlib readiness) + primer smoke RLlib

Semana 4+:
- Fase E (escalado escenarios grandes + performance)

---

## Riesgos principales y mitigacion

Riesgo: desalineacion accion sampleada vs ejecutada
- Mitigacion: `ActionBridge` obligatorio + forced_ratio como KPI

Riesgo: regresion silenciosa por cambios de shape
- Mitigacion: validadores de batch y tests de contrato

Riesgo: costo de simulacion en mapas grandes
- Mitigacion: profiling temprano + curriculum + tuning de paralelismo

Riesgo: lock-in del trainer custom
- Mitigacion: Gym + evaluator neutral + config centralizada

---

## Criterio de exito final

Se considera exitoso cuando:
- el entorno Gym es la interfaz oficial de entrenamiento
- existe baseline SB3 reproducible y comparable
- el sistema esta RLlib-ready sin refactor mayor
- el entrenamiento escala a mapas x4/20v20 manteniendo estabilidad y calidad tactica

---

## Checklist de ejecucion (priorizada)

### P0 - Esta semana (bloqueantes)
- [x] Verificar rutas absolutas en todos los entrypoints de train/eval (`train_ppo.py`, `evaluate_model.py`, runners).
- [x] Crear smoke tests minimos: `env.reset()`, `env.step()`, `ppo_update(one batch)`, `evaluate(1 ep)`.
- [x] Validar guardrails online: `approx_kl`, `clip_fraction`, `grad_norm`, `nan/inf` detector.
- [x] Registrar config efectiva en inicio de run (seed, scenario, max_steps, paths, hostname).
- [x] Congelar schema de `ActionBridge` trace (`sampled/resolved/executed/forced`) y versionarlo.
- [x] Confirmar reproducibilidad base (misma seed -> variacion acotada en 3 corridas cortas). (script: `python -m assault_sim.train.repro_check`)

### P1 - Proxima semana (alto impacto)
- [x] Implementar `GymAssaultEnv` (decision step = activacion RL completa).
- [x] Definir `observation_space` y `MultiDiscrete action_space` con validacion de spaces.
- [x] Exponer alignment trace en `info` de Gym.
- [x] Crear `train_sb3.py` y `eval_sb3.py` con callbacks de checkpoint/eval.
- [x] Unificar export de metricas (json + csv) para comparar custom vs SB3.
- [x] Ejecutar benchmark comparativo inicial (win_rate, damage_ratio, forced_ratio, zero_dmg_rate, samples/sec).

### P2 - RLlib-ready (2-3 semanas)
- [ ] Introducir contratos tipados (`Trajectory`, `Batch`, `EvalResult`) en modulo dedicado.
- [ ] Extraer `checkpointing.py` y `eval_gate.py` neutrales al framework.
- [ ] Centralizar configuracion en `TrainConfig` (archivo + dataclass).
- [ ] Implementar smoke de integracion RLlib (registro env + rollout corto).
- [ ] Documentar mapping de config SB3 -> RLlib (horizonte, batch, workers, eval cadence).
- [ ] Definir criterio de migracion oficial (cuando RLlib reemplaza trainer actual).

### P3 - Escalado mapas x4 / 20v20
- [ ] Profiling de hotspots de simulacion (acciones, pathfinding, combate, encoding).
- [ ] Curriculum de complejidad (tamano mapa, numero de unidades, horizonte).
- [ ] Ajuste de paralelismo/throughput (workers, fragment length, minibatches).
- [ ] Establecer SLO de entrenamiento largo (24h sin crash, eval estable multi-seed).
- [ ] Validacion de calidad tactica en escenarios grandes con gates de promocion.

### Definition of Done por hito
- [x] P0 Done: no errores de rutas/shape y run corto reproducible estable.
- [x] P1 Done: baseline SB3 funcional y comparativa numerica publicada.
- [ ] P2 Done: pipeline RLlib-ready con smoke test exitoso.
- [ ] P3 Done: entrenamiento estable y tacticamente competitivo en mapas grandes.

### Decision de arquitectura (2026-06-05)
- [x] SB3 se adopta como ruta principal de entrenamiento (Gym + SB3 PPO).
- [x] Trainer custom queda como ruta secundaria para experimentos y validacion cruzada.

