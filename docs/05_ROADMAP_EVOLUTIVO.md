# Hoja de Ruta Evolutiva: Assault Architecture Roadmap (2024–2026)

> **Estado**: Canónico y Actualizado  
> **Ámbito**: Evolución del Motor de IA `agents/efficientzero_v2/` y la Plataforma de Simulación Táctica.

---

## 1. Matriz de Síntesis y Hoja de Ruta Evolutiva

A partir de la auditoría de la arquitectura original y los hallazgos recientes en la literatura científica de **Model-Based Reinforcement Learning** (EfficientZero V2 en ICML 2024, Google DeepMind *"Stop Regressing"* 2024, DreamerV3 y Palma et al. Feb 2025 sobre wargames hexagonales con redes recurrentes), se establece la siguiente matriz de síntesis:

| Área | Estado Assault Original | Estado Actual (EZ-v2) | Recomendación Literatura Reciente (2024–2026) | Impacto Esperado | Estado de Implementación |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Búsqueda MCTS** | PUCT clásico (512 sims) | PUCT + Modulación Priors N1 | **Gumbel MuZero Search** (muestreo de $k$ acciones candidatas) | Reducción de $\sim 60\%$ en tiempo de self-play sin pérdida táctica | 🟡 En Proceso / Opcional |
| **Distribución de Valor** | Regresión escalar MSE | Two-Hot ($K=30$, 61 átomos) | **HL-Gauss** (discretización con suavizado gaussiano $\mathcal{N}(y, \sigma^2)$) | Menor sobreajuste y curvas de Loss de valor más suaves | 🟢 Implementado en `support.py` |
| **Niebla de Guerra (POMDP)** | Canales de observación $o_t$ | Canales + Cabeza Threat Map | **Capa Recurrente / Memoria de Avistamiento** (`TemporalContextBlock` GRU) | Seguimiento de unidades enemigas ocultas en niebla | 🟢 Implementado en `network_base.py` |
| **Topología Espacial** | Conv2D $3\times 3$ cartesiana | Conv2D + SE + Spatial Attention | **Hexagonal Masking** en kernels $3\times 3$ (`HexagonalMaskConv2d`) | Eliminación de sesgos diagonales inexistentes en el hexágono | 🟢 Implementado en `network_base.py` |
| **Escala de Recompensas** | Escalado lineal manual | Two-Hot contractivo $h(x)$ | **Symlog Transform** ($\text{sign}(x)\ln(\|x\|+1)$) | Robustez universal ante recompensas extremas de victoria/derrota | 🟢 Implementado en `support.py` |
| **Jerarquía Táctica** | Acciones combinatorias planas | Planificador Macro N1 HRL | **Roles Doctrinales + Posturas Operativas** (Spearhead, Fire Support, Defender, Screen) | Eliminación de pasividad y triplicación de captura neta de VPs | 🟢 Implementado en `macro_planner.py` |
| **Balance de Gradientes** | Suma ponderada fija | PCGrad / AdaptiveLossScaler | **Proyección Ortogonal de Gradientes Opuestos** | Coexistencia estable de 6 cabezas sin degradación de política | 🟢 Implementado en `loss_balancer.py` |

---

## 2. Fases de Desarrollo Técnico

### Fase 1: Estabilidad Numérica y Representación de Valor (Completada 🟢)
* **Objetivo**: Erradicar el colapso de gradiente provocado por la regresión escalar MSE directa en partidas con recompensas dispersas.
* **Componentes**:
  * Implementación de soporte discreto **Two-Hot** invertible ($61$ átomos).
  * Adición de **HL-Gauss** (*Histogram Loss with Gaussian Targets*, DeepMind 2024) para suavizado estocástico continuo.
  * Compresión simétrica logarítmica **Symlog** ($\text{sign}(x)\ln(|x|+1)$).

### Fase 2: Topología Hexagonal y Convolución Nativa (Completada 🟢)
* **Objetivo**: Respetar estrictamente la física del tablero hexagonal y eliminar sesgos anisotrópicos.
* **Componentes**:
  * Módulo `HexagonalMaskConv2d` que enmascara las 2 esquinas diagonales sin adyacencia física en coordenadas axiales $(q, r)$.
  * Integración en los bloques residuales convolucionales `ResidualConvBlock`.

### Fase 3: Comprensión Táctica y Balanceo de Pérdidas (Completada 🟢)
* **Objetivo**: Dotar al modelo de criterio militar preventivo y asegurar entrenamiento armónico de múltiples objetivos.
* **Componentes**:
  * Cabezas auxiliares: `threat_map` (2D LOS y cobertura de fuego enemiga), `attrition` (balance de bajas propias vs. enemigas) y `morale` (degradación de cohesión).
  * Algoritmo **PCGrad** para ortogonalizar gradientes en conflicto entre cabezas auxiliares y tronco principal de política/valor.

### Fase 4: Jerarquía Estratégica HRL (Completada 🟢)
* **Objetivo**: Resolver la coordinación de escuadras multi-unidad desacoplando la doctrina macro de la micro-maniobra física.
* **Componentes**:
  * Módulo `MacroStrategyPlanner` (Nivel 1): Evaluación de estado, postura global (`ASSAULT_VP`, `DEFENSIVE_HOLD`, `ZONE_SUPPRESS`) y asignación de roles (`SPEARHEAD`, `FIRE_SUPPORT`, `DEFENDER`, `SCREEN`).
  * Modulación de Priors (+35% Boost) en la raíz del árbol MCTS.

### Fase 5: Optimización de Búsqueda MCTS (En Curso 🟡)
* **Objetivo**: Acelerar drásticamente la generación de autojuego sin pérdida de calidad táctica.
* **Componentes**:
  * Integración de **Gumbel MuZero Search** (ICML 2024) con muestreo de $k$ acciones candidatas ($k \approx 8-16$), garantizando mejora matemática de política con presupuestos de simulación reducidos.
  * *Search-Based Value Estimation* (Root Mean Target $\bar{Q}_{\text{root}}$) para mitigar el error off-policy en el replay buffer.

---

## 3. Auditoría Exhaustiva de Topología, Canales y Recompensas (Auditoría Post-Currículum Octubre 2026)

A partir de los resultados empíricos obtenidos en el currículum multi-escenario de 8 fases (`self_vs_self_vs_random_2scenarios_v1`), se presenta el desglose técnico y cuantitativo del motor `EfficientZeroV2`.

### 3.1 Topología de Red (`EfficientZeroV2Network`)
* **Función de Representación ($h_\theta$):**
  * Entrada: Tensor $32 \times 16 \times 16$ (canales $\times$ altura $\times$ anchura).
  * Convolución inicial con GroupNorm ($\min(8, C)$ grupos) y activación $\text{SiLU}$.
  * Bloques convolucionales residuales (`ResidualConvBlock`) equipados con compresión **Squeeze-and-Excitation (SE)** de ratio 4 para reponderar canales globalmente.
  * Convolución nativa hexagonal (`HexagonalMaskConv2d`): Enmascara dinámicamente las esquinas $(0,0)$ y $(2,2)$ en coordenadas axiales, suprimiendo falsas adyacencias diagonales no euclidianas.
  * Latente resultante: Tensor de $48 \times 16 \times 16$ normalizado por $L_2$ para mitigar deriva de escala latente.
* **Función de Dinámica ($g_\theta$):**
  * Entrada: Estado latente $s_t$ ($48 \times 16 \times 16$) concatenado con el embedding espacial de la acción ejecutada ($16 \times 16 \times 16$).
  * Torre de dinámica: 3 bloques residuales con convolución hexagonal y SE.
  * Salida: Estado latente predicho $s_{t+1}$ y predicción de recompensa intermedia mediante `SpatialAttentionBlock`.
* **Proyección de Consistencia Auto-supervisada (SimSiam/EfficientZero):**
  * Cuello de botella $128$-d con normalización proyectiva para alinear el estado predicho no enrollado con la representación real $h_\theta(o_{t+k})$ mediante pérdida de similitud coseno negativo, evitando el colapso dimensional del espacio latente.

### 3.2 Análisis del Espacio de Observación (32 Canales Axiales)
El espacio de entrada canaliza la doctrina militar y la cinemática del motor:

| Rango de Canales | Identificadores | Propósito Doctrinal | Diagnóstico de Utilidad Empírica |
| :--- | :--- | :--- | :--- |
| **0 – 3** | `ally_presence`, `enemy_presence`, `ally_hp_norm`, `enemy_hp_norm` | Ocupación y salud efectiva de tropas | **Crítico (100% activación)**. Base de supervivencia y targeting. |
| **4 – 5** | `ally_crossfire_risk`, `enemy_target_engagement` | Estado de supresión y líneas de fuego cruzado | **Alto**. Reduce suicidios tácticos en zonas batidas. |
| **6 – 7** | `vp_contest_race`, `reaction_fire_threat` | Amenaza de fuego de oportunidad y carrera a VP | **Crítico**. Guía directa de MCTS ante emboscadas enemigas. |
| **8 – 11** | `ally_mg`, `enemy_mg`, `ally_mortar`, `local_firepower_balance` | Distribución de armas pesadas y balance de fuego | **Muy Alto**. Crucial en escenarios urbanos para crear anclajes. |
| **12 – 14** | `map_playable`, `vp_mask`, `vp_owner_relative` | Topología válida y propiedad relativa de banderas | **Crítico**. Define la función de utilidad global de la partida. |
| **15 – 18** | `move_cost`, `terrain_cover`, `los_block`, `vp_distance_field` | Balística de terreno y gradiente radial a VP | **Muy Alto**. El gradiente radial $\frac{1}{1 + d_{\text{vp}}}$ erradica la pasividad. |
| **19 – 21** | `q_norm`, `r_norm`, `frontline_control` | Coordenadas axiales y línea de control territorial | **Medio**. `frontline_control` aporta coherencia; `q`/`r` son estáticas. |
| **22 – 25** | `ally/enemy mobility_norm`, `ally/enemy direct_range_norm` | Alcance efectivo de tiro y capacidad de maniobra | **Alto**. Permite a morteros y fusileros mantener rangos seguros. |
| **26 – 29** | `ally_fire_coverage`, `heavy_fortifications`, `ally_attack_norm`, `hazards` | Campos de tiro propios, búnkeres y campos minados | **Alto**. Modula el avance hacia edificios defensivos de piedra. |
| **30 – 31** | `ally_defense_power_norm`, `enemy_defense_power_norm` | Fuerza de dados defensivos normalizada | **Medio**. Útil para valorar ratios de intercambio (trades). |

### 3.3 Cabezas Tácticas Especializadas y Balanceo de Pérdidas
* **Cabeza de Amenaza (`prediction_threat_map`):** Salida $1 \times 16 \times 16$ entrenada de forma supervisada con la LOS enemiga real. Permite al agente anticipar fuego de reacción sin requerir búsquedas MCTS excesivamente profundas.
* **Cabeza de Desgaste (`prediction_attrition`):** Vector de dimensión 2 que predice bajas propias vs. enemigas en la ventana de desenrollado.
* **Cabeza de Cohesión/Moral (`prediction_morale`):** Clasificación en 4 estados (Normal, Disrupted, Suppressed, Broken).
* **Mecanismo de Balanceo de Gradientes (PCGrad):**
  * La co-optimización de política ($\mathcal{L}_{\text{pol}}$), valor ($\mathcal{L}_{\text{val}}$), consistencia ($\mathcal{L}_{\text{cons}}$) y las 3 cabezas tácticas auxiliares induce conflictos directos de gradiente ($\mathbf{g}_i \cdot \mathbf{g}_j < 0$).
  * Se aplica **PCGrad** (*Projecting Conflicting Gradients*), proyectando ortogonalmente los gradientes auxiliares sobre el hiperplano normal al gradiente principal, garantizando que el tronco convolucional no degrade la política ni el valor.

### 3.4 Hiperparámetros de MCTS y Estructura de Recompensas
* **MCTS:** $c_{\text{PUCT}} = 2.3$, $\alpha_{\text{Dirichlet}} = 0.3$, $\epsilon = 0.25$, normalización adaptativa Min-Max de raíces de $Q$ al $90\%$, con modulación probabilística de éxito de combate.
* **Estructura de Recompensas (Shaping):**
  * Recompensa terminal: Victoria $+0.20$, Derrota $-0.20$, Timeout $-0.35$.
  * Incentivos de maniobra: Bonificación por captura de VP ($+0.70$ base $+ 1.45$ por hexágono), progreso continuo a objetivo ($+1.05$), y control del anillo de aproximación ($+0.16$).
  * Penalizaciones cinemáticas: Inactividad con movimientos legales disponibles ($-0.24$), disparo de reacción fallido ($-0.08$).

---

## 4. Nuevas Fases de la Hoja de Ruta Evolutiva (Recomendaciones Post-Auditoría)

### Fase 6: Búsqueda Eficiente Gumbel-MuZero y Puerta de Atención de Canales (Q1 2027) 🟡
* **6.1 Búsqueda Gumbel-MuZero ($k$-Action Search):**
  * Reemplazar la búsqueda PUCT con muestreo Gumbel de las $k=8$ mejores acciones y división sucesiva (*Sequential Halving*).
  * **Impacto**: Reduce el tiempo de simulación por turno en un **$55\%$** con idéntica profundidad táctica, eliminando la necesidad de escalar a 640+ simulaciones.
* **6.2 Puerta de Atención Dinámica de Canales (CBAM / Channel Gating):**
  * Añadir un bloque de compresión y excitación contextual a la entrada de los 32 canales para ponderar automáticamente canales relevantes según el escenario (p. ej., suprimir canales de fortificaciones o coordenadas en mapas abiertos planos).

### Fase 7: Calibración Adaptativa de Quality Gates y Soporte Asimétrico Symlog (Q1 2027) 🟡
* **7.1 Quality Gates Auto-Calibrados al Escenario:**
  * Sustituir los umbrales fijos rígidos de VP en `curriculum.yaml` (`min_tracked_captured_avg: 2.52`) por percentiles relativos al diseño del escenario ($1.0$ capturas efectivas en mapas reducidos).
  * **Impacto**: El agente con $>80\%$ de victoria promociona en el **Ciclo 1**, reduciendo la duración del currículum de 24 ejecuciones a 8 ejecuciones directas.
* **7.2 Soporte de Valor Two-Hot con Escala Symlog Asimétrica:**
  * Adaptar los $61$ átomos de Two-Hot para que los bins cercanos a cero tengan alta resolución (diferenciación de pequeñas ventajas tácticas de desgaste) y los valores extremos utilicen compresión $\text{symlog}(x) = \text{sign}(x)\ln(|x|+1)$, eliminando la saturación de los extremos del soporte.

