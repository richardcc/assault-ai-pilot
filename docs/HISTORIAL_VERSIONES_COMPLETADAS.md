# Historial Canónico de Versiones e Hitos Consolidados (Changelog Técnico)

> **Registro Oficial Inmutable de Entregas, Calidad y Linaje de Versiones**  
> Este documento constituye el libro de registro autoritativo de todas las versiones publicadas, tareas completadas, hitos consolidados y fases históricas archivadas de la plataforma **Assault**.  
> Para consultar la planificación activa, prioridades inmediatas y próximas iniciativas, refiérase a la [**Hoja de Ruta Evolutiva (Roadmap Maestro)**](05_ROADMAP_EVOLUTIVO.md).

---

## 1. Directivas de Gobernanza y Criterios de Consolidación

Una versión o tarea se considera formalmente **Consolidada** y se archiva en este catálogo únicamente cuando satisface los cuatro pilares del marco de calidad de Assault:
1. **Pila Pura EfficientZero V2:** Desarrollo nativo sobre el stack moderno (`agents/efficientzero_v2/`), sin shims ni dependencias de MuZero legacy (100% decomisionado).
2. **Suite de Verificación en Verde:** Superación estricta de la suite de pruebas unitarias y de integración (`pytest agents/efficientzero_v2/tests/`).
3. **Validación Cuantitativa en Benchmark:** Cumplimiento de los umbrales de rendimiento táctico (Win Rate, Tactical Quality Score TQS, CER y Asymmetry Gap).
4. **Registro de Versión Obligatorio:** Asociación explícita e inmutable a la subversión de la plataforma en la que se integró (`vMAJOR.MINOR.PATCH`).

---

## 2. Linaje y Cronología de Entregas

A continuación se registra el historial de versiones formal (`vMAJOR.MINOR.PATCH`). Las fases técnicas y científicas ya completadas y verificadas contra tests unitarios y benchmarks se archivan formalmente en esta sección de referencia.

```mermaid
flowchart TD
    %% Subgraphs por épocas / ciclos cronológicos
    subgraph C1["ÉPOCA 1: CIMENTACIÓN Y MOTOR FÍSICO VOEC (2024 - 2025)"]
        v10["<b>v1.0.0</b><br/>• Motor VOEC Base Axial (q,r)<br/>• Reglas Infantería, Balística y LOS<br/>• Simulación Estocástica"]:::cBase
        v15["<b>v1.5.0</b><br/>• Two-Hot 61 Átomos con Symlog<br/>• HL-Gauss (DeepMind 2024)<br/>• Convolución Hexagonal Nativa"]:::cBase
        v10 --> v15
    end

    subgraph C2["ÉPOCA 2: EFFICIENTZERO V2 Y RENDIMIENTO HRL (2025 - 2026)"]
        v20["<b>v2.0.0</b><br/>• EfficientZero V2 Canónico<br/>• 10 Cabezas Tácticas Auxiliares<br/>• Balanceo PCGrad + MacroPlanner HRL"]:::cEZV2
        v21["<b>v2.1.0</b><br/>• Búsqueda Gumbel + ACT Adaptativo<br/>• InputChannelGate (SE Dinámico)<br/>• Invarianza FCN Zero-Shot"]:::cEZV2
        v22["<b>v2.2.0</b><br/>• Engine Alto Rendimiento CoW (>109k clones/s)<br/>• Ray-Casting LOS (>4.9k steps/s)<br/>• Streaming Binario MessagePack"]:::cEZV2
        v23["<b>v2.3.0</b><br/>• Final Territory Ownership (FCN)<br/>• Asaltos Combinados Secuenciales<br/>• Two-Hot Asimétrico"]:::cEZV2
        v15 --> v20
        v20 --> v21
        v21 --> v22
        v22 --> v23
    end

    subgraph C3["ÉPOCA 3: GOBERNANZA, PERFILADO Y MLOPS FORENSE (OCTUBRE 2026)"]
        v240["<b>v2.4.0</b><br/>• Zero-Mock Integral y DuckDB/Parquet<br/>• XAI Causal §13 e Inventario Jerárquico"]:::cGov
        v241["<b>v2.4.1 - v2.4.2</b><br/>• Perfilado Unidades Fases 1 & 2<br/>• Contratos Doctrinales y Canales 2D"]:::cGov
        v243["<b>v2.4.3</b><br/>• Mutación Dinámica Doctrinal<br/>• Modulación Prior MCTS (+35%)"]:::cGov
        v244["<b>v2.4.4</b><br/>• Observabilidad MLOps Puerto 8778<br/>• Telemetría Forense y Badges de Rol"]:::cGov
        v245["<b>v2.4.5</b><br/>• Evaluación y Verificación en Currículum<br/>• Métricas Doctrinales y Parity Gate"]:::cGov
        v250["<b>v2.5.0 [ACTUAL]</b><br/>• Potencial Radial VPs (Ng et al. 1999)<br/>• Sesgo MCTS y Poda 40% Estéril"]:::cActive
        v23 --> v240
        v240 --> v241
        v241 --> v243
        v243 --> v244
        v244 --> v245
        v245 --> v250
    end

    classDef cBase fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc;
    classDef cEZV2 fill:#0f2e4a,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef cGov fill:#134e4a,stroke:#2dd4bf,stroke-width:2px,color:#ffffff;
    classDef cActive fill:#064e3b,stroke:#34d399,stroke-width:3px,color:#ffffff;
```

### Matriz Cronológica Resumen de Versiones y Hitos Consolidados

| Versión | Época / Ciclo | Fase Técnica / Doctrinal | Componentes Clave y Rendimiento Verificado | Estado |
| :--- | :--- | :--- | :--- | :--- :---: |
| **`v1.0.0`** | 2024-2025 | Cimentación VOEC | Coordenadas axiales $(q, r)$, balística dados de combate, LOS por elevación, simulación estocástica. | `ARCHIVADO 🗄️` |
| **`v1.5.0`** | 2024-2025 | Representación y Geometría | Two-Hot 61 átomos con Symlog, HL-Gauss (DeepMind 2024), convolución hexagonal nativa. | `ARCHIVADO 🗄️` |
| **`v2.0.0`** | 2025-2026 | Multi-Task Táctico y HRL | 10 cabezas tácticas auxiliares, balanceo adaptativo PCGrad, MacroPlanner HRL con roles doctrinarios. | `ARCHIVADO 🗄️` |
| **`v2.1.0`** | 2025-2026 | Búsqueda Eficiente e Invarianza | Búsqueda Gumbel MuZero + ACT adaptativo ($\sim 60\%$ aceleración), InputChannelGate (SE), invarianza FCN zero-shot. | `ARCHIVADO 🗄️` |
| **`v2.2.0`** | 2025-2026 | Rendimiento Extremo | CoW State con delta ($>109{,}000$ clones/s), Ray-Casting LOS ($>4{,}900$ steps/s), streaming binario MessagePack. | `ARCHIVADO 🗄️` |
| **`v2.3.0`** | 2025-2026 | Dinámicas Avanzadas | Predicción Final Territory Ownership, asaltos combinados secuenciales, Two-Hot asimétrico. | `ARCHIVADO 🗄️` |
| **`v2.4.0`** | Octubre 2026 | Gobernanza y Telemetría Canónica | Zero-Mock estricto, desacoplamiento DuckDB/Parquet, XAI Causal §13 e Inventario Jerárquico Canónico. | `ARCHIVADO 🗄️` |
| **`v2.4.1`** | Octubre 2026 | Perfilado Unidades (Fase 1) | Contratos doctrinales formales, catálogo de 8 roles canónicos, validación de esquemas JSON/dataclass. | `ARCHIVADO 🗄️` |
| **`v2.4.2`** | Octubre 2026 | Perfilado Unidades (Fase 2) | Expansión sensorial a 32 canales axiales con proyección 2D de roles y perfiles tácticos. | `ARCHIVADO 🗄️` |
| **`v2.4.3`** | Octubre 2026 | Perfilado Unidades (Fase 3) | Mutación dinámica de roles en `MacroStrategyPlanner` y modulación prior MCTS ($+35\%$). | `ARCHIVADO 🗄️` |
| **`v2.4.4`** | Octubre 2026 | Observabilidad Forense (Fase 4) | Telemetría forense integral, badges de roles/mutaciones y visor MLOps en puerto 8778 (222 tests en verde). | `ARCHIVADO 🗄️` |
| **`v2.4.5`** | Octubre 2026 | Evaluación en Currículum (Fase 5) | Harness de evaluación canónico (`eval.py`), métricas de rol (`recon_survival`, `fire_support_stationarity`, `spearhead_vp`), parity report y guardrails de currículum (228 tests en verde). | `ARCHIVADO 🗄️` |
| **`v2.5.0`** | Octubre 2026 | Captura Progresiva VPs (Línea 2) | Andamiaje de potencial radial invariante $\Phi(s)$ (Ng et al. 1999), sesgo MCTS + poda 40%, factor de urgencia temporal $\tau=t/T$ (Devlin & Kudenko 2012), penalización por parálisis en campo abierto y canales sensoriales 36-37 (218 tests al 100% en verde). | `CONSOLIDADO 🟢` |
| **`v2.5.1`** | Octubre 2026 | Fidelidad Canónica a max_turns y Paso Completo de Asalto | Presupuesto temporal seguro en autojuego (`scenario_max_turns * max(units * 2, 20)`), erradicación de timeout prematuro en Turno 8, ajuste de max_steps a 120/180 en benchmarks, y elevación de vp_potential_weight / vp_urgency_lambda a 1.5. | `CONSOLIDADO 🟢` |
| **`v2.5.2`** | Octubre 2026 | Estabilidad de Telemetría Curricular y ELO Calibrado | Ponderación multi-perfil de win rate en runner PowerShell, alineación de tracked_side en auto-juego espejo, etiquetado nativo EfficientZeroV2 en controladores, exportación ONNX para Netron y visualización condicional de Gates en el visor MLOps. | `CONSOLIDADO 🟢` |
| **`v2.5.3`** | Octubre 2026 | Optimización Evolutiva de Ciclos y Desacoplamiento de Checkpoints | Erradicación de herencia de checkpoints externos en lanzamientos desde cero (tabula rasa garantizada), analizador evolutivo de ejecuciones pasadas (`evolutionary_cycle_optimizer.py`), promoción automática del ciclo ganador $C_X \to C_1$ (nuevo baseline) y síntesis adaptativa de variantes $C_2$ (explotación/refinamiento) y $C_3$ (exploración/agresividad). | `CONSOLIDADO 🟢` |


## 3. Fases Recientes Consolidadas (Ciclos v2.4.x - v2.5.x — Octubre 2026)

#### v2.5.3 — Optimización Evolutiva de Ciclos y Desacoplamiento Estricto de Checkpoints [CONSOLIDADO 🟢]
* **Objetivo**: Garantizar que los curriculums lanzados desde cero entrenen siempre sin interferencias de checkpoints externos (tabula rasa limpia), implementando simultáneamente un mecanismo evolutivo de hiperparámetros donde cada fase aprenda de ejecuciones previas: el ciclo ganador $ se convierte en el nuevo $ (baseline) y se sintetizan automáticamente las variantes adaptativas $ (explotación/refinamiento) y $ (exploración/agresividad).
* **Componentes Consolidados**:
  * **Aislamiento Estricto de Pesos en Lanzamientos desde Cero**:
    * Eliminación sistemática de cualquier residuo de 
esume_checkpoint o checkpoint_path en las configuraciones base de fase y en los planes adaptativos. Cada ejecución desde cero recorre sus fases de forma autónoma sin contaminación de modelos previos.
  * **Optimizador Evolutivo de Ciclos (gents/efficientzero_v2/curriculum/evolutionary_cycle_optimizer.py)**:
    * Auditoría automática del historial de ejecución (curriculum_phase_traceability.jsonl) para identificar el ciclo ganador de cada fase según promoción formal de gate (promote), mejor de ciclos (promote_best_of_cycles) o máxima puntuación TQS/Win Rate.
    * Promoción de los hiperparámetros ganadores de $ a la configuración base $ de la fase para futuras ejecuciones.
    * Síntesis inteligente de variantes adaptativas:
      * **$ (Explotación y Convergencia Táctica)**: $+5\%$ tasa de reanálisis, temperatura MCTS más conservadora ($-0.05$), incremento de updates por iteración ($+2$) y mayor peso de potencial de VPs ($+0.10$).
      * **$ (Exploración y Agresividad Territorial)**: $+15\%$ a bonificaciones de captura y progreso hacia VPs, mayor peso a la pérdida de objetivos territoriales ($+0.04$), temperatura MCTS expandida ($+0.05$) y $+4$ updates de entrenamiento.
    * Persistencia de especificaciones en cycles/<phase>.adaptive_cycles.yaml y registro de linaje generacional en curriculum_generation_lineage.jsonl.
  * **Integración Nativa en Runner Curricular (curriculums/common/run_dynamic_gated_curriculum.ps1)**:
    * Build-ResumeOverlayConfig consulta dinámicamente el plan adaptativo de la fase (daptive_cycles.yaml) y aplica la estrategia correspondiente a cada iteración de ciclo ($, $, $).
    * Paso final automático de evolución al completar todas las fases del currículum.
  * **Suite de Pruebas Automatizadas (	est_evolutionary_cycle_optimizer.py)**:
    * 4 tests unitarios dedicados en verde validando auditoría de trazas, síntesis de variantes, eliminación de checkpoints y ejecución e2e.


#### v2.5.2 — Estabilidad Forense de Telemetría Curricular, Evaluación Asimétrica y Calibración ELO `[CONSOLIDADO 🟢]`
* **Objetivo**: Corregir anomalías de cálculo en la tasa de victorias no-timeout en evaluaciones curriculares multi-perfil, erradicar la asimetría de evaluación en autojuego espejo (self-play EZv2 vs EZv2), asegurar la integridad del ancla ELO Bradley-Terry ante empates, y dinamizar el estado de promoción en el visualizador MLOps con cumplimiento de UI en inglés.
* **Componentes Consolidados**:
  * **Agregador Ponderado Multi-Perfil en Runner Curricular (`curriculums/common/run_dynamic_gated_curriculum.ps1`)**:
    * Cálculo ponderado por episodios no-timeout para `resolved_non_timeout_win_rate`, eliminando la sobrescritura arbitraria con la primera fila (`Select-Object -First 1`), la cual causaba lecturas espurias de 0.0% cuando el primer perfil evaluado era un empate de autojuego.
  * **Alineación de Perspectiva en Auto-Juego Espejo (`assault_bench/episode_runner_impl.py`)**:
    * En perfiles `ezv2_selfplay` con múltiples candidatos, priorización del bando trazado (`tracked_side` definido en el escenario) en lugar de asignar arbitrariamente el lado al primer bando en mover (`obs.to_play`), garantizando que las victorias del agente en el bando activo computen correctamente.
  * **Erradicación de Vestigios MuZero en Controladores (`assault_bench/benchmark_result_builder.py`)**:
    * `_controller_label_from_policy` mapea de forma limpia y estricta a `EfficientZeroV2` ante políticas `mcts`/`ezv2`, cumpliendo la directiva de decomisión total de MuZero.
  * **Robustez en Ancla Bradley-Terry y Manejo de Empates (`mlops/reporting/viewer_frontend/src/curriculumMetrics.ts`)**:
    * Acotación balanceada $[0.15, 0.85]$ en `computeStepAnchorElo` para el perfil de autojuego, previniendo caídas catastróficas de más de 700 puntos ELO por empates o sesgos asimétricos.
    * Fallback automático al score agregado de la fase en `extractStepTraceMetrics` cuando la tasa resuelta indica 0 pero existen victorias netas en otros perfiles.
  * **Resolución del Fallo de Evaluación en Coaliciones Multi-Bando (`assault_bench/episode_runner_impl.py`)**:
    * Corrección del cálculo de victoria cuando la política evaluada controla múltiples bandos en coalición (`winner in eval_candidates`), resolviendo el artefacto de `mettete_i_piedi_terra_1` donde 24 victorias del defensor alemán `GE` (85.7% de WR real) se computaban erróneamente como 0.0% por esperar `IT`.
  * **Estandarización del Protocolo MLOps Safeguard en Informes de Ejecución (`docs/informes_ejecucion/`)**:
    * Integración de 5 salvaguardas obligatorias en la cabecera canónica (`00_CABECERA_INFORMES_EJECUCION.md`) y en el Informe 01 (`INFORME_01_CURRICULUM_Y_AUDITORIA_TACTICA.md`) para auditar formalmente coaliciones, simetría en auto-juego, agregación multi-perfil, ancla ELO y correspondencia pasos-turnos antes de declarar regresiones.
  * **Visualizador de Linaje MLOps Condicional y 100% en Inglés (`CurriculumLineageFlow.tsx`)**:
    * Reemplazo del badge estático `★ PROMOVIDO` por indicación dinámica real: `★ PROMOTED` (verde) ante `PASS`/`promote`, y `⚠️ GATE FAILED (HOLD)` (rojo/ámbar) ante fallos en los criterios del gate.
    * Traducción integral al inglés de todos los textos, tooltips, etiquetas de conectores e hitos de progresión táctica.
  * **Exportador ONNX y Visualización de Topología en Netron (`mlops/reporting/onnx_exporter.py`, `NetworkTopologyTab.tsx`)**:
    * Módulo especializado de exportación a formato abierto ONNX (`onnx 1.23.2`) mediante trazado dinámico PyTorch (`torch.onnx.export`).
    * Exportación modular desacoplada en 3 grafos computacionales independientes:
      1. `initial_inference.onnx`: Red de Representación + Cabezas Iniciales de Política, Valor y las 4 Cabezas Tácticas Auxiliares (`threat_map`, `attrition`, `morale`, `final_ownership`).
      2. `recurrent_inference.onnx`: Red Dinámica Recurrente (predicción de siguiente estado latente + recompensa) + Cabezas de Política y Valor.
      3. `representation_tower.onnx`: Backbone puro de extracción de características espaciales desde el tensor de observación $(B, 38, 16, 16)$ al espacio latente $(B, 48, 16, 16)$.
    * Endpoints REST en el visor MLOps (`POST /api/model/export-onnx`, `GET /api/model/export-onnx`, `GET /api/model/download-onnx`).
    * Panel de control interactivo en la pestaña de Topología del Dashboard MLOps con botón de exportación bajo demanda, descarga directa de los 3 archivos `.onnx` y acceso directo a [Netron.app](https://netron.app) para auditoría e inspección visual de capas, pesos y flujos tenoriales.
    * Corrección oportuna de interfaz de usuario: 100% de los textos y controles de la pestaña de Topología de Red migrados al inglés canónico.

#### v2.5.2 — Orquestación Unificada de Currículum Multi-Etapa, Linaje de Checkpoints E2E, Modulación Intrínseca de VPs y Reseteo Limpio `[CONSOLIDADO 🟢]`
* **Objetivo**: Garantizar un flujo único de extremo a extremo entre el currículum de aceleración hacia VPs (Etapa 1) y el currículum multi-escenario de autojuego progresivo (Etapa 2), encadenando automáticamente los checkpoints promovidos para mantener la genealogía unificada bajo un único modelo en el dashboard MLOps, modulando sensorial y analíticamente el valor intrínseco de cada VP ($v_{vp}/2.0$) y proporcionando una herramienta de archivado seguro y reseteo limpio de entorno.
* **Componentes Consolidados**:
  * **Encadenamiento Automático de Etapas en Master Pipeline (`run_full_multi_curriculum_pipeline.ps1`)**:
    * Parámetro `ChainStageCheckpoints = $true` por defecto (con flag `-NoChain` opcional). Al finalizar la Etapa 1 (`vp_acceleration_v1`), el checkpoint promovido de la Fase 4 (`phase4_tactical_gela_mastery`) se resuelve y se transfiere automáticamente a la Etapa 2 (`self_vs_self_vs_random_2scenarios_v1`) mediante `ExplicitStartCheckpoint`.
    * La Fase 1 de la Etapa 2 genera un overlay de reanudación (`resume_checkpoint`), enlazando el `parent_run_id` directamente al ciclo final de la Etapa 1. Con ello, `build_catalog.py` y DuckDB registran las 11 fases (4 de aceleración + 7 multi-escenario) como un **único modelo genealógico continuo** en el Dashboard MLOps.
  * **Archivado Seguro y Reseteo Limpio (`scripts/reset_curriculum_environment.ps1` y flag `-CleanStart`)**:
    * Herramienta no destructiva que traslada todas las ejecuciones pasadas (`runs/`, `runs_curriculum/`, ciclos y metadatos) a `runs_archive/archive_<timestamp>/`.
    * Regeneración inmediata del catálogo Parquet y la base DuckDB (`reporting.duckdb`) en estado limpio (0 modelos), permitiendo lanzamientos desde cero completamente aislados.
  * **Modulación Intrínseca por Valor de Hexágono VP**:
    * `voec_sim/core/simulator.py`: Exportación formal de `value` y `per_turn` en `vp_hexes`.
    * `voec_sim/core/reward_calculator.py`: Modulación del potencial radial $\Phi(s)$ PBRS por el valor relativo $v_{\text{rel}} = v_{vp} / 2.0$, otorgando mayor gradiente y bonificación de control a VPs de alto valor táctico.
    * `agents/efficientzero_v2/core/macro_planner.py`: Selección de VPs objetivo ponderada por ratio $\text{score} = v_{\text{rel}} / (1 + d)$.
    * `agents/efficientzero_v2/core/observation.py`: Canales 13, 14 y 18 escalados por $v_{\text{rel}}$.
    * Verificación: 100% de tests unitarios e integración en verde (171/171 tests en `voec_sim/tests/` y `agents/efficientzero_v2/tests/`).

#### v2.5.1 — Fidelidad Canónica a max_turns, Corrección de Presupuesto en Autojuego y Aceleración de Urgencia de VPs `[CONSOLIDADO 🟢]`
* **Objetivo**: Asegurar que las partidas en autojuego y evaluación nunca se corten prematuramente por un tope arbitrario de pasos, garantizando que el motor de simulación corra hasta el `max_turns` canónico del escenario oficial, erradicar penalizaciones espurias de timeout en el asalto final, y acelerar la agresividad hacia VPs.
* **Componentes Consolidados**:
  * **Presupuesto Seguro en Autojuego (`resolve_effective_step_budget` en `selfplay.py`)**:
    * Actualizado a `scenario_turns * max(units * 2, 20)`. Para un escenario de 8 turnos y 14 unidades (Gela), el presupuesto pasa de un rígido 112 pasos a un margen seguro de 224 pasos.
    * Con esto, las partidas de autojuego nunca sufren corte abrupto ni penalización de timeout (`timeout_penalty = -1.0`), finalizando exclusivamente cuando el motor de reglas canónicas emite `done = True` en `turn > max_turns` tras resolver las condiciones de victoria del wargame.
  * **Exposición de Contrato en Adaptador (`EZV2VOECAdapter.scenario_max_turns()`)**:
    * Delegación directa en `self.sim.scenario_max_turns()`, garantizando acceso limpio al límite de turnos sin depender de introspección reflectiva.
  * **Presupuesto Holgado en Benchmarks (`max_steps: 120` / `180`)**:
    * Actualización integral de los ficheros de benchmark curricular (`assault_bench/configs/benchmark_config.curriculum_2scenarios_*.yaml` y `vp_acceleration_phase4.yaml`), permitiendo que escenarios de 8 y 12 turnos concluyan por evaluación reglamentaria de VPs.
  * **Impulso de Urgencia y Potencial de Asalto**:
    * Elevación de `vp_potential_weight: 1.5` y `vp_urgency_lambda: 1.5` en la configuración estándar de EfficientZero V2 y en los currículums de 2 escenarios, incentivando sprint decidido hacia los hexágonos de victoria antes de la expiración del último turno.

#### v2.5.0 (Versión Base Anterior) — Andamiaje de Recompensas por Potencial Radial a VPs, Sesgo MCTS y Factor de Presión Temporal `[CONSOLIDADO 🟢]`
* **Objetivo**: Erradicar el colapso de política por dispersión de recompensas en la captura de banderas, acelerar el gradiente de avance hacia Puntos de Victoria (VPs), podar ramas de deambulación estéril y pasividad en MCTS, e imponer urgencia temporal y penalización acumulativa por inacción en terreno expuesto.
* **Componentes Consolidados**:
  * **Calculador Canónico de Potencial Radial y Presión Temporal (`voec_sim/core/reward_calculator.py`, `agents/efficientzero_v2/core/support.py`)**:
    * Implementación estricta de la función de potencial invariante de Ng, Harada & Russell (ICML 1999) modulada por decaimiento temporal (Devlin & Kudenko 2012): $\Phi(s, t) = \Phi_{\text{dist}}(s) \cdot \exp(-\lambda \cdot \tau) + \Phi_{\text{ctrl}}(s)$, con $\tau = t / T$ y $\lambda = 1.2$.
    * Invariancia PBRS dinámica estricta demostrada y testeada: el decaimiento se congela en $1.0$ si el bando controla al menos un VP ($N_{\text{ctrl}} \ge 1$), preservando la retención defensiva; mientras que ante 0 VPs controlados el valor cae exponencialmente a medida que transcurren los turnos sin objetivos asegurados.
    * Telescopaje exacto verificado: $\sum_{t=0}^{T-1} \gamma^t F(s_t, t, a_t, s_{t+1}, t+1) = -\Phi(s_0, 0)$ con $\Phi(s_T, T) = 0$.
  * **Penalización Acumulativa por Parálisis en Terreno Abierto (`compute_paralysis_penalty`)**:
    * Penalización cuadrático-lineal para unidades en campo abierto (`cover < 0.35`) que no ocupan un VP amigo, no reducen distancia hacia objetivos ni disparan: $P = -w_{\text{pen}} \cdot (1.0 + 0.5 \cdot \min(4, \text{streak} - 1))$.
    * Reset inmediato del streak de inactividad ante cualquier maniobra de avance hacia VPs, asalto o disparo efectivo.
  * **Sesgo de Búsqueda MCTS y Poda de Deambulación Estéril (`agents/efficientzero_v2/core/macro_planner.py`, `mcts.py`)**:
    * En postura `ASSAULT_VP`, inyección directa del gradiente de distancia y canal `vp_contest_race`: las acciones que cierran distancia hacia el VP reciben un multiplicador progresivo $(1.0 + 0.35 \cdot \Delta d)$, y $+15\%$ adicional si la intención neuronal predice asalto.
    * Poda selectiva del $40\%$ en ramas de deambulación estéril: acciones de movimiento que incrementan la distancia al VP sin objetivo de combate sufren penalización de prior ($\times 0.60$).
    * Poda del $50\%$ en pasividad estéril: acciones de `WAIT`/`PASS` bajo postura `ASSAULT_VP` son despriorizadas ($\times 0.50$).
    * Soporte nativo en `run_mcts_puct` mediante `vp_race_prior_biasing`, `vp_race_bonus_by_action`, `sterile_action_mask` y registro forense de `sterile_branches_pruned_count` en `MCTSOutput`.
  * **Expansión Sensorial Hexagonal Nativa y Observabilidad MLOps (`observation.py`, `train_engine.py`, `NetworkTopologyTab.tsx`)**:
    * Modulación del Canal 18 (`vp_distance_field`) con $(1.0 + 0.5 \tau)$ hacia VPs no capturados.
    * Canal 36 nativo: `turn_urgency_pressure` ($\tau = t/T$ amplificado sobre VPs disputados).
    * Canal 37 nativo: `paralysis_exposure_risk` (hexágonos ocupados por unidades aliadas en campo abierto $< 0.35$ lejos de VPs).
    * Catálogo canónico de 38 canales en el visualizador MLOps (puerto 8778).
  * **Trazabilidad Forense en Autojuego (`agents/efficientzero_v2/core/selfplay.py`)**:
    * Integración de `vp_potential_component` y `paralysis_penalty` en el cálculo de recompensas (`reward_shaping.vp_potential_weight`).
    * Registro de métricas canónicas en `sample.info`: `vp_potential_reward_component`, `vp_potential_phi_before`, `vp_potential_phi_after`, `vp_potential_delta`, `turn_urgency_factor`, `paralysis_penalty` y `mcts_sterile_branches_pruned`.
  * **Coordinación de Escuadras para Asalto a VPs (`macro_planner.py`, `close_combat_resolver.py`, `close_combat_context.py`)**:
    * **Base de Fuego (*Base of Fire*)**: Escuadras de apoyo pesado (`ROLE_FIRE_SUPPORT`, ej. MMG `.30cal`, `.50cal`, morteros) que fijan o suprimen defensores en o adyacentes a VPs reciben un boost de prior MCTS de $\times 1.35$.
    * **Elemento de Maniobra y Asalto Coordinado**: Escuadras de asalto (`ROLE_SPEARHEAD` / `ROLE_MANEUVER`) que asaltan a un defensor previamente suprimido por la base de fuego reciben un bonus coordinado de $\times 1.40$ (y $\times 1.20$ con escuadra amiga adyacente de apoyo).
    * **Prohibición de Asalto Frontal Suicida en Solitario**: Asaltos frontales en solitario contra defensores no suprimidos sufren penalización de prior de $-80\%$ ($\times 0.20$) y son clasificados como estériles en `is_sterile_action()`, podándolos en el árbol de búsqueda MCTS PUCT.
    * **Regla Táctica CC-006**: Si una carga frontal en solitario se ejecuta contra un defensor alerta no suprimido, el atacante pierde su dado de combate más débil en Ronda 1 por fuego defensivo (`_apply_cc006_unsuppressed_solo_frontal_penalty`).
  * **Currículum Progresivo Acelerado de Captura de VPs (`curriculums/vp_acceleration/`, `trainer.py`)**:
    * **4 Fases Progresivas con Escenarios Canónicos Dedicados**:
      1. `vp_phase1_unoccupied_3hex.json`: Sprint puro de aproximación y captura de VP no ocupado a 3 hexágonos de distancia, validando el gradiente radial de potencial $\Phi(s)$ e invarianza PBRS.
      2. `vp_phase2_defended_suppressed.json`: Asalto coordinado contra VP defendido por infantería estática en supresión inicial, entrenando la base de fuego (`ROLE_FIRE_SUPPORT` con mortero de 81mm) y la penetración de punta de lanza (`ROLE_SPEARHEAD`).
      3. `vp_phase3_race_2v2.json`: Carrera competitiva simultánea 2 vs 2 unidades hacia VPs neutrales centrales, afianzando la postura `ASSAULT_VP` y el factor de urgencia temporal.
      4. `battaglia_cittadina_2_1.json`: Escenario táctico completo (Gela) con 14 unidades, 5 VPs y fortificaciones urbanas. **Hito de éxito:** Victoria $\ge 75\%$ contra bot heurístico y disputa equilibrada contra humano en $<15$ turnos.
    * **Punto de Entrada Canónico `trainer.py`**: Interfaz de entrenamiento raíz 100% nativa y exclusiva para EfficientZero V2 (cero retrocompatibilidad MuZero), delegando en `agents.efficientzero_v2.train.train_efficientzero_v2`.
    * **Orquestación y Ciclos de Benchmark**: Esquemas `.cycle.json`, configuraciones de benchmark en `assault_bench/configs/` y ejecutor PowerShell automatizado `run_all_phases.ps1`.
  * **Certificación de Pruebas Unitarias y Contratos (319 Tests en Verde)**:
    * `voec_sim/tests/test_reward_calculator.py`: 9 tests verificando potencial de distancia, bonus de control, decaimiento exponencial por urgencia temporal, invarianza telescópica de Devlin & Kudenko, y acumulación/reset de penalización de parálisis.
    * `agents/efficientzero_v2/tests/test_vp_race_mcts_biasing.py`: 2 tests certificando sesgo prior, poda del 40% en MCTS y preservación de visitas.
    * `agents/efficientzero_v2/tests/test_squad_coordination_assault.py`: 5 tests certificando Base of Fire ($\times 1.35$), asalto a defensor suprimido ($\times 1.40$), penalización/poda de asalto en solitario sin supresión, apoyo combinado multi-escuadra y pérdida de dado CC-006.
    * `agents/efficientzero_v2/tests/test_vp_acceleration_curriculum.py`: 4 tests certificando las 4 fases progresivas, carga de escenarios en VOEC, delegación en `trainer.py` y definiciones de ciclos.
    * `agents/efficientzero_v2/tests/test_doctrine_sensory_contract.py`: 6 tests certificando proyección 2D de roles y perfiles tácticos, canales 32 a 35, y canales 36 y 37 de presión temporal y riesgo de parálisis.
    * 319/319 tests globales ejecutados al 100% en verde (128 tests de EfficientZero V2, 88 tests de Assault Model, 31 tests de VOEC Sim y 72 tests de Assault Bench).

#### v2.4.5 — Evaluación y Verificación en Currículum (Fase 5) `[CONSOLIDADO 🟢]`
* **Objetivo**: Desarrollar el Evaluation Harness canónico (`assault_bench/eval.py`), formalizar las métricas de alineación doctrinal por rol (`recon_survival_rate`, `fire_support_stationarity`, `spearhead_vp_capture_rate`, `doctrine_adherence_rate`, `doctrine_mutation_rate`), verificar la paridad táctica frente a baselines heurísticos e integrar los guardrails doctrinales en los currículums de entrenamiento.
* **Componentes Consolidados**:
  * **Harness de Evaluación Canónico (`assault_bench/eval.py`)**: Interfaz CLI y programática para evaluar checkpoints de EfficientZero V2 (`evaluate_checkpoint`), escenarios aislados y fases de currículum (`verify_curriculum_phase_doctrine`), con emisión de reportes forenses estructurados.
  * **Motor de Métricas Doctrinales (`assault_bench/doctrine_metrics.py`)**:
    * `compute_doctrine_role_metrics`: Cálculo exacto de supervivencia de reconocimiento (`recon_survival_rate`), estacionariedad de apoyo de fuego (`fire_support_stationarity`), capturas por punta de lanza (`spearhead_vp_capture_rate`), adherencia a directivas de rol (`doctrine_adherence_rate`) y frecuencia/motivos de mutación (`doctrine_mutation_rate`).
    * `aggregate_doctrine_kpis`: Agregación ponderada y congruente a través de múltiples episodios y semillas sin división por cero.
    * `verify_doctrine_parity`: Verificador formal de paridad y cumplimiento de umbrales doctrinales (`PASS`/`FAIL`).
  * **Integración en Telemetría y Contratos de Benchmark (`assault_bench/`)**: Inyección automática de `doctrine_eval_kpis` en `phase29_metrics.py`, `phase29_contract.py` y `benchmark_finalize.py`, habilitando la trazabilidad de doctrina en DuckDB/Parquet.
  * **Guardrails Doctrinales en Currículum (`curriculums/self_vs_self_vs_random_2scenarios_v1/curriculum.yaml`)**: Incorporación de umbrales doctrinales en los gates de promoción (`min_recon_survival_rate: 0.40`, `min_fire_support_stationarity: 0.45`, `min_doctrine_adherence_rate: 0.35`).
  * **Suite de Pruebas Unitarias e Integración (`assault_bench/tests/test_doctrine_eval.py`)**: 6 nuevos tests dedicados que verifican cálculos, agregaciones, paridad y contratos (228 tests globales al 100% en verde).

#### v2.4.4 — Observabilidad MLOps y Telemetría Forense (Fase 4) `[CONSOLIDADO 🟢]`
* **Objetivo**: Integrar la telemetría forense completa de perfiles doctrinales, mutaciones dinámicas de roles y modulaciones de prior MCTS en el flujo de autojuego, datasets de benchmark y visualizador interactivo MLOps (puerto 8778).
* **Componentes Consolidados**:
  * **Cálculo Analítico de Modulación Prior (`agents/efficientzero_v2/core/macro_planner.py`)**: Función `compute_action_boost` para calcular con exactitud determinista el multiplicador de prior asignado a cada acción según el rol doctrinal activo y la proximidad a Puntos de Victoria.
  * **Inyección en Bucle de Autojuego y Transiciones (`agents/efficientzero_v2/core/selfplay.py`, `timeline_exporter.py`)**: Trazabilidad completa en `sample.info` y en el exportador XAI con `role_assigned`, `role_is_mutated`, `role_mutation_reason`, `prior_boost_applied`, `badge_label` y snapshot integral de escuadras aliadas y enemigas.
  * **Modelos y Pipelines de Benchmark (`assault_bench/`)**: Enriquecimiento de `unit_snapshot_dict`, `StepSignalData`, `episode_runner_impl.py` y `episode_trace_row_builder.py` con campos doctrinales canónicos sin penalización de rendimiento.
  * **Frontend Interactivo MLOps (React + Vite, Puerto 8778)**:
    * Mapeo canónico de los 8 roles tácticos (`SPEARHEAD`, `FIRE_SUPPORT`, `CLOSE_DEFENSE`, `RECON`, `OBJECTIVE_DEFENDER`, `FLANK_SCREEN`, `TACTICAL_RESERVE`, `RECOVER`) con paleta semántica militar.
    * Badges visuales de rol activo, distintivo de mutación contextual (`⚡ MUTADA: REASON`) y píldoras cuantitativas de sesgo prior (`+X% π`) tanto en la tarjeta de escuadra activa como en los rosters de unidades aliadas y del oponente.
    * Nueva tarjeta de auditoría forense doctrinal (*Selected Unit Forensic Doctrine Card*) en el visor de replay.
  * **Suite de Pruebas Unitarias Forenses (`agents/efficientzero_v2/tests/test_doctrine_telemetry_forensics.py`)**: 4 nuevos tests dedicados que certifican la preservación de campos y congruencia de prior boost (222 tests globales al 100% en verde).

#### v2.4.3 — Mutación Dinámica Doctrinal y Modulación Prior MCTS (Fase 3) `[CONSOLIDADO 🟢]`
* **Objetivo**: Implementar la lógica contextual de mutación dinámica de roles en el planificador macro jerárquico (`MacroStrategyPlanner`) y modular los priors raíz del árbol MCTS en un $+35\%$ manteniendo libertad de exploración emergente.
* **Componentes Consolidados**:
  * **Dataclass `MacroPlan` Enriquecido (`agents/efficientzero_v2/core/macro_planner.py`)**: Trazabilidad completa con `unit_mutation_reasons`, `unit_base_roles`, `unit_mutated`, `get_mutation_reason()`, `get_base_role()` y `is_mutated()`.
  * **Reglas Jerárquicas de Mutación Contextual (`compute_macro_plan`)**:
    * **Regla 1 (Presión de Victoria / Turno Tardío)**: Unidades con `allow_spearhead_if_vp_deficit: true` mutan a `ROLE_SPEARHEAD` ante déficit neto de VPs o en el último tercio de partida (`VP_DEFICIT_PRESSURE`).
    * **Regla 2 (Degradación de Moral y Supervivencia)**: Unidades suprimidas, bajo umbral de HP o con $<50\%$ fuera de BUA mutan a `ROLE_RECOVER` (`MORALE_OR_HEALTH_DEGRADATION`).
    * **Regla 3 (Aislamiento / Flanqueo Inmediato)**: Armas de apoyo pesado en rol `FIRE_SUPPORT` con enemigos adyacentes ($\le 1$ hex) y sin escolta cercana mutan a `ROLE_CLOSE_DEFENSE` (`FLANKED_CLOSE_DEFENSE`).
  * **Modulación Prior MCTS (+35% Boost)**:
    * Boost adaptativo en raíz MCTS (+35%) para acciones afines al rol activo (`ROLE_SPEARHEAD`, `ROLE_FIRE_SUPPORT`, `ROLE_CLOSE_DEFENSE`, `ROLE_RECON`, `ROLE_OBJECTIVE_DEFENDER`, `ROLE_FLANK_SCREEN`, `ROLE_TACTICAL_RESERVE`, `ROLE_RECOVER`).
    * Normalización estricta de la distribución de probabilidad a $1.0$.
  * **Suite de Pruebas Unitarias (`agents/efficientzero_v2/tests/test_macro_planner.py`)**: 8 tests en verde verificando las 3 reglas de mutación, preservación de reserva de Dunnigan y normalización de priors (218 tests globales al 100% en verde).

#### v2.4.2 — Expansión Sensorial y Mapeo 2D Doctrinal en `voec_sim` y EZv2 (Fase 2) `[CONSOLIDADO 🟢]`
* **Objetivo**: Integrar los perfiles doctrinales y los rangos óptimos de combate en el plano sensorial continuo de simulación e inferencia, proyectando huellas 2D de efectividad operativa sobre el tensor de observación de EfficientZero V2.
* **Componentes Consolidados**:
  * **Puente Sensorial Autorizado (`voec_sim/core/simulator.py`, `voec_sim/contracts/types.py`)**: `UnitSnapshot` incorpora `doctrine_role` y `doctrine_profile`; `spatial_features()` expone `unit_doctrine_roles` y `unit_optimal_ranges`.
  * **Adaptador de Auto-Juego (`agents/efficientzero_v2/core/adapter_voec.py`)**: Exposición transparente de perfiles y roles activos en `EZV2Observation.units`.
  * **Proyección Espacial 2D y Roles Doctrinales (`agents/efficientzero_v2/core/observation.py`)**:
    * Codificación canónica continua de roles (`DOCTRINE_ROLE_CODES`: `SPEARHEAD` 1.0, `FIRE_SUPPORT` 0.75, `RECON` 0.50, `SCREEN` 0.25, `COMMAND` 0.10).
    * Proyección continua del mapa 2D de alcance óptimo de combate en los canales 24 (`ally_direct_range_norm`) y 25 (`enemy_direct_range_norm`) amortiguado por bloqueo de LOS y cobertura.
    * Activación de sesgo doctrinal de apoyo por fuego en canales 8 y 9 (`ally_heavy_mg_support` / `enemy_heavy_mg_support`).
    * Soporte para tensores extendidos de hasta 36 canales (`ally_doctrine_role`, `enemy_doctrine_role`, `ally_optimal_range_2d`, `enemy_optimal_range_2d`).
  * **Suite de Verificación Dedicada (`agents/efficientzero_v2/tests/test_doctrine_sensory_contract.py`)**: 5 nuevos tests exhaustivos, batería global de 215 tests al 100% en verde.

#### v2.4.1 — Perfilado Doctrinal de Unidades: Catálogo y Contratos Tipados (Fase 1) `[CONSOLIDADO 🟢]`
* **Objetivo**: Dotar a cada una de las 19 unidades del catálogo canónico de un perfil doctrinal (`doctrine_profile`) tipado formalmente, desacoplando capacidades físicas duras de directivas de rol táctico sin colapsar la creatividad de la red.
* **Componentes Consolidados**:
  * **Contrato Tipado `DoctrineProfile` (`assault_model/units/unit_type.py`)**: Dataclass inmutable con validación estricta de `default_role`, `optimal_engagement_range`, `preferred_terrain`, `cohesion_weight`, `fallback_threshold_hp` y reglas de mutación.
  * **Inyección en Catálogo Canónico (`assets/catalogs/unit_catalog.json`)**: Cobertura al 100% de las 19 escuadras y equipos de infantería (Reconocimiento, Armas de Apoyo, Asalto/Punta de Lanza y Pantalla).
  * **Suite de Pruebas Unitarias (`assault_model/tests/test_unit_doctrine_profile.py`)**: 100% de cobertura y validación de serialización roundtrip sin regresiones.

#### v2.4.0 — Gobernanza Zero-Mock, Desacoplamiento y Explicabilidad Causal `[CONSOLIDADO 🟢]`
* **Objetivo**: Erradicar el 100% de inferencias espurias, mocks y números inventados en frontend y reporting; desacoplar métricas base de representaciones visuales; integrar explicabilidad causal (XAI) al perfilado táctico.
* **Componentes Consolidados**:
  * **Purga Integral Zero-Mock / Zero-Inference**: Eliminación de porcentajes ficticios (`NetworkTopologyTab.tsx`), erradicación de turnos y macro-posturas adivinadas (`MatchReplayTab.tsx`), y eliminación de strings fijos de escenarios o facciones (`VpSummaryTab.tsx`, `replay_api.py`). Los componentes muestran estrictamente datos reales o `-`/`N/A`.
  * **Inventario Jerárquico Canónico de Métricas (`docs/13_INVENTARIO_CANONICO_METRICAS.md`)**: Taxonomía en 4 niveles (Motor, MCTS, Red Neuronal, Benchmarks MLOps) con trazabilidad matemática unívoca contra columnas de Apache Parquet y DuckDB.
  * **Marco Canónico de Explicabilidad Causal y Perfilado Táctico (`docs/00_PREMISAS_DEL_PROYECTO.md` §13)**: Directivas de XAI y Causal Profiling para auditar el razonamiento táctico del agente antes de su despliegue competitivo.

---

## 4. Fases Históricas Archivadas (Ciclos v1.0.0 a v2.3.0) (Ciclos v1.0.0 a v2.3.0)

#### v2.3.0 — Innovaciones Tácticas Avanzadas y Transferencia Científica SOTA `[ARCHIVADO 🟢]`
* **Objetivo**: Transferir avances de KataGo y literatura de wargames hexagonales (Palma et al. Feb 2025).
* **Componentes Consolidados**:
  * **Cabeza Densa *Final Territory Ownership Map* ($1\times H\times W$, KataGo — Wu 2020)**: Predicción convolucional del control territorial final del mapa inyectada en `aux["final_ownership_pred"]` en inferencia inicial y recurrente.
  * **Asaltos Combinados Secuenciales (Palma et al. 2025, Sec. 3.3)**: Compromiso coordinado de escuadras adyacentes (`commit_support_unit`) que aportan dados verdes de infantería o rojos de MMG/Mortero en combates cuerpo a cuerpo.
  * **Quality Gates Auto-Calibrados por Escenario con Two-Hot Asimétrico Exponencial**: Boost de resolución exponencial en torno a cero (`sign(x) * |x|^0.75`) para discriminar ventajas tácticas de desgaste y puertas de promoción calibradas a la capacidad de VPs del escenario.

#### v2.2.0 — Engine de Alto Rendimiento y Streaming Binario `[ARCHIVADO 🟢]`
* **Objetivo**: Eliminar cuellos de botella de simulación en CPU y latencia de serialización en el visor web MLOps.
* **Componentes Consolidados**:
  * **Vectorización Ray-Caster y Dijkstra (Sección 6.1)**: Interpolación lineal fraccional vectorizada en NumPy/Numba (`_vectorized_fractional_ray_samples`), matrices tensoriales precalculadas de visibilidad $(N, N)$ y adyacencia $(N, 6)$. Rendimiento medido: **$4{,}924\,\text{steps/s}$** ($>2.4\times$ sobre el objetivo de $2{,}000\,\text{steps/s}$).
  * **Clonado Inmutable Copy-on-Write (CoW, Sección 6.2)**: `CoWHexStateMap` y `GameStateDelta` que comparten `_base` en $O(1)$ con `0` objetos copiados inicialmente al ramificar. Rendimiento medido: **$>109{,}000\,\text{clones/s}$** con aislamiento mutacional del 100%.
  * **Control Territorial Incremental (Sección 6.3)**: Índice espacial invertido recalculando únicamente el radio $R \le 3$ de unidades alteradas ($O(k \cdot R^2)$ amortizado).
  * **Streaming Binario MessagePack (Sección 6.5)**: Codec RFC-8949 binario en WebSocket (`/ws/game?format=msgpack`) y REST. Reducción **$>85\%$** en ancho de banda y latencia **$<5\,\text{ms}$**.

#### v2.1.0 — Búsqueda Eficiente Gumbel / ACT, Compuerta de Canales e Invarianza FCN `[ARCHIVADO 🟢]`
* **Objetivo**: Acelerar drásticamente la generación de autojuego, filtrar planos sensoriales irrelevantes y habilitar despliegue en mapas de tamaño arbitrario.
* **Componentes Consolidados**:
  * **Búsqueda Gumbel MuZero Search** (*Sequential Halving* sin reemplazo) y presupuesto de simulación adaptativo **ACT** (`compute_adaptive_simulations`) en `mcts.py`, guiado por la entropía de Shannon de la política $H(\pi)$ y la dispersión de valores $Q$. Aceleración del autojuego en $\sim 60\%$.
  * **Compuerta Dinámica de Canales (`InputChannelGate`)**: Mecanismo Squeeze-and-Excitation (SE) que analiza los 32 canales axiales de observación y suprime dinámicamente canales muertos según el escenario.
  * **Invarianza Espacial FCN Zero-Shot**: Arquitectura puramente convolucional con `_adapt_spatial` y `AdaptiveAvgPool2d`, desplegable en mapas $16\times 16$, $32\times 32$ y $64\times 64$ sin alterar pesos ni requerir reentrenamiento.
  * **Dinámica Recurrente Weight-Tied**: Dinámica $g_\theta$ iterada $k$ pasos con conexión **Recall** y pérdida de progresión **Progressive Loss** ($\mathcal{L}_{\text{prog}}$) con 0 parámetros extra.

#### v2.0.0 — Comprensión Táctica Multitarea, Balanceo PCGrad y Jerarquía HRL `[ARCHIVADO 🟢]`
* **Objetivo**: Dotar a la red de criterio militar preventivo mediante 10 cabezas auxiliares simultáneas sin interferencia destructiva de gradientes, desacoplando la doctrina macro de la micro-maniobra.
* **Componentes Consolidados**:
  * **10 Cabezas Auxiliares Tácticas**: `threat_map` (2D), `attrition`, `morale`, `objective_intent`, `multi_vp`, `combat_outcome`, `valid_actions_mask`, `action_category`, `final_ownership`, `value_target`.
  * **Balanceador de Gradientes PCGrad** (`loss_balancer.py`): Proyección ortogonal de gradientes opuestos $g_i \leftarrow g_i - \frac{g_i \cdot g_j}{\|g_j\|^2} g_j$ cuando $g_i \cdot g_j < 0$, asegurando convergencia armónica de las 10 cabezas.
  * **MacroStrategyPlanner (HRL Nivel 1)**: Conexión neuronal directa a `objective_intent_logits` y `multi_vp_pred`, emitiendo posturas globales (`ASSAULT_VP`, `DEFENSIVE_HOLD`, `ZONE_SUPPRESS`) y asignando roles doctrinales (`SPEARHEAD`, `FIRE_SUPPORT`, `OBJECTIVE_DEFENDER`, `FLANK_SCREEN`, `TACTICAL_RESERVE`, `RECOVER`) basados en tratados clásicos (Dunnigan, Sun Tzu, Henry Hyde).

#### v1.5.0 — Estabilidad Numérica, Distribución de Valor y Geometría Hexagonal `[ARCHIVADO 🟢]`
* **Objetivo**: Erradicar el colapso de gradiente provocado por la regresión escalar MSE directa en partidas con recompensas dispersas y eliminar sesgos anisotrópicos de la cuadrícula cartesiana.
* **Componentes Consolidados**:
  * **Two-Hot Discreto** ($61$ átomos en $[-30, 30]$) invertible con contracción simétrica logarítmica **Symlog** ($\text{sign}(x)\ln(|x|+1)$) en `agents/efficientzero_v2/core/support.py`.
  * **HL-Gauss** (*Histogram Loss with Gaussian Targets*, DeepMind 2024) que proyecta objetivos continuos mediante discretización suavizada $\mathcal{N}(y, \sigma^2)$ para estabilizar el entrenamiento de valor y recompensas intermedias.
  * `HexagonalMaskConv2d` y `HexagonalDepthwiseSeparableConv2d` en `network_base.py`, anulando sesgos de diagonales irreales en la topología hexagonal.

#### v1.0.0 — Cimentación del Motor VOEC y Reglas Wargame Base `[ARCHIVADO 🟢]`
* **Objetivo**: Implementar el modelo físico y doctrinal del wargame táctico sobre tablero hexagonal.
* **Componentes Consolidados**:
  * Coordenadas axiales $(q, r)$ con transformaciones de distancia y adyacencia en `assault_model/map/hex_utils.py`.
  * Catálogo de unidades y balística de combate con resolución de tiradas de dados multiespectro (Rojo, Azul, Verde, Amarillo) y tiradas de salvación en `assault_model/combat/`.
  * Algoritmo de Línea de Visión (LOS) discreto e interpretación de elevación y cobertura de terreno en `assault_model/combat/line_of_sight.py`.
  * Simulación estocástica y modelo sensorial VOEC en `voec_sim/core/simulator.py`.
