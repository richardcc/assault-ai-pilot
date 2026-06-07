# ROADMAP Training 2026 (Gym -> SB3 -> RLlib Ready)

## Update operativo (2026-06-07)

Cambios implementados y validados en esta iteracion:
- Motor de victoria alineado con campania:
  - si escenario define `victory_outcomes` con `metric=objectives_captured` y `timing=end_of_last_turn`, el resultado final se decide por esa tabla.
  - semantica cerrada: victoria solo con `Vittoria` / `Vittoria totale`; `Pareggio` = empate; `Sconfitta*` = derrota del tracked side.
- Control de VP:
  - los VP mantienen ownership al quedar vacios hasta que otro bando los capture.
  - evento `VP_CAPTURED` emitido en runtime cuando cambia control.
- UI/telemetria:
  - cabecera con `VPs` por bando y progreso de `OBJECTIVES` (capturados/total + resultado de tabla).
  - estado de partida incluye `done`, `winner`, `end_reason`.
- Train/Eval multi-lado y multi-escenario:
  - `rl_sides` global (US/IT/GE) + salto automatico de combinaciones lado/escenario invalidas.
  - reporte por combinacion `side x scenario` + comparativo consolidado.
- Eval y metricas:
  - desglose por `rl_result` (win/draw/loss) y `tracked_result` (resultado de tabla de campania).
  - `end_reason` neutralizado a `objective_outcome_resolved` para comparacion cross-side.
  - fix raiz de `UNKNOWN:1` (tracker inicializado despues de reset para tener scenario valido desde episodio 1).
- Reward/observacion:
  - observacion RL extendida con progreso de objetivos (`objectives_captured`) y presion temporal.
  - shaping objetivo: tracked side aprende a capturar; no-tracked aprende a negar y tambien a capturar.
  - shaping terminal alineado a resultado de `victory_outcomes`.
- Politicas/heuristica:
  - `OptionExecutor` y `TacticalPathHeuristic` priorizan mover hacia objetivos VP relevantes cuando no hay buen ataque.
  - `HOLD` evita pasividad si existen objetivos capturables.
- Limpieza de legado:
  - eliminado fallback a checkpoints sin sufijo de bando (`sb3_latest.zip`, `sb3_vecnormalize.pkl`) en train/backend/eval.
  - artefactos oficiales solo por lado: `sb3_latest_<SIDE>.zip`, `sb3_vecnormalize_<SIDE>.pkl`.

Estado cuantitativo reciente (eval 100 eps por combinacion valida):
- US vs `mettete_i_piedi_terra_1`: win_rate ~0.265.
- US vs `battaglia_cittadina_2_1`: win_rate ~0.000.
- IT vs `battaglia_cittadina_2_1`: win_rate ~1.000.
- GE vs `mettete_i_piedi_terra_1`: win_rate ~0.785.

Conclusion operativa:
- pipeline y reglas estan coherentes;
- cuello de botella principal: performance US en cumplimiento de objetivos de captura.

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
- Victoria de campania por `victory_outcomes` integrada en runtime y UI
- Reportes de evaluacion por `side x scenario` con `rl_result` y `tracked_result`
- Limpieza de artefactos legacy (sin checkpoint generico sin bando)
- Politicas/heuristica orientadas a objetivos VP (captura y negacion)

Pendiente estructural:
- contratos tipados de rollout/dataset
- pipeline RLlib-ready
- escalado y tuning para mapas x4 / 20v20
- mejora de performance US en objetivos de captura (prioridad tactica activa)

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

## Fase A - Consolidacion tecnica (1 semana) ✅ COMPLETADA

Objetivo:
- cerrar deuda tecnica inmediata antes de introducir Gym/SB3

Entregables:
- [x] normalizar rutas absolutas en todos los scripts de train/eval
- [x] extraer helpers comunes de checkpoint/load/save en modulo unico
- [x] agregar validaciones de shape en ingreso a PPO update (fail-fast)
- [x] agregar smoke tests minimos: reset/step/training one-batch/eval one-episode
- [x] registrar config efectiva al inicio de cada run (seed, scenario, max_steps, paths)

KPI salida:
- 0 errores de rutas relativas en train/eval
- arranque reproducible (misma seed -> misma metrica inicial en tolerancia definida)

---

## Fase B - Gymnasium adapter formal (1 semana) ✅ COMPLETADA

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

## Fase C - Baseline SB3 PPO (1 semana) ✅ COMPLETADA

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

## Fase D - RLlib readiness (1-2 semanas) 🟡 EN PROGRESO

Objetivo:
- dejar el sistema preparado para migrar a RLlib con costo medio-bajo

Entregables:
- [x] contratos tipados `Trajectory`/`Batch` en modulo dedicado
- [ ] desacople final de evaluacion (runner agnostico)
- [x] configuracion centralizada `TrainConfig` (archivo + dataclass)
- [x] callbacks neutrales (checkpoint/eval/metric export)
- [ ] guia de migracion RLlib (mapping config + policy + env registration)
- [x] smoke de integracion RLlib (`python -m assault_sim.train.smoke_rllib`)

Estado de fase:
- P2 queda en estado **casi cerrado**: bloque tecnico principal completado; pendiente cierre formal de validacion final y runner de evaluacion totalmente agnostico.

KPI salida:
- checklist RLlib-ready completada
- prueba de integracion minima con RLlib (entorno registrado + rollout corto)

---

## Fase E - Escalado a mapas x4 y 20v20 (2-4 semanas) ⏳ PENDIENTE

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
- [x] reporte comparativo por `side x scenario`
- [x] desglose de resultados por `rl_result` (win/draw/loss)
- [x] desglose de resultados por `tracked_result` de campania

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
- [x] Introducir contratos tipados (`Trajectory`, `Batch`, `EvalResult`) en modulo dedicado.
- [x] Extraer `checkpointing.py` y `eval_gate.py` neutrales al framework.
- [x] Centralizar configuracion en `TrainConfig` (archivo + dataclass).
- [x] Implementar smoke de integracion RLlib (registro env + rollout corto).
- [x] Documentar mapping de config SB3 -> RLlib (horizonte, batch, workers, eval cadence).
- [x] Definir criterio de migracion oficial (cuando RLlib reemplaza trainer actual).

#### Mapping SB3 -> RLlib (referencia operativa)

- `sb3_n_steps` -> `rollout_fragment_length` (steps por worker antes de enviar muestras)
- `sb3_num_envs` -> `num_env_runners` (o `num_rollout_workers` segun API RLlib usada)
- `sb3_batch_size` / acumulacion de muestras -> `train_batch_size` (batch total por iteracion)
- `sb3_n_epochs` -> `num_sgd_iter` (pasadas SGD por batch)
- `sb3_learning_rate` -> `lr`
- `sb3_gamma` -> `gamma`
- `sb3_gae_lambda` -> `lambda_` (GAE)
- `sb3_clip_range` -> `clip_param`
- `sb3_ent_coef` -> `entropy_coeff`
- `sb3_net_arch` -> `model.fcnet_hiddens`
- `sb3_eval_freq` + `sb3_eval_episodes` -> `evaluation_interval` + `evaluation_num_episodes`

Notas:
- RLlib maneja paralelismo por workers de rollout; en CPU-heavy envs suele escalar mejor que `DummyVecEnv`.
- Mantener el mismo `GymAssaultEnv` registrado para evitar drift entre frameworks.

#### Criterio oficial de migracion a RLlib

Migrar ruta principal SB3 -> RLlib solo si se cumplen todos:
- calidad tactica no inferior en 2 corridas consecutivas (`win_rate`, `damage_ratio`, `zero_dmg_rate`, `forced_ratio`)
- throughput >= SB3 en hardware objetivo
- smoke RLlib estable y sin errores de serializacion/registro de entorno
- evaluacion multi-seed sin degradacion estadistica relevante
- operacion diaria (train/eval/checkpoint) documentada y reproducible

### P3 - Escalado mapas x4 / 20v20
- [ ] Profiling de hotspots de simulacion (acciones, pathfinding, combate, encoding).
- [ ] Curriculum de complejidad (tamano mapa, numero de unidades, horizonte).
- [ ] Ajuste de paralelismo/throughput (workers, fragment length, minibatches).
- [ ] Establecer SLO de entrenamiento largo (24h sin crash, eval estable multi-seed).
- [ ] Validacion de calidad tactica en escenarios grandes con gates de promocion.
- [ ] Recuperacion de US por objetivos de campania (capturas) con tuning dirigido de reward/curriculum.

### Definition of Done por hito
- [x] P0 Done: no errores de rutas/shape y run corto reproducible estable.
- [x] P1 Done: baseline SB3 funcional y comparativa numerica publicada.
- [ ] P2 Done: pipeline RLlib-ready con smoke test exitoso.
- [ ] P3 Done: entrenamiento estable y tacticamente competitivo en mapas grandes.

Prioridad de ejecucion actual:
- foco primario: recuperar US en objetivos de captura (campania) sin degradar IT/GE.
- foco secundario: iniciar P3 (profiling + throughput + curriculum de complejidad).

### Decision de arquitectura (2026-06-05)
- [x] SB3 se adopta como ruta oficial y unica de entrenamiento (Gym + SB3 PPO).
- [x] Trainer custom (`train_ppo.py`) queda deshabilitado por defecto (solo override explicito).

---

## Resumen ejecutivo (1 pagina)

Estado actual:
- ruta principal de entrenamiento operativa con Gym + SB3 PPO
- pipeline de evaluacion funcional con reportes JSON/CSV y metricas de alineacion
- backend integrado para inferencia SB3 con fallback heuristico
- reproducibilidad base validada en corridas cortas (seed fija)
- operacion diaria estandarizada en comandos SB3 (`train_sb3.py` + `eval_sb3.py`)
- fine-tune post-1M configurado (LR menor + reward anti-ataques de bajo valor) para mejorar `damage_ratio` y reducir `zero_dmg_rate`

Brechas pendientes (prioridad):
- P2 RLlib-ready: contratos tipados, config centralizada, checkpoint/eval gate neutrales
- smoke de integracion RLlib (registro de entorno + rollout corto)
- panel de analisis de alignment por opcion/unidad
- P3 escalado: profiling + tuning de throughput para mapas x4 / 20v20

Ajuste activo de entrenamiento (SB3):
- `train_config.json`: `sb3_learning_rate` bajado a `0.0002` y bloque de fine-tune a `500000` timesteps
- `reward_config.json`: refuerzo de castigo a malos intercambios y ataques sin dano (`bad_trade_penalty`, `zero_damage_attack_penalty`, `shaped_zero_damage_penalty`)
- objetivo del bloque: mantener `win_rate` y elevar `damage_ratio` con menor `zero_dmg_rate`

Checklist de validacion del fine-tune (go/no-go):
- [ ] `win_rate` >= 0.56 (no degradar vs baseline post-1M)
- [ ] `damage_ratio` >= 0.75 (objetivo intermedio; objetivo final > 1.00)
- [ ] `zero_dmg_rate` <= 0.50
- [ ] `forced_ratio` <= 0.10

Decision:
- GO si cumple al menos 3/4 criterios sin degradacion severa en `win_rate`
- NO-GO si `win_rate` cae por debajo de 0.52 o `damage_ratio` no mejora frente al baseline

Riesgos activos:
- costo de simulacion puede dominar el tiempo total al escalar escenarios
- falta de contratos tipados aumenta riesgo de regresiones al migrar de framework
- degradacion silenciosa de calidad tactica bajo tuning agresivo de performance

Mitigaciones:
- mantener gates de promocion por calidad (win_rate, damage_ratio, forced_ratio)
- exigir smoke RLlib antes de cualquier migracion formal
- introducir perfiles de carga por tamano de mapa y numero de unidades

Recomendacion de secuencia:
- opcion recomendada: cerrar P2 primero (2-3 semanas), luego atacar P3
- razon: reduce costo/riesgo de cambios estructurales antes de optimizar gran escala

ETA orientativa:
- P2 RLlib-ready: 2-3 semanas
- P3 escalado x4 / 20v20: 2-4 semanas
- horizonte total a "RLlib-ready + escalado inicial": 4-7 semanas

Criterio de avance a produccion interna:
- smoke RLlib en verde
- entrenamiento 24h estable sin crash
- metricas tacticas no inferiores a baseline SB3 actual en escenarios objetivo

