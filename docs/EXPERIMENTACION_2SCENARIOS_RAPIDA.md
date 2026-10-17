# Guía Rápida de Experimentación Multi-Escenario (2 Scenarios Fast Cycle)

## 1. Propósito y Contexto del Experimento

Este documento registra la configuración canónica, comandos y arquitectura del experimento multi-escenario optimizado para **EfficientZero v2**. Permite relanzar o consultar de forma inmediata la ejecución de dos escenarios sin tener que reconstruir parámetros ni buscar rutas en el historial.

### ¿Qué se está evaluando en este experimento?
1. **Rendimiento y Tiempo de Ciclo ($\text{s/iter}$):** Aceleración multi-núcleo con 6 workers paralelos para self-play (`parallel_backend: process`) junto con backprop en CUDA (`amp_dtype: bf16` y `matmul_precision: high`).
2. **Topología de Red Optimizada:** Red EfficientZero v2 compacta ($682.309$ parámetros frente a los $2,93\text{M}$ de la versión anterior) con activaciones no lineales pre-residuales y normalización por capas.
3. **Nuevos Canales Tácticos de Observación (Reemplazo de Canales Muertos):**
   - **Canal 4 (`ally_suppressed`):** Indicador binario ($1.0/0.0$) de si la unidad aliada está bajo fuego y fijada.
   - **Canal 5 (`enemy_suppressed`):** Indicador de si la unidad enemiga está suprimida (incapaz de reacción u oportunidad).
   - **Canal 6 (`vp_contest_race`):** Gradiente normalizado $\frac{d_{enemigo} - d_{aliado}}{\max(d_{enemigo}, d_{aliado}) + 1} \in [-1, +1]$ que mide la carrera hacia los puntos de victoria.
   - **Canal 11 (`local_firepower_balance`):** Balance local de fuego directo $\text{cobertura\_aliada} - \text{amenaza\_enemiga} \in [-1, +1]$.
   - **Canal 26 (`ally_fire_coverage`):** Heatmap continuo de los hexágonos batidos por el fuego aliado directo.
   - **Canal 27 (`fortification_defensive_tier`):** Grado de protección pasiva del terreno ($+1.0$ búnker, $+0.6$ trinchera, $-0.6$ campos minados, $-0.3$ alambre).

---

## 2. Comandos de Ejecución

### A. Ejecutar el Curriculum Completo (6 Fases Progresivas)
Para lanzar la ejecución encadenada de todo el curriculum (`phase1_bootstrap` hasta `phase6_self_only_stabilize`) con transferencia automática de checkpoints y evaluación de gates de promoción:

```powershell
powershell -ExecutionPolicy Bypass -File .\curriculums\self_vs_self_vs_random_2scenarios_v1\run_all_phases.ps1
```

**Parámetros útiles:**
- `-DryRun`: Realiza una comprobación en seco sin entrenar ni evaluar.
- `-StartPhase <nombre_fase>`: Comienza directamente desde una fase específica (ej. `-StartPhase phase2_mix_70_30`).
- `-ContinueFromLatestCheckpoint`: Reanuda el entrenamiento a partir del último checkpoint disponible en disco.
- `-StopOnGateFail`: Detiene el curriculum si una fase no supera sus umbrales mínimos (VP capture rate, etc.).

---

### B. Ejecutar una Sola Fase Aislada (Fast Single Cycle)
Para probar o iterar rápidamente solo sobre la Fase 1 (`bootstrap.fast`) de forma aislada:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_curriculum_cycle.ps1 -ManifestPath .\curriculums\self_vs_self_vs_random_2scenarios_v1\cycles\phase1_bootstrap.fast.cycle.json
```

---

## 3. Manifiestos y Archivos de Configuración Involucrados

| Componente | Archivo | Descripción Clave |
| :--- | :--- | :--- |
| **Manifiesto del Ciclo** | [`curriculums/self_vs_self_vs_random_2scenarios_v1/cycles/phase1_bootstrap.fast.cycle.json`](file:///c:/repos/python/assault/curriculums/self_vs_self_vs_random_2scenarios_v1/cycles/phase1_bootstrap.fast.cycle.json) | Declara los comandos de entrenamiento, evaluación en benchmark y los archivos rastreados por hash. |
| **Config Fast (Entrenamiento)** | [`curriculums/self_vs_self_vs_random_2scenarios_v1/configs/efficientzero_v2.phase1_bootstrap.fast.yaml`](file:///c:/repos/python/assault/curriculums/self_vs_self_vs_random_2scenarios_v1/configs/efficientzero_v2.phase1_bootstrap.fast.yaml) | `num_workers: 6`, `parallel_backend: process`, `device: cpu` para selfplay; `amp_dtype: bf16` para CUDA. |
| **Config Benchmark (Evaluación)** | [`assault_bench/configs/benchmark_config.curriculum_2scenarios_phase1_256_80_20.fast.yaml`](file:///c:/repos/python/assault/assault_bench/configs/benchmark_config.curriculum_2scenarios_phase1_256_80_20.fast.yaml) | `cuda_parallel_workers: 6`, `cuda_parallel_use_threads: true`, 20 semillas evaluadas en matchups cruzados con 128 simulaciones MCTS (~5 min). |

---

## 4. Dónde se Guardan los Resultados y Métricas

- **Directorio de cada Ciclo:**
  `runs_curriculum/experiments/curriculum_cycles/<TIMESTAMP>_self_vs_self_vs_random_2scenarios_v1_phase1_bootstrap_fast/`
  - `logs/01_train.log`: Log completo del entrenamiento iteración a iteración.
  - `logs/02_eval.log`: Log de la evaluación en benchmark frente a agentes random y selfplay.
  - `meta/status.json`: Estado final (`ok` o `failed`) y marcas de tiempo UTC.
  - `meta/manifest.lock.json`: Hashes SHA256 de todas las configuraciones empleadas.
- **Pesos y Checkpoints del Modelo:**
  `runs_curriculum/efficientzero_v2_<run_id>/checkpoints/` (`iter_*.pt` y `final.pt`).
- **Base de Datos DuckDB:**
  `runs_curriculum/experiments/reporting/reporting.duckdb` (tablas `catalog_models`, `catalog_trains`, `catalog_evals`).
- **Visor Visual MLOps:**
  Disponible en `http://127.0.0.1:8778` con pestañas de Topología de Red, Repetición de Partidas (Match Replay) y Diagnósticos de Cabezales.
