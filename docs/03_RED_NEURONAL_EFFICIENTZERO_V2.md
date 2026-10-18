# Red Neuronal y Motor de Inteligencia Artificial: EfficientZero V2

> **Estado**: Canónico y Exhaustivo  
> **Directiva Fundamental**: El motor de aprendizaje es exclusivamente **EfficientZero V2** (`agents/efficientzero_v2/`). MuZero v1 clásico está 100% decomisionado.

---

## 1. Topología General de la Red Neuronal

La red de **EfficientZero V2** implementa un modelo de mundo diferenciable capaz de planificar en un espacio latente continuo sin requerir llamadas al simulador físico durante la búsqueda en árbol.

```mermaid
flowchart TD
    subgraph Entrada ["1. Entrada Sensorial (Tablero Hexagonal)"]
        OBS["Observación o_t\n(32 canales x 16 x 16)"]
    end

    subgraph Jerarquia_N1 ["2. Nivel 1: Planificador Macro Jerárquico"]
        MACRO["MacroStrategyPlanner\nPostura Global + Roles Doctrinales"]
        OBS --> MACRO
    end

    subgraph Representacion ["3. Red de Representación h_θ(o)"]
        OBS --> REP_IN["HexagonalMaskConv2d (32 -> 48) + GroupNorm + SiLU"]
        REP_IN --> REP_TOWER["Tower: Bloques Residuales SE (48ch)\n+ Máscara Hexagonal de 6 Vecinos"]
        REP_TOWER --> LATENT_0["Estado Latente Raíz s_0\n(48 canales x 16 x 16)"]
    end

    subgraph Dinamica ["4. Red de Dinámica Recurrente g_θ(s, a)"]
        LATENT_0 --> DYN_CONCAT
        ACTION["Acción Candidata a_t\n(Embedding Broadcast 1 x 16 x 16)"] --> DYN_CONCAT["Concatenación (48 + 1 = 49ch)"]
        DYN_CONCAT --> DYN_TOWER["Bloques Residuales Recurrentes (48ch)"]
        DYN_TOWER --> LATENT_NEXT["Siguiente Estado Latente s_{t+1}"]
        DYN_TOWER --> REW_HEAD["Reward Head: Conv1x1 -> AdaptiveAvgPool -> Two-Hot / HL-Gauss"]
        REW_HEAD --> REW_PRED["Recompensa Inmediata r_{t+1}"]
    end

    subgraph Prediccion ["5. Tronco de Predicción y Cabezas f_θ(s)"]
        LATENT_0 --> P_TRUNK["Spatial Attention Bottleneck (4x4)"]
        LATENT_NEXT --> P_TRUNK
        
        P_TRUNK --> HEAD_POL["Política f_p(s): 32 Logits Prior\n(Modulado +35% por Nivel 1)"]
        P_TRUNK --> HEAD_VAL["Valor f_v(s): Two-Hot / HL-Gauss\n[-30, +30] con Symlog / Phi"]
        P_TRUNK --> HEAD_OBJ["Objetivo f_o(s): Progreso VP"]
        P_TRUNK --> HEAD_THREAT["Amenaza f_threat(s): Mapa 2D de LOS/Fuego"]
        P_TRUNK --> HEAD_ATTR["Desgaste f_attr(s): Vector Bajas [Amigas, Enemigas]"]
        P_TRUNK --> HEAD_MORALE["Moral f_morale(s): Cohesión (4 Clases)"]
    end

    subgraph Consistencia ["6. Proyector de Consistencia Temporal q_θ(s)"]
        LATENT_0 --> PROJ["Consistency MLP: 128d Normalizado"]
        PROJ --> Z_VEC["Vector z_t (|z|=1)"]
    end

    MACRO -.->|Modulación de Priors| HEAD_POL
```

---

## 2. Los 5 Componentes del Modelo de Mundo

### 2.1. Red de Representación ($h_\theta$)
* **Entrada**: Tensor espacial sensorial $o_t \in \mathbb{R}^{B \times 32 \times H \times W}$ construido por `voec_sim`.
* **Convoluciones con Máscara Hexagonal (`HexagonalMaskConv2d`)**: A diferencia de las convoluciones cartesianas $3\times 3$, anula estáticamente las dos esquinas diagonales que no comparten arista en la cuadrícula hexagonal axial $(q, r)$, eliminando la distorsión anisotrópica.
* **Bloques Residuales con Squeeze-and-Excitation (SE)**: Cada bloque residual cuenta con un cuello de botella SE que recalibra la relevancia de los 48 canales latentes según el contexto táctico.
* **Salida**: Estado latente abstracto inicial $s_0 \in \mathbb{R}^{B \times 48 \times H \times W}$.

### 2.2. Red de Dinámica ($g_\theta$)
* **Entrada**: Estado latente $s_k$ concatenado con el embedding espacial de la acción ejecutada $a_k$.
* **Evolución Temporal Latente**: Predice cómo cambia el estado del campo de batalla sin simular la física:
  $$g_\theta(s_k, a_k) \to (s_{k+1}, \hat{r}_{k+1})$$
* **Escalado Min-Max Latente**: Para evitar que las activaciones exploten o se desvanezcan a lo largo del desenrollado recursivo ($k=1 \dots 6$), cada estado latente recurrente se re-normaliza dinámicamente:
  $$s_{\text{norm}} = \frac{s - \min(s)}{\max(s) - \min(s) + \epsilon}$$

### 2.3. Red de Predicción ($f_\theta$)
Proyecta cualquier estado latente $s_k$ a las variables clave de decisión:
* **Cabezal de Política ($f_p$)**: Vector de logits sobre las 32 acciones candidatas prefiltradas.
* **Cabezal de Valor ($f_v$)**: Distribución sobre el retorno esperado acumulado hasta el fin de la partida.
* **Cabezal de Objetivos Auxiliares ($f_o$)**: Predicción escalar de captura o progreso hacia Puntos de Victoria (VPs).

### 2.4. Proyector de Consistencia Temporal ($q_\theta$) y Pérdida SimSiam
Para evitar el colapso de representación (donde la red de dinámica aprende a predecir un estado latente trivial o constante), el proyector $q_\theta$ alinea el estado imaginado $s_{k}$ con la representación real de la observación futura $h_\theta(o_{t+k})$:
$$\mathcal{L}_{\text{consistency}} = -\frac{1}{2} \left( \frac{q_\theta(s_k)}{\|q_\theta(s_k)\|_2} \cdot \text{stop\_grad}\left(\frac{h_\theta(o_{t+k})}{\|h_\theta(o_{t+k})\|_2}\right) \right)$$

---

## 3. Cabezas Tácticas Auxiliares de Comprensión Profunda

Para dotar al modelo de criterio militar en el wargame, se incorporan tres cabezas auxiliares entrenadas conjuntamente con el tronco principal:

```mermaid
graph LR
    S["Estado Latente s"] --> T["f_threat(s)\nMapa 2D de Amenaza"]
    S --> A["f_attr(s)\nVector Bajas [A, E]"]
    S --> M["f_morale(s)\nCohesión (4 Clases)"]
    
    T --> T_OUT["Logits por Hexágono [1, H, W]\nRiesgo de Fuego y LOS Enemiga"]
    A --> A_OUT["Bajas Propias vs Enemigas\nEvita Victorias Pírricas"]
    M --> M_OUT["Probabilidad de Supresión\nNORMAL / PINNED / SUPPRESSED / ROUTED"]
```

1. **`prediction_threat_map` ($f_{\text{threat}}$)**: Proyecta una matriz bidimensional $H \times W$ con la probabilidad de recibir fuego en cada hexágono, guiando al agente a navegar tras coberturas y fuera de líneas de tiro enemigas.
2. **`prediction_attrition` ($f_{\text{attr}}$)**: Predice el balance neto de desgaste (bajas aliadas esperadas vs. bajas enemigas infligidas). Permite al agente distinguir victorias tácticas limpias de victorias pírricas insostenibles.
3. **`prediction_morale` ($f_{\text{morale}}$)**: Predice la distribución de probabilidad sobre los estados de moral táctica (`NORMAL`, `PINNED`, `SUPPRESSED`, `ROUTED`), fomentando repliegues preventivos antes de que las escuadras entren en pánico.

---

## 4. Representación Discreta de Valor: Two-Hot, HL-Gauss y Symlog

La literatura reciente de Deep Reinforcement Learning (Google DeepMind 2024, DreamerV3) demuestra que la regresión escalar directa mediante error cuadrático medio (MSE) fracasa ante recompensas dispersas y multiescala.

### 4.1. Transformaciones Contractivas: $\phi$-Transform y Symlog
Para comprimir la escala dinámica sin perder resolución en torno a cero:
* **$\phi$-Transform Canónica**:
  $$h(x) = \text{sign}(x)(\sqrt{|x| + 1} - 1) + \epsilon x$$
* **Symlog Transform (DreamerV3)**:
  $$\text{symlog}(x) = \text{sign}(x) \ln(|x| + 1)$$
  $$\text{symexp}(y) = \text{sign}(y) (\exp(|y|) - 1)$$

### 4.2. Discretización de Soporte: Two-Hot vs. HL-Gauss

| Característica | Two-Hot Clásico | HL-Gauss (DeepMind 2024, "Stop Regressing") |
| :--- | :--- | :--- |
| **Mapeo de Probabilidad** | Rígido sobre los 2 átomos vecinos más cercanos. | Distribución Gaussiana continua $\mathcal{N}(y, \sigma^2)$ extendida sobre el histograma. |
| **Función Objetivo** | Cross-Entropy sobre átomos discretos. | Cross-Entropy / Divergencia KL contra la campana gaussiana. |
| **Efecto de Regularización**| Puede sufrir sobreajuste o picos de varianza en horizontes largos. | Actúa como *label smoothing* estocástico natural; gradientes notablemente más suaves y estables. |
| **Recuperación Escalar** | $\hat{v} = h^{-1}\left(\sum_{i=-K}^{K} i \cdot p_i\right)$ | $\hat{v} = \text{symexp}\left(\sum_{i=-K}^{K} z_i \cdot p_i\right)$ |

---

## 5. Planificador Macro Jerárquico HRL (Nivel 1)

El mayor desafío en wargames tácticos es la coordinación simultánea de múltiples escuadras en un espacio de acción combinatorio. *Assault* resuelve esto mediante una jerarquía de toma de decisiones en dos niveles:

```mermaid
flowchart TD
    subgraph N1 ["Nivel 1: Planificador Macro Estratégico"]
        EVAL["Evaluación de Estado de Partida\n(Control de VPs, balance de bajas y amenaza global)"]
        POSTURE["Selección de Postura Macro:\n1. ASSAULT_VP (Ofensiva agresiva)\n2. DEFENSIVE_HOLD (Consolidar ventaja)\n3. ZONE_SUPPRESS (Dominar con fuego)"]
        ROLES["Asignación Doctrinal de Roles por Escuadra:\n- SPEARHEAD (Vanguardia de asalto)\n- FIRE_SUPPORT (Ametralladoras / Morteros)\n- OBJECTIVE_DEFENDER (Guarnición de VP)\n- FLANK_SCREEN (Pantalla de seguridad)"]
        
        EVAL --> POSTURE --> ROLES
    end

    subgraph N2 ["Nivel 2: Búsqueda Táctica MCTS PUCT"]
        PRIORS["Modulación de Priors:\nP_mod(a) = P(a) * (1 + 0.35 * Boost(Postura, Rol, a))"]
        TREE["Árbol de Búsqueda MCTS (512 simulaciones / 6 unrolls)"]
        
        PRIORS --> TREE
    end

    ROLES ==> PRIORS
```

* **Desacoplamiento Operativo**: El Nivel 1 no decide cada paso físico de una unidad; define la doctrina.
* **Modulación de Priors**: Durante el paso raíz del MCTS, las acciones tácticas que coinciden con el rol de la unidad y la postura del equipo reciben un bono del $+35\%$ en su probabilidad prior $P(a)$. Esto guía la búsqueda de Monte Carlo hacia rutas coherentes con el plan general sin eliminar la libertad del árbol para encontrar maniobras tácticas imprevistas.

---

## 6. Mitigación de Conflicto de Gradientes: PCGrad

Al entrenar simultáneamente la política, el valor, el objetivo y las tres cabezas tácticas, los gradientes pueden entrar en conflicto destructivo:
$$\langle g_{\text{task}_i}, g_{\text{task}_j} \rangle < 0$$

Para resolverlo, el balanceador de pérdidas utiliza **PCGrad (*Projecting Conflicting Gradients*)**:
Si dos gradientes apuntan en direcciones opuestas, el gradiente de la tarea secundaria se proyecta sobre el hiperplano ortogonal al de la tarea primaria:
$$g_i = g_i - \frac{g_i \cdot g_j}{\|g_j\|^2} g_j$$
Esto garantiza matemáticamente que ninguna cabeza táctica auxiliar degrade la calidad de la política o el valor del modelo.

---

## 7. Matriz de Síntesis y Hoja de Ruta Evolutiva (Roadmap 2024–2026)

A partir de la auditoría de la arquitectura original y los hallazgos recientes en la literatura científica de Model-Based RL (EfficientZero V2 en ICML 2024, Google DeepMind *"Stop Regressing"* 2024, DreamerV3 y Palma et al. Feb 2025 sobre wargames hexagonales con redes recurrentes), se establece la siguiente matriz de síntesis y hoja de ruta evolutiva:

| Área | Estado Assault Original | Estado Actual (EZ-v2) | Recomendación Literatura Reciente (2024–2026) | Impacto Esperado | Estado de Implementación |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Búsqueda MCTS** | PUCT clásico (512 sims) | PUCT + Modulación Priors N1 | **Gumbel MuZero Search** (muestreo de $k$ acciones candidatas) | Reducción de $\sim 60\%$ en tiempo de self-play sin pérdida táctica | 🟡 En Proceso / Opcional |
| **Distribución de Valor** | Regresión escalar MSE | Two-Hot ($K=30$, 61 átomos) | **HL-Gauss** (discretización con suavizado gaussiano $\mathcal{N}(y, \sigma^2)$) | Menor sobreajuste y curvas de Loss de valor más suaves | 🟢 Implementado en `support.py` |
| **Niebla de Guerra (POMDP)** | Canales de observación $o_t$ | Canales + Cabeza Threat Map | **Capa Recurrente / Memoria de Avistamiento** (`TemporalContextBlock` GRU) | Seguimiento de unidades enemigas ocultas en niebla | 🟢 Implementado en `network_base.py` |
| **Topología Espacial** | Conv2D $3\times 3$ cartesiana | Conv2D + SE + Spatial Attention | **Hexagonal Masking** en kernels $3\times 3$ (`HexagonalMaskConv2d`) | Eliminación de sesgos diagonales inexistentes en el hexágono | 🟢 Implementado en `network_base.py` |
| **Escala de Recompensas** | Escalado lineal manual | Two-Hot contractivo $h(x)$ | **Symlog Transform** ($\text{sign}(x)\ln(\|x\|+1)$) | Robustez universal ante recompensas extremas de victoria/derrota | 🟢 Implementado en `support.py` |
| **Jerarquía Táctica** | Acciones combinatorias planas | Planificador Macro N1 HRL | **Roles Doctrinales + Posturas Operativas** (Spearhead, Fire Support, Defender, Screen) | Eliminación de pasividad y triplicación de captura neta de VPs | 🟢 Implementado en `macro_planner.py` |
| **Balance de Gradientes** | Suma ponderada fija | PCGrad / AdaptiveLossScaler | **Proyección Ortogonal de Gradientes Opuestos** | Coexistencia estable de 6 cabezas sin degradación de política | 🟢 Implementado en `loss_balancer.py` |

