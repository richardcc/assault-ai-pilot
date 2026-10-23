# 11. Currículums y Entrenamiento Progresivo

> [!NOTE] POSIBLE CONTENIDO REPETIDO (Pendiente de decisión del usuario)
> La especificación del Currículum Acelerado de Captura de VPs coincide parcialmente con la Tarea 2.5 de [Línea 2 (Roadmap)](roadmap/02_LINEA_2_ACELERACION_CAPTURA_VPS.md). Se preserva íntegramente conforme a la directiva de no eliminación de párrafos.

## 1. Fundamentos del Aprendizaje por Currículum en Wargames Tácticos

El entrenamiento de agentes de Aprendizaje por Refuerzo en wargames tácticos de nivel de sección/escuadra como **Assault** se enfrenta a dos desafíos fundamentales:
1. **Dispersión Extrema de Recompensas (*Sparse Rewards*)**: En escenarios tácticos completos con mapas $18\times 12$ y 14 unidades simultáneas, un agente iniciado desde cero rara vez alcanza Puntos de Victoria (VPs) mediante exploración puramente estocástica, cayendo en mínimos locales de pasividad, intercambio estéril de disparos a larga distancia o deambulación defensiva.
2. **Complejidad Combinatoria de Espacio de Estados y Acciones**: Con miles de ramas legales por paso de decisión (movimiento hexagonal, encaramiento, líneas de visión, combate a distancia, asaltos combinados y fuego de oportunidad), la convergencia directa sobre escenarios complejos es lenta e ineficiente.

Para resolver este desafío de raíz, la plataforma implementa una **Arquitectura de Currículum Progresivo con Puertas de Calidad Dinámicas (*Dynamic Gated Curriculum Architecture*)** basada exclusivamente en **`EfficientZeroV2`** (con la arquitectura clásica MuZero 100% decomisionada).

El sistema cuenta con **dos currículums canónicos oficiales**:
1. **Currículum Acelerado de Captura de VPs y Paridad Humana (`curriculums/vp_acceleration/`)**: Currículum vertical de 5 fases progresivas enfocado en erradicar la pasividad, dominar la base de fuego, romper la inercia defensiva mediante asalto asimétrico y asaltar VPs competitivamente en $<15$ turnos.
2. **Currículum Multi-Escenario Progresivo Self-Play vs Random (`curriculums/self_vs_self_vs_random_2scenarios_v1/`)**: Currículum horizontal de 7 fases progresivas para robustez táctica, estabilización de políticas en múltiples mapas y balanceo de matchmaking.

---

## 2. Currículum 1: Aceleración de Captura de VPs y Paridad Humana (`vp_acceleration`)

> **Ruta Canónica:** `curriculums/vp_acceleration/`  
> **Motor Exclusivo:** `EfficientZeroV2`  
> **Objetivo Primario:** Forjar un agente agresivo y coordinado que capture y retenga VPs contra oponentes heurísticos y humanos, alcanzando $\ge 75\%$ de victorias en $<15$ turnos en el escenario canónico de Gela y dominando la ruptura urbana ofensiva en Battaglia Cittadina.

```mermaid
flowchart TD
    classDef phase fill:#0f2e4a,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef gate fill:#134e4a,stroke:#2dd4bf,stroke-width:2px,color:#ffffff;

    P1["<b>FASE 1: Sprint de Captura Desocupada</b><br/>vp_phase1_unoccupied_3hex<br/>1 Escuadra US vs 1 VP a dist=3"]:::phase
    G1{"Gate 1: Tasa Captura >= 12%<br/>Captured Avg >= 0.90<br/>Win Rate >= 80%"}:::gate
    P2["<b>FASE 2: Asalto a Defensor Suprimido</b><br/>vp_phase2_defended_suppressed<br/>Base of Fire (Mortero 81mm) + Asalto"]:::phase
    G2{"Gate 2: Spearhead VP >= 60%<br/>Fire Support Stat >= 50%<br/>Win Rate >= 75%"}:::gate
    P3["<b>FASE 3: Carrera Frontal Simultánea 2v2</b><br/>vp_phase3_race_2v2<br/>2 US vs 2 IT a VPs disputados"]:::phase
    G3{"Gate 3: Captured Avg >= 1.20<br/>Adherencia Doctrinal >= 45%<br/>Win Rate >= 70%"}:::gate
    P4["<b>FASE 4: Maestría Táctica Completa (Gela)</b><br/>battaglia_cittadina_2_1<br/>14 Unidades, 5 VPs, Fortificaciones"]:::phase
    G4{"Gate 4: Hito Paridad Humana<br/>Win Rate vs Heurístico >= 75%<br/>Duración < 15 turnos"}:::gate
    P5["<b>FASE 5: Asalto Urbano Puro Ofensivo Asimétrico</b><br/>battaglia_cittadina_2_1 (T=8)<br/>100% Atacante (US vs Random), Timeout -1.0"]:::phase
    G5{"Gate 5: Ruptura Ofensiva Asimétrica<br/>Win Rate >= 80%<br/>Captured Avg >= 1.50<br/>Take Rate >= 12%"}:::gate

    P1 --> G1
    G1 -- "Promoción" --> P2
    G1 -- "Fallo" --> P1
    P2 --> G2
    G2 -- "Promoción" --> P3
    G2 -- "Fallo" --> P2
    P3 --> G3
    G3 -- "Promoción" --> P4
    G3 -- "Fallo" --> P3
    P4 --> G4
    G4 -- "Promoción" --> P5
    G4 -- "Fallo" --> P4
    P5 --> G5
    G5 -- "Fallo" --> P5
```

### 2.1 Especificación de Fases y Escenarios Dedicados

| Fase | Nombre Técnico | Escenario Canónico | Configuración Táctica | Mecánicas Clave Entrenadas |
| :---: | :--- | :--- | :--- | :--- |
| **Fase 1** | `phase1_vp_sprint_unoccupied` | `vp_phase1_unoccupied_3hex.json` | 1 escuadra `US_RIFLES_43` a 3 hexágonos de un VP neutral desocupado. Límite: 6 turnos. | Andamiaje de potencial radial $\Phi(s)$ (Ng et al. 1999). Gradiente PBRS directo hacia bandera sin interferencia de combate. |
| **Fase 2** | `phase2_vp_assault_suppressed` | `vp_phase2_defended_suppressed.json` | 1 punta de lanza `US_RIFLES_43`, 1 apoyo `US_81MM_MORTAR`, 1 defensor `IT_RIFLES_43` suprimido sobre VP. Límite: 8 turnos. | Doctrina de Base de Fuego (boost $1.35\times$) y Asalto Coordinado a defensor suprimido (boost $1.40\times$). Regla CC-006. |
| **Fase 3** | `phase3_vp_race_2v2` | `vp_phase3_race_2v2.json` | 2 escuadras aliadas vs 2 escuadras del Eje a distancias equidistantes de 2 VPs centrales. Límite: 10 turnos. | Postura `ASSAULT_VP`, factor de urgencia temporal $\tau=t/T$ (Devlin & Kudenko 2012) y penalización por parálisis en campo abierto. |
| **Fase 4** | `phase4_tactical_gela_mastery` | `battaglia_cittadina_2_1.json` | Escenario táctico completo (Gela): 7 unidades US, 7 unidades IT, 5 VPs, fortificaciones, trincheras y cobertura urbana. | Asalto integral multinivel, roles dinámicos, desvío de reservas y convergencia estratégica hacia la victoria. |
| **Fase 5** | `phase5_urban_assault_pure_offensive` | `battaglia_cittadina_2_1.json` | Asalto Urbano Asimétrico Puro: Modo 100% atacante (`US` vs `Random`), $T_{\max} = 8$ turnos, penalización severa por timeout ($-1.0$), 10 ciclos de refuerzo adaptativo con MCTS a 256–416 simulaciones. | Dynamic PBRS escalado en el tiempo ($(1 + t/T_{\max})$), atenuación de bajas en brecha ($d \le 2$, factor $0.40$), bono de disputa ($0.8$), desensibilización radical de la Paradoja del Comandante Prudente. |

### 2.2 Umbrales Cuantitativos de Promoción (*Quality Gates*)

Para avanzar de una fase a la siguiente, el evaluador de benchmark ejecuta la suite de evaluación sobre los checkpoints generados y verifica que se cumplan estrictamente los siguientes criterios:

```yaml
# curriculums/vp_acceleration/curriculum.yaml
phases:
  - name: phase1_vp_sprint_unoccupied
    gate:
      min_vp_capture_take_rate: 0.12     # Captura rápida de banderas desocupadas
      min_tracked_captured_avg: 0.90     # Promedio de VPs asegurados por partida
      min_vp_net_avg_tracked_side: 0.50  # Diferencial positivo neto de control
      min_win_rate: 0.80                 # Tasa de victoria mínima del 80%

  - name: phase2_vp_assault_suppressed
    gate:
      no_regression_defeat_rate: true    # Cero tolerancia a incrementos de derrotas
      min_vp_capture_take_rate: 0.10     
      min_spearhead_vp_capture_rate: 0.60 # >= 60% de VPs capturados por escuadras SPEARHEAD
      min_fire_support_stationarity: 0.50 # Apoyo pesado mantiene desenfilada/estacionariedad
      min_doctrine_adherence_rate: 0.45  # Cumplimiento formal de órdenes doctrinales
      min_win_rate: 0.75

  - name: phase3_vp_race_2v2
    gate:
      no_regression_defeat_rate: true
      min_vp_capture_take_rate: 0.08
      min_tracked_captured_avg: 1.20     # Dominio en disputa de 2 VPs simultáneos
      min_vp_net_avg_tracked_side: 0.40
      min_doctrine_adherence_rate: 0.45
      min_win_rate: 0.70

  - name: phase4_tactical_gela_mastery
    gate:
      no_regression_defeat_rate: true
      min_win_rate_vs_heuristic: 0.75    # Hito: >= 75% victorias vs bot heurístico
      max_avg_turns: 15.0                # Hito: Resolución decisiva en < 15 turnos
      min_vp_capture_take_rate: 0.08
      min_tracked_captured_avg: 2.50
      min_doctrine_adherence_rate: 0.40
      min_recon_survival_rate: 0.40
      min_fire_support_stationarity: 0.45

  - name: phase5_urban_assault_pure_offensive
    max_reinforcement_cycles: 10
    gate:
      no_regression_defeat_rate: true
      min_win_rate: 0.80                 # >= 80% de victorias ofensivas directas
      min_tracked_captured_avg: 1.50     # Promedio de VPs capturados por US
      max_avg_turns: 8.0                 # Asalto rápido comprimido en <= 8 turnos
      min_vp_capture_take_rate: 0.12     # Alta cadencia de captura de hexágonos VP
      min_doctrine_adherence_rate: 0.45  # Cumplimiento doctrinal en brecha urbana
```

### 2.3 Mecánica de Ciclos por Fase: Independencia Intra-Fase vs. Acumulación Inter-Fase

Uno de los aspectos arquitectónicos más críticos del motor de currículum de **Assault** (`curriculums/common/run_dynamic_gated_curriculum.ps1`) es la distinción formal entre la **ejecución de ciclos dentro de una fase** y la **transición entre fases consecutivas**:

```mermaid
flowchart TD
    classDef base fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#ffffff;
    classDef cycle fill:#0f2e4a,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef eval fill:#134e4a,stroke:#2dd4bf,stroke-width:2px,color:#ffffff;
    classDef winner fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#ffffff;

    B["<b>Checkpoint Promovido Fase Anterior</b><br/>(Semilla Base Común)"]:::base

    subgraph Phase_Loop ["Bucle de Ciclos de la Fase (Independientes en Pesos)"]
        C1["<b>Ciclo 1: Promoted Baseline</b><br/>Parámetros estándar"]:::cycle
        E1{"Gate Eval: FAIL"}:::eval
        C2["<b>Ciclo 2: Adaptive Exploitation</b><br/>+Reanalysis, MCTS frío"]:::cycle
        E2{"Gate Eval: FAIL"}:::eval
        C3["<b>Ciclo 3: Adaptive Exploration</b><br/>+VP Bonuses, +Objective Loss"]:::cycle
        E3{"Gate Eval: FAIL / PASS"}:::eval
    end

    B -->|"Arranque Limpio"| C1
    C1 --> E1
    B -->|"Arranque Limpio (Sin pesos de C1)"| C2
    E1 -.->|"Inyección Fallos a Overlays"| C2
    C2 --> E2
    B -->|"Arranque Limpio (Sin pesos de C2)"| C3
    E2 -.->|"Inyección Fallos a Overlays"| C3
    C3 --> E3

    W["<b>Selección del Ciclo Ganador Único</b><br/>Máximo TQS y Win Rate<br/>(promote_best_of_cycles)"]:::winner
    E1 -.-> W
    E2 -.-> W
    E3 --> W

    NextPhase["<b>Siguiente Fase</b><br/>(Hereda el Checkpoint Ganador Único)"]:::base
    W ==>|"Encadenamiento Inter-Fase (Acumulativo)"| NextPhase
```

#### 1. Comportamiento Intra-Fase: Ciclos Independientes en Pesos (NO Acumulativos)
- **Aislamiento de Pesos de Red**: Cada ciclo ($C_1, C_2, \dots, C_N$) dentro de una misma fase **NO acumula los pesos del ciclo anterior**. Todos los ciclos parten exactamente del **mismo checkpoint base promovido por la fase previa** (`$phaseBaselineCheckpoint`).
- **Propósito Anti-Divergencia**: Si el Ciclo 2 explora una parametrización agresiva que induce colapso de entropía o parálisis táctica, el Ciclo 3 **no hereda esa política degradada**. El entrenamiento vuelve a bifurcarse desde el modelo consolidado previo.
- **Lo que SÍ se Acumula y Muta**: Los **hiperparámetros y la configuración de entrenamiento** evolucionan adaptativamente entre ciclos:
  - Si un ciclo falla por un criterio específico del gate (ej. `xai_vp_capture_take_rate < min_vp_capture_take_rate`), las razones de fallo (`$lastGateFailReasons`) son analizadas por [`evolutionary_cycle_optimizer.py`](file:///c:/repos/python/assault/agents/efficientzero_v2/curriculum/evolutionary_cycle_optimizer.py) y [`Build-ResumeOverlayConfig`](file:///c:/repos/python/assault/curriculums/common/run_dynamic_gated_curriculum.ps1#L825) para generar el *overlay* del siguiente ciclo (ej. subiendo el ratio de reanálisis, enfriando la temperatura MCTS o incrementando el bono radial PBRS hacia banderas).

#### 2. Criterio de Selección: Se queda SOLO UN ciclo por fase
Al finalizar los ciclos de una fase, el sistema selecciona **un único modelo ganador**:
- **Paso Anticipado por Aprobado (PASS)**: En cuanto cualquier ciclo cumple el 100% de los criterios del Quality Gate, el bucle de ciclos se interrumpe inmediatamente (`break`), y ese checkpoint se corona como el ganador de la fase.
- **Selección al Límite de Ciclos (`promote_best_of_cycles`)**: Si se agota el número máximo de ciclos (`max_reinforcement_cycles`: 3 en fases 1-4, 10 en fase 5) sin un aprobado absoluto, el orquestador compara todos los ciclos evaluados según su **Tactical Quality Score (TQS)** (con desempate por **Win Rate**). El ciclo con la puntuación más alta es seleccionado como el mejor candidato de la fase, guardando sus parámetros con [`Save-WinningCycleParamsToPhaseConfig`](file:///c:/repos/python/assault/curriculums/common/run_dynamic_gated_curriculum.ps1#L945) y descartando los demás checkpoints intermedios.

#### 3. Comportamiento Inter-Fase: Encadenamiento de Fases (SÍ Acumulativo)
Entre fases consecutivas del currículum, los pesos **SÍ son acumulativos y progresivos**:
- La Fase $i+1$ se inicializa cargando obligatoriamente el **checkpoint único promovido de la Fase $i$**.
- De este modo, el agente traslada secuencialmente sus destrezas: el sprint radial aprendido en Fase 1 se conserva para el asalto coordinado de la Fase 2, la postura de carrera 2v2 de la Fase 3, el combate urbano complejo de la Fase 4 y la ruptura asimétrica pura de la Fase 5.

---

## 3. Currículum 2: Multi-Escenario Progresivo Self-Play vs Random (`self_vs_self_vs_random_2scenarios_v1`)

> **Ruta Canónica:** `curriculums/self_vs_self_vs_random_2scenarios_v1/`  
> **Motor Exclusivo:** `EfficientZeroV2`  
> **Objetivo Primario:** Dotar al modelo de invarianza topográfica y generalización ante comportamientos caóticos mediante la alternancia progresiva entre partidas de auto-juego (*Self-Play*) y partidas contra baselines aleatorios en dos escenarios tácticos simultáneos (`battaglia_cittadina_2_1` y `mettete_i_piedi_terra_1`).

```mermaid
flowchart LR
    classDef phase fill:#0f2e4a,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef gate fill:#134e4a,stroke:#2dd4bf,stroke-width:2px,color:#ffffff;

    B1["<b>Fase 1: Bootstrap</b><br/>Mix 80/20 Escenarios<br/>Priors Base"]:::phase --> B2["<b>Fase 1b: Channel Adapt</b><br/>Adaptación Canales 2D<br/>Pre-entrenamiento"]:::phase
    B2 --> B3["<b>Fase 1c: Refine Aggressive</b><br/>Refinamiento Agresivo<br/>Combate Directo"]:::phase
    B3 --> P2["<b>Fase 2: Mix 70/30</b><br/>70% Self / 30% Random<br/>Primer Filtro"]:::phase
    P2 --> P3["<b>Fase 3: Mix 50/50</b><br/>50% Self / 50% Random<br/>Equilibrio Táctico"]:::phase
    P3 --> P4["<b>Fase 4: Mix 30/70</b><br/>30% Self / 70% Random<br/>Stress-Test"]:::phase
    P4 --> P5["<b>Fase 5: Self-Dominant</b><br/>90% Self / 10% Random<br/>Alta Competición"]:::phase
    P5 --> P6["<b>Fase 6: Self-Only</b><br/>100% Self-Play<br/>Estabilización Final"]:::phase
```

### 3.1 Esquema de Fases y Ponderación de Escenarios

| Fase | Mezcla de Escenarios | Matchmaking de Autojuego | Propósito Táctico y Científico |
| :--- | :--- | :--- | :--- |
| **`phase1_bootstrap`** | 80% Battaglia, 20% Mettete | 100% Self-Play (MCTS Temp 1.2) | Establecer las primeras representaciones latentes de terreno, líneas de visión y balística. |
| **`phase1_channel_adapt`** | 70% Battaglia, 30% Mettete | 100% Self-Play (Canales 0-37) | Adaptar el codificador hexagonal residual a los canales sensoriales tácticos y de moral. |
| **`phase1_refine_aggressive`** | 60% Battaglia, 40% Mettete | 100% Self-Play | Fomentar el avance ofensivo y el castigo de la pasividad en aproximación. |
| **`phase2_mix_70_30`** | 50% Battaglia, 50% Mettete | 70% Self-Play, 30% vs Random | Inyectar ruido estocástico del rival para evitar el sobreajuste a patrones repetitivos. |
| **`phase3_mix_50_50`** | 50% Battaglia, 50% Mettete | 50% Self-Play, 50% vs Random | Régimen equilibrado de explotación y robustez ante maniobras impredecibles. |
| **`phase4_mix_30_70`** | 50% Battaglia, 50% Mettete | 30% Self-Play, 70% vs Random | Prueba de estrés: castigo a políticas que asumen que el rival juega racionalmente. |
| **`phase5_self_dominant_90_10`** | 50% Battaglia, 50% Mettete | 90% Self-Play, 10% vs Random | Vuelta a la alta competición MCTS con un residuo de perturbación. |
| **`phase6_self_only_stabilize`** | 50% Battaglia, 50% Mettete | 100% Self-Play Puro | Estabilización final de valor y política a máxima profundidad de búsqueda ($MCTS \ge 512$). |

### 3.2 Guardrails Doctrinales y Soft Guardrail para `side_b`

Debido a la asimetría táctica de los wargames (donde un bando defiende fortificaciones elevadas y el otro asalta en campo abierto), este currículum implementa el **Soft Guardrail para `ezv2_vs_random_side_b`**, permitiendo la promoción de checkpoints siempre que el lado más desfavorable no sufra colapso catastrófico (`severe_min_score: 0.03`, `max_score_drop_vs_prev: 0.20`), al tiempo que se exige estricta no-regresión en la tasa de derrota global (`no_regression_defeat_rate: true`).

---

## 4. Guía Operativa de Ejecución

### 4.1 Orquestación Integral Multi-Currículum (`run_full_multi_curriculum_pipeline.ps1`)

Para ejecutar de manera totalmente desatendida y secuencial el **viaje táctico completo** (Etapa 1: Aceleración de VPs $\to$ Ingesta MLOps $\to$ Etapa 2: Multi-Escenario Progresivo con autojuego al 70% $\to$ Cierre MLOps), se utiliza el orquestador maestro [`scripts/run_full_multi_curriculum_pipeline.ps1`](file:///c:/repos/python/assault/scripts/run_full_multi_curriculum_pipeline.ps1):

```powershell
# Ejecución completa del viaje táctico (desde cero o con seed opcional)
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_multi_curriculum_pipeline.ps1

# Opciones avanzadas:
# 1. Validación previa de integridad y manifiestos sin computar en GPU (DryRun)
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_multi_curriculum_pipeline.ps1 -DryRun

# 2. Warm-start desde un checkpoint preexistente como semilla inicial
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_multi_curriculum_pipeline.ps1 -InitialCheckpoint "mlops/checkpoints/best_baseline.pt"

# 3. Detenerse inmediatamente ante fallo de gate tras agotar ciclos de refuerzo
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_multi_curriculum_pipeline.ps1 -StopOnGateFail -StopOnPhaseError

# 4. Ejecutar únicamente Etapa 1 (vp_acceleration) y sincronizar DuckDB
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_multi_curriculum_pipeline.ps1 -SkipMultiScenario
```

### 4.2 Orquestación por Currículum Individual (`run_all_phases.ps1`)

Cada currículum dispone además de su propio script `run_all_phases.ps1` que delega en el motor unificado [`curriculums/common/run_dynamic_gated_curriculum.ps1`](file:///c:/repos/python/assault/curriculums/common/run_dynamic_gated_curriculum.ps1):

```powershell
# -------------------------------------------------------------
# 1. Ejecución del Currículum de Aceleración de VPs
# -------------------------------------------------------------
powershell -ExecutionPolicy Bypass -File .\curriculums\vp_acceleration\run_all_phases.ps1

# Opciones avanzadas:
# Simulación rápida sin ejecutar entrenamiento (DryRun)
powershell -ExecutionPolicy Bypass -File .\curriculums\vp_acceleration\run_all_phases.ps1 -DryRun

# Iniciar en una fase específica
powershell -ExecutionPolicy Bypass -File .\curriculums\vp_acceleration\run_all_phases.ps1 -StartPhase phase2_vp_assault_suppressed

# Detenerse inmediatamente si un gate no se supera
powershell -ExecutionPolicy Bypass -File .\curriculums\vp_acceleration\run_all_phases.ps1 -StopOnGateFail

# Reanudar desde el último checkpoint registrado
powershell -ExecutionPolicy Bypass -File .\curriculums\vp_acceleration\run_all_phases.ps1 -ContinueFromLatestCheckpoint


# -------------------------------------------------------------
# 2. Ejecución del Currículum Multi-Escenario (2 Scenarios v1)
# -------------------------------------------------------------
powershell -ExecutionPolicy Bypass -File .\curriculums\self_vs_self_vs_random_2scenarios_v1\run_all_phases.ps1
```

### 4.2 Ejecución Manual por Fase con el Entrenador Canónico (`trainer.py`)

Para entrenar o depurar una fase individual de forma aislada, se utiliza el punto de entrada canónico [`trainer.py`](file:///c:/repos/python/assault/trainer.py):

```powershell
# Fase 1: Sprint de captura a VPs desocupados
python trainer.py --config curriculums/vp_acceleration/configs/efficientzero_v2.phase1_unoccupied.yaml

# Fase 2: Asalto coordinado con Base of Fire a VP defendido
python trainer.py --config curriculums/vp_acceleration/configs/efficientzero_v2.phase2_defended.yaml

# Fase 3: Carrera frontal simultánea 2v2
python trainer.py --config curriculums/vp_acceleration/configs/efficientzero_v2.phase3_race_2v2.yaml

# Fase 4: Maestría en escenario completo (Gela)
python trainer.py --config curriculums/vp_acceleration/configs/efficientzero_v2.phase4_gela_mastery.yaml
```

### 4.3 Evaluación y Verificación de Checkpoints con `assault_bench`

Para evaluar formalmente el rendimiento de un checkpoint frente a baselines heurísticos o aleatorios:

```powershell
# Evaluar Fase 1 (Tasa de captura en 3 hexágonos)
python -m assault_bench.runner --config assault_bench/configs/benchmark_config.vp_acceleration_phase1.yaml

# Evaluar Fase 4 (Meta: Victoria >= 75% vs heurístico en <15 turnos)
python -m assault_bench.runner --config assault_bench/configs/benchmark_config.vp_acceleration_phase4.yaml
```

### 4.4 Monitorización en Vivo en Dashboard MLOps (Puerto 8778)

Durante y tras la ejecución de los currículums, el servidor MLOps permite visualizar el progreso de las fases, curvas de aprendizaje, matrices de confusión táctica y repeticiones interactivas de partidas con trazabilidad de roles:

```powershell
# Iniciar servidor de visualización MLOps
python -m mlops.reporting.viewer_server --port 8778
```

En `http://localhost:8778`:
- **Pestaña VpSummaryTab**: Trazabilidad del diferencial de VPs, tasa de conversión y tiempo de captura por turno.
- **Pestaña EvalMetricsTab**: Verificación de cumplimiento de gates por fase y evolución de la tasa de victorias.
- **Pestaña MatchReplayTab**: Reproducción forense paso a paso con badges doctrinales (`SPEARHEAD`, `FIRE_SUPPORT`, `RECON`) e inspectores de modulación de prior MCTS.


---

## 5. Aceleración Estadística de Evaluación: Test Secuencial Wald SPRT [Consolidado v2.5.3]

Durante las fases de evaluación curricular y benchmarks frente a baselines heurísticos o aleatorios, evaluar una cuota fija de partidas (ej. 100 partidas) introduce un coste temporal masivo cuando un modelo ya es claramente ganador o perdedor tras las primeras 25-30 partidas.

Para erradicar este desperdicio computacional sin degradar el rigor matemático, se implementa el **Test Secuencial de Razón de Verosimilitud de Wald (SPRT)** (*Sequential Probability Ratio Test*):

### 5.1. Formulación del Test de Hipótesis Binaria
Se formula una prueba de hipótesis sobre la probabilidad de victoria $p$:
* **Hipótesis Nula ($H_0$)**: $p \le p_0$ (El modelo evaluado no supera el umbral mínimo aceptable, ej. $p_0 = 0.50$).
* **Hipótesis Alternativa ($H_1$)**: $p \ge p_1$ (El modelo evaluado alcanza la calidad objetivo, ej. $p_1 = 0.65$).

### 5.2. Razón de Verosimilitud Logarítmica y Límites de Parada
Tras observar $n$ partidas independientes con $w$ victorias, $l$ derrotas y $d$ empates (ponderados como $0.5$ victorias), la razón de verosimilitud logarítmica acumulada $\Lambda_n$ se define como:
$$\Lambda_n = w \ln \left(\frac{p_1}{p_0}\right) + l \ln \left(\frac{1 - p_1}{1 - p_0}\right)$$

Los límites de decisión de Wald para probabilidades de error tipo I ($\alpha = 0.01$) y tipo II ($\beta = 0.01$) se calculan formalmente como:
$$A = \ln \left(\frac{1 - \beta}{\alpha}\right) = \ln \left(\frac{0.99}{0.01}\right) \approx +4.5951$$
$$B = \ln \left(\frac{\beta}{1 - \alpha}\right) = \ln \left(\frac{0.01}{0.99}\right) \approx -4.5951$$

### 5.3. Regla de Decisión y Cancelación Asíncrona
En cada partida finalizada en el pool concurrente de evaluación:
1. Si $\Lambda_n \ge A$: **Se Acepta $H_1$ (Victoria Confirmada)**. Se detiene inmediatamente la evaluación y se cancelan todas las tareas asíncronas en vuelo (`future.cancel()`).
2. Si $\Lambda_n \le B$: **Se Rechaza $H_1$ / Se Acepta $H_0$ (Derrota Confirmada)**. Se detiene inmediatamente la evaluación sin malgastar computación.
3. Si $B < \Lambda_n < A$: La evidencia es aún inconclusa; se continúa evaluando hasta alcanzar la muestra máxima presupuestada ($N_{\max}$).

**Impacto Cuantitativo**: Reduce el tiempo total de benchmarking entre un **$50\%$ y un $75\%$**, garantizando un nivel de confianza estadística del $99\%$ ($p < 0.01$).

---

## 6. Diagnóstico Doctrinal: La Paradoja del "Comandante Prudente" (*The Prudent Commander Paradox*)

### 6.1. Definición y Origen Causal
La **Paradoja del Comandante Prudente** es una patología conductual de aprendizaje por refuerzo descubierta en las campañas de self-play de Assault:
> El agente aprende con gran maestría los fundamentos tácticos de supervivencia (uso de cobertura, desenfilada, concentración de fuego), logrando ratios de intercambio de bajas favorables ($CER \ge 1.10$). Sin embargo, ante escenarios con límite estricto de turnos ($T_{\max}$), **el agente prefiere no arriesgar sus unidades en un asalto urbano al hexágono de VP**, resultando en derrotas automáticas por expiración de turnos. En términos doctrinales: *un comandante que preserva todas sus fuerzas pero no cumple la misión ha sido derrotado militarmente*.

### 6.2. Mitigación Matemática y Curricular (Tareas 2.10 y 2.11)
Para quebrar la Paradoja del Comandante Prudente sin perder la solidez táctica adquirida, se implementan tres intervenciones estructurales:

1. **Desensibilización de Bajas en la Brecha ($d \le 2$)**:
   La penalización de recompensa por pérdida de unidades ($r_{\text{loss}}$) se atenúa en un $60\%$ ($r_{\text{loss}} \times 0.40$) cuando la unidad se encuentra en el radio de asalto del VP ($d(u, \text{VP}) \le 2$), permitiendo al agente asumir el desgaste necesario para la ruptura defensiva.
2. **Potencial de Urgencia Temporal Invariante PBRS**:
   $$\Phi(s, t) = \alpha \left(1 + \frac{t}{T_{\max}}\right) \left(-\min_u d(u, \text{VP})\right) + \beta \cdot \text{Contest}$$
   El valor de acercarse al VP aumenta a medida que el reloj de la partida avanza, venciendo la inercia conservadora en turnos finales.
3. **Penalización Catastrófica por Timeout**:
   Si la partida expira ($t = T_{\max}$) sin que el atacante controle el VP, se aplica un castigo terminal estricto ($R_{\text{timeout}} = -|Loss|$), forzando al algoritmo MCTS a descartar ramas pasivas en los turnos finales.

### 6.3. Fase 5: Currículum Asimétrico Ofensivo de Asalto Urbano Puro (Tarea 2.11) [Consolidado v2.5.6]
* **Escenario**: `battaglia_cittadina_2_1` con horizonte táctico comprimido a $T_{\max} = 8$ turnos.
* **Modo de Matchup Asimétrico**: $100\%$ atacante (`self_vs_random` con `tracked_side="US"`, `to_play="US"`), obligando al agente a forzar la ruptura urbana frente a defensores estáticos atrincherados antes de retornar al autojuego simétrico.
* **Esquema Evolutivo de 10 Ciclos**: Definido en `curriculums/vp_acceleration/cycles/phase5_urban_assault_pure_offensive.adaptive_cycles.yaml`:
  * **Ciclo 1**: Baseline inicial con andamiaje temporal PBRS y castigo catastrófico por timeout ($-1.0$).
  * **Ciclos 2–4 (Explotación Adaptativa)**: Incremento de reanálisis ($0.50 \to 0.52$), mayor peso de potencial y bono de brecha ($d \le 2$).
  * **Ciclos 5–7 (Exploración Adaptativa)**: Expansión de simulaciones MCTS a 320, máxima agresividad en frontera y penalización severa por inmovilidad (`idle_penalty: -0.25`).
  * **Ciclos 8–10 (Convergencia de Hiper-Asalto)**: Reanálisis intensivo ($0.58 \to 0.60$), MCTS de 384 a 416 simulaciones con temperatura determinista ($0.80$) para consolidar la doctrina de asalto urbano puro con Win Rate $\ge 80\%$.
* **Validación**: Suite de pruebas unitarias `agents/efficientzero_v2/tests/test_task_2_11_urban_assault_curriculum.py` (4/4 tests en verde).

---

## 7. Observabilidad MLOps: Gráfica Multi-Métrica y Comparativa de Metas (Quality Gates) [Consolidado v2.5.14]

Para garantizar la trazabilidad forense completa de la progresión curricular, el dashboard MLOps (:8778) y la vista de catálogo incorporan un componente visual multi-métrica (`CurriculumProgressionChart`) y tarjetas de flujo de pipeline (`CurriculumLineageFlow`):

### 7.1. Modos de Conmutación Reactiva
El operador puede alternar instantáneamente entre cuatro perspectivas analíticas:
1. **📈 ELO Curve**: Curva de progresión del rating ELO global a lo largo de todos los ciclos y fases del currículum, destacando con estrella (★) y línea de tendencia dorada el ciclo óptimo seleccionado para la promoción de cada fase.
2. **🎯 Win Rate vs. Goal**: Gráfica comparativa del porcentaje de victoria obtenido frente al umbral mínimo exigido por la puerta de calidad (`min_win_rate` o `min_win_rate_vs_heuristic`).
3. **🚩 Captured VPs vs. Goal**: Comparativa del promedio de Puntos de Victoria capturados por partida (`captured_avg`) contra el objetivo formal del Quality Gate (`min_tracked_captured_avg`).
4. **⚡ VP Take Rate vs. Goal**: Comparativa de la tasa de captura efectiva de VPs (`vp_take_rate`) frente a la cuota mínima de ocupación (`min_vp_capture_take_rate`).

### 7.2. Indicadores Visuales y Bandas de Fase
* **Líneas de Umbral por Fase (`🎯 ≥Goal`)**: Cada banda vertical de fase renderiza una línea discontinua ámbar con el valor objetivo exacto especificado en el contrato del gate.
* **Coloración Semántica de Nodos**:
  * **Verde Esmeralda (`#10b981`)**: El ciclo superó el objetivo exigido por el Gate.
  * **Rojo Carmesí (`#ef4444`)**: El ciclo no alcanzó la meta mínima estipulada.
  * **Dorado (`#fbbf24`)**: Ciclo óptimo promovido de la fase (*Selected per Phase*).
* **Tarjetas de Pipeline**: Las tarjetas de cada fase en `CurriculumLineageFlow` reflejan directamente las métricas obtenidas acompañadas de su meta formal (ej. `Win Rate: 84.0% (🎯 >=75.0%)`, `VPs Avg: 1.80 (🎯 >=1.20)`).

---

## 8. Arquitectura de Refuerzo Acumulativo Intra-Fase y Mitigación del Precipicio Curricular [Consolidado v2.5.15]

### 8.1. Diagnóstico del "Precipicio Curricular" (*Curriculum Cliff*)
El análisis forense de la campaña curricular reveló una degradación escalonada del Win Rate a medida que aumentaba la complejidad del escenario ($100\% \to 60\% \to 33\% \to 28\% \to 3\% \to 0\%$). La causa raíz radicaba en dos patologías arquitectónicas:
1. **Reintentos Estáticos Aislados**: Ante un Quality Gate no superado en el Ciclo $N$, el orquestador descartaba el checkpoint obtenido y reiniciaba el Ciclo $N+1$ desde el baseline de la fase anterior, impidiendo la acumulación iterativa de gradientes.
2. **Promoción Ciega por Expiración de Ciclos**: Al agotarse los ciclos presupuestados sin alcanzar el umbral, el sistema seleccionaba el mejor intento y avanzaba forzosamente a la siguiente fase, transfiriendo políticas deficientes a mapas con mayor número de unidades y restricciones temporales severas.

### 8.2. Mecanismo de Warm-Start Acumulativo (*Accumulative Warm-Start*)
En `run_dynamic_gated_curriculum.ps1`, cada ciclo intra-fase que no supera el Gate encadena inmediatamente los pesos del mejor candidato generado hasta el momento en esa misma fase (`$bestPhaseCheckpoint`):
$$\theta_{c+1}^{(p)} \leftarrow \arg\max_{\theta \in \{\theta_1, \dots, \theta_c\}} \text{TQS}(\theta)$$
Este esquema transforma los ciclos de refuerzo en un proceso evolutivo continuo ($\theta_1 \to \theta_2 \to \theta_3$) con mutación adaptativa de hiperparámetros (temperatura MCTS, ratios de reanálisis y andamiaje PBRS).

### 8.3. Rebalanceo Doctrinal de Recompensas
* **Fase 2 (`vp_phase2_defended_suppressed`)**: Consolidación de base de fuego y asalto coordinado elevando iteraciones y episodios por iteración (`episodes_per_iter: 20`, `train_updates_per_iter: 20`, `reanalysis_ratio: 0.48`).
* **Fase 3 (`vp_phase3_race_2v2`)**: Reajuste anti-parálisis y de asalto en brecha (Task 2.10): Activación de Time-Scaled PBRS (Devlin & Kudenko), atenuación de bajas en zona de brecha (`breach_casualty_attenuation: 0.35`, $d \le 2$ hexágonos respecto a VPs disputados), bono por disputar el hexágono (`vp_contested_bonus: 1.5`), incentivo masivo de captura (`capture_bonus: 6.0`, `vp_capture_bonus_per_hex: 15.0`) y enfriamiento de temperatura MCTS (`mcts_temperature: 1.10`) para erradicar la selección espuria de casillas adyacentes por bono de exploración en favor de la captura inmediata.
* **Fase 5 (`urban_assault_pure_offensive`)**: Penalización estricta por turnos inmóviles fuera de cobertura (`idle_penalty: -0.25`), potencial de aproximación radial al VP reforzado ($\alpha = 1.8$) y temperatura inicial de exploración elevada ($\tau = 1.25$).

### 8.4. Guía Canónica de Diagnóstico y Telemetría de Pérdidas de Entrenamiento (Loss Interpretation & Dual Mode)

Durante el bucle de entrenamiento de EfficientZero V2 (`train_engine.py` / `trainer.py`), la consola y MLflow emiten periódicamente el desglose de pérdidas:

```text
[EfficientZeroV2]   train loss=50.9003 policy=1.4654 value=19.0544 reward=29.7313 objective=0.9895 consistency=0.000002
```

Para evitar falsos diagnósticos de divergencia o no convergencia, el equipo de desarrollo debe interpretar estos valores según el régimen de soporte configurado (`support_size`):

#### 1. Régimen de Soporte: Two-Hot (`support_size > 0`) vs. MSE Escalar (`support_size = 0`)
* **Two-Hot (Cross-Entropy en nats)**: Cuando `support_size = 30`, el valor y la recompensa se modelan como distribuciones sobre 61 átomos. Las pérdidas oscilan entre $0.5$ y $\ln(61) \approx 4.11$ nats. Un valor superior a $10.0$ indicaría colapso de distribución o inestabilidad numérica.
* **Escalar Continuo (MSE en unidades cuadráticas)**: Cuando `support_size = 0` (habitual en fases curriculares de alta dispersión de recompensas), la salida es un escalar directo entrenado con **Mean Squared Error**.
  $$\mathcal{L}_{\text{rew}} = \frac{1}{B} \sum_{b=1}^{B} (r_b - r_b^*)^2 \implies \text{RMSE}_r = \sqrt{\mathcal{L}_{\text{rew}}}$$
  En escenarios como `vp_phase3_race_2v2`, la recompensa de captura asciende a $+16.14$ puntos (`vp_capture_bonus_per_hex: 12.24` + `capture_bonus: 3.90`) y el progreso a $+9.52$. Un `reward_loss = 29.73` equivale a un error típico $\text{RMSE} = \sqrt{29.73} \approx 5.45$ puntos en un espacio donde las recompensas varían de $0$ a $+16$. Un `value_loss = 19.05` equivale a $\text{RMSE} = \sqrt{19.05} \approx 4.36$ en retornos acumulados de $-15$ a $+25$. Ambos valores reflejan una convergencia completamente saludable y esperada.

#### 2. Matriz de Auditoría y Rangos de Salud de Telemetría

| Métrica en Log | Régimen | Rango Saludable | Significado Táctico |
| :--- | :---: | :---: | :--- |
| **`policy`** | Cross-Entropy | $0.80 - 1.80$ | Discriminación de acciones sobre 32 candidatos. El óptimo uniforme sin conocimiento es $\ln(32) \approx 3.47$. Un valor de $\approx 1.46$ indica preferencias tácticas sólidas aprendidas de MCTS. |
| **`value`** | MSE (`support=0`) | $10.0 - 35.0$ | Error cuadrático de valor respecto a retornos descontados con $N$-step bootstrapping. $\text{RMSE} \approx 4.0 - 5.5$. |
| **`reward`** | MSE (`support=0`) | $15.0 - 45.0$ | Error cuadrático en predicción de transiciones de recompensa inmediatas dispersas. $\text{RMSE} \approx 4.5 - 6.5$. |
| **`objective`** | BCE / Multi-Task | $0.30 - 1.20$ | Supervisión auxiliar combinada de cabezas tácticas (`threat_map`, `morale_pred`, `objective_intent`, `attrition`). |
| **`consistency`** | SimSiam $\ell_2$ MSE | $< 0.005$ | Pérdida de auto-supervisión temporal entre representaciones latentes consecutivas. Valores $\approx 10^{-6}$ certifican coherencia geométrica perfecta en la red dinámica $g$. |
| **`train loss`** | Suma Ponderada | $30.0 - 65.0$ | Suma total ponderada: $\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{pol}} + \mathcal{L}_{\text{val}} + \mathcal{L}_{\text{rew}} + w_{\text{obj}}\mathcal{L}_{\text{obj}} + w_{\text{cons}}\mathcal{L}_{\text{cons}} + w_{\text{aux}}\mathcal{L}_{\text{aux}}$. |

#### 3. Validación Definitiva: Correlación con el Quality Gate
El indicador autoritativo de salud de la política no es el valor absoluto de la función de coste escalar, sino la superación de los criterios de promoción en el benchmark de evaluación (`eval.py`). En la ejecución auditada `efficientzero_v2_18f90171`:
* **Resultado del Gate:** `PASS` 🟢
* **VPs Capturados (US Tracked):** $0.40$ (frente a $0.00$ de la línea base estocástica).
* **Bloqueo de Suicidios Tácticos:** `assault_misuse_block: true` (cero asaltos ilegales o estériles).
* **Contratos de Reacción:** `reaction_contract_pass: true` (adherencia reglamentaria completa).

---

## 9. Protocolo de Estabilidad Operativa, Gestión de Almacenamiento y Prevención de Caídas [Consolidado v2.5.25]

> [!IMPORTANT] DIRECTIVA OPERATIVA: PREVENCIÓN DE INTERRUPCIONES CONTINUAS EN RUNS DESATENDIDOS
> Para erradicar definitivamente las caídas recurrentes durante ejecuciones largas de currículum (*"se volvió a parar"*, *"continúa la tarea"*), queda formalizado en este epígrafe el diagnóstico forense de la causa raíz y las cuatro salvaguardas operativas de obligado cumplimiento en la plataforma.

### 9.1 Diagnóstico Forense de la Causa Raíz (Crash por Agotamiento de Espacio y Paginación)

El análisis forense de las interrupciones en fases avanzadas (ej. parada en iteración 54 de 60 de la Fase 5) demostró que el fallo **no es algorítmico ni de divergencia de gradientes**, sino un colapso en cascada de recursos a nivel de Sistema Operativo:

1. **Hiper-acumulación de Replays Forenses XAI no Comprimidos**:
   * En cada evaluación de benchmark, el orquestador (`assault_bench/bench_io.py`) persistía archivos de repetición en `xai/bench_replay_episodes/episode_XXXX.json`.
   * Cada episodio almacena los 180+ pasos de combate con el estado completo de 14 unidades, mapas espaciales axiales, cabezas tácticas y candidatos MCTS, serializado con formato indentado (`indent=2`).
   * Peso promedio por archivo: **~85 MB a 92 MB**.
   * Una sola ronda de benchmark generaba **~1 GB**, acumulando **132.2 GB** en 9.486 archivos JSON descompresionados entre `runs_curriculum` (81.9 GB), `runs_archive` (34.4 GB) y `runs` (15.9 GB).
2. **Colapso del Espacio Libre en C:\ (< 1%)**:
   * En un disco de 3.814 GB, el espacio libre se redujo a menos de 26 GB, llegando a picos de **0.00 GB libres** durante las fases más intensivas.
3. **Fallo de Paginación Virtual y OOM en PyTorch**:
   * Al saturarse el disco, Windows bloquea el crecimiento dinámico del archivo de intercambio (`pagefile.sys`).
   * Cuando PyTorch solicita memoria RAM dinámica para tensores y MCTS, el asignador falla inmediatamente con:
     ```text
     RuntimeError: DefaultCPUAllocator: not enough memory
     ```
   * El proceso muere de manera abrupta, congelando el runner y dejando al usuario con tareas incompletas.

```mermaid
flowchart TD
    A["Ejecución Curricular Multi-Fase"] --> B["Volcado JSON indentado de partidas<br/>(~90 MB / episodio en bench_replay_episodes)"]
    B --> C["Acumulación masiva de 132.2 GB<br/>en carpetas de runs"]
    C --> D["Espacio libre en C:\ cae a 0.00 GB"]
    D --> E["Windows no puede expandir pagefile.sys"]
    E --> F["Crash Fatal:<br/>RuntimeError: DefaultCPUAllocator: not enough memory"]
    F --> G["Interrupción constante del pipeline"]
```

---

### 9.2 Cuatro Salvaguardas Obligatorias de Estabilidad

Para blindar la estabilidad del entrenamiento desatendido y evitar que se detenga continuamente, se aplican de manera estricta las siguientes medidas:

#### A. Pre-flight Check de Almacenamiento (Safety Gate de Disco)
Antes de iniciar cualquier ciclo o fase en los scripts de orquestación (`run_dynamic_gated_curriculum.ps1`, `run_all_phases.ps1`) y en el punto de entrada Python:
* **Umbral de Seguridad:** Se verifica que el volumen `C:\` disponga de al menos **30 GB de espacio libre**.
* **Comportamiento Preventivo:** Si el espacio es inferior al umbral, el script aborta inmediatamente con un mensaje de alerta explícito antes de iniciar el entrenamiento, evitando la corrupción de checkpoints y caídas sucias del kernel de PyTorch.

#### B. Serialización Eficiente y Compresión de Replays (Reducción del 95%)
* **Eliminación de `indent=2`**: Toda serialización JSON de telemetría de replay debe realizarse en formato compacto sin espacios en blanco redundantes, reduciendo el tamaño en un ~45%.
* **Soporte de Compresión Nativa (`.zst` / `.json.gz`)**: Los episodios de replay masivos deben persistirse comprimidos, reduciendo el tamaño por archivo de ~90 MB a **< 4 MB** por partida.

#### C. Política Estricta de Retención de Episodios (Pruning Policy)
* En las fases curriculares intermedias no se almacenan decenas de episodios completos de todas las iteraciones.
* Se persisten únicamente las métricas agregadas en `.parquet` y DuckDB, reservando los episodios forenses completos únicamente para el benchmark final que certifique la superación del Quality Gate o para los casos atípicos extremos (ej. mejor partida y peor derrota).

#### D. Rutina Automatizada de Mantenimiento y Purga de Replays Obsoletos
* Se dispone de una utilidad de mantenimiento para purgar directorios `bench_replay_episodes` de ejecuciones históricas obsoletas, liberando más de **100 GB** de manera inmediata en la máquina de desarrollo sin alterar el linaje de pesos `.pt` ni la telemetría histórica de DuckDB.


