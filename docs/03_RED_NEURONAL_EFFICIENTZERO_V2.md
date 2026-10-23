# Red Neuronal y Motor de Inteligencia Artificial: EfficientZero V2

> **Estado**: Canónico y Exhaustivo  
> **Directiva Fundamental**: El motor de aprendizaje es exclusivamente **EfficientZero V2** (`agents/efficientzero_v2/`). MuZero v1 clásico está 100% decomisionado.

---

## 1. Topología General de la Red Neuronal (EfficientZero V2)

La arquitectura desacoplada de **EfficientZero V2** implementa un modelo de mundo diferenciable de 4 componentes:
1. **Representación ($h_0$)**: Encoder espacial convolucional que proyecta la observación sensorial $o_t$ en un espacio latente continuo $s_0$.
2. **Dinámica Recurrente ($g$)**: Simula transiciones hacia adelante $s_{t+1} = g(s_t, a_t)$ y emite la recompensa inmediata $r_{t+1}$ sin consultar el motor de reglas físicas.
3. **Cabezas de Predicción ($f_	heta$)**: Evalúan la política prior $\pi(a)$, el valor $v(s)$, el objetivo auxiliar de VPs y las cabezas tácticas auxiliares (amenaza, desgaste, moral).
4. **Consistencia Auto-supervisada ($q_{\text{proj}}$)**: Estabiliza el espacio latente mediante proyección SimSiam, stop-gradient y norma $\ell_2$ unitaria.

```mermaid
flowchart TD
    subgraph Entrada ["1. ENTRADA SENSORIAL AGNOSTICA (Simulador VOEC)"]
        OBS["Observación o_t\n(Tensor 38 canales x 16 x 16)"]
    end

    subgraph Jerarquia_N1 ["2. NIVEL 1 - DOCTRINA (Planificador Macro HRL)"]
        MACRO["MacroStrategyPlanner\n• 5 Roles Doctrinales Dinámicos\n• Análisis Topográfico IPB Turno 0\n• Modulación Priors MCTS beta_macro"]
        OBS --> MACRO
    end

    subgraph Representacion ["3. ENCODER CNN: h_0(o) Representación (~400.128 params)"]
        OBS --> REP_IN["HexagonalMaskConv2d (38 -> 48) + GroupNorm + SiLU"]
        REP_IN --> REP_TOWER["3x ResidualBlockSE (48ch)\n6 Conv2D + Máscara Hexagonal + SE (ratio 4)"]
        REP_TOWER --> LATENT_0["ESTADO LATENTE s_0\n(48 canales x 16 x 16, Min-Max [-1, +1])"]
    end

    subgraph Dinamica ["4. RED DE DINÁMICA: g(s, a) -> s_1 (Unroll 5 pasos)"]
        LATENT_0 --> DYN_CONCAT
        ACTION["Acción MCTS a_0 (0..31)\n(Broadcast 1 x 16 x 16)"] --> DYN_CONCAT["Concatenación (48 + 1 = 49ch)"]
        DYN_CONCAT --> DYN_TOWER["dynamics_state: Conv3x3 + 3 ResBlocks + 2 Bottlenecks (48ch)"]
        DYN_TOWER -->|"Bucle Recurrente Weight-Tied (pasos 2..5)\nConcatenado con Plano Neutro (48 + 1 = 49ch)"| DYN_TOWER
        DYN_TOWER --> LATENT_NEXT["Siguiente Estado Latente s_1 (Min-Max Norm)\n(48 canales x 16 x 16)"]
        LATENT_NEXT --> REW_HEAD["Recompensa Inmediata r_1: Conv1x1 -> Pool -> Linear\nTwo-Hot / HL-Gauss (61 átomos)"]
    end

    subgraph Prediccion ["5. TRONCO DE PREDICCIÓN Y CABEZAS f_theta(s) (915.568 params totales)"]
        LATENT_0 --> P_TRUNK["prediction_trunk: 2x ResidualBlockSE (48ch)"]
        LATENT_NEXT --> P_TRUNK
        P_TRUNK --> S_ATTN["SpatialAttentionBlock (Conv 7x7 -> Gate Sigmoid)"]

        S_ATTN --> HEAD_POL["POLÍTICA f_pi\n32 Logits (Conv 1x1)\nLoss: ~2.10 | Coef: 77.5%"]
        S_ATTN --> HEAD_VAL["VALOR f_v\n1 Escalar [-1.0, +1.0] (Pool 2x2)\nLoss: ~0.12 | Coef: 10.0%"]
        S_ATTN --> HEAD_OBJ["OBJETIVO AUXILIAR f_aux\nProgreso VP (Pool 2x2)\nLoss: ~0.04 | Coef: 4.5%"]
        S_ATTN --> HEAD_CONS["CONSISTENCIA q_proj\nSimSiam (Pool 4x4, Stop-Grad)\nLoss: ~0.08 | Coef: 3.5%"]
        S_ATTN --> HEAD_THREAT["AMENAZA / GUARNICIÓN f_threat [TACTICAL]\nHeatmap 16x16 (FCN Conv / no-shrink)\nLoss: ~0.13 | Coef: 3.0%"]
        S_ATTN --> HEAD_ATTR["DESGASTE / DAÑO f_attr [TACTICAL]\nVector [Aliado / Enemigo] (Spatial Attention)\nLoss: ~0.02 | Coef: 2.0%"]
        S_ATTN --> HEAD_MORALE["ESTADO DE MORAL f_morale [TACTICAL]\n4 Clases (Normal / Pin / Supp / Rout)\nLoss: ~0.30 | Coef: 1.5%"]
    end

    MACRO -.->|Modulación Dinámica de Priors beta_macro (+35% / IPB)| HEAD_POL
```

### 1.1 Ficha Técnica de la Arquitectura (Telemetría MLOps Live Snapshot)

Conforme al panel de **Topología Dinámica de la Red Neuronal** en el Dashboard MLOps (`Puerto 8778 -> Network Topology -> Topology & Architecture`):

| Parámetro / Dimensión | Especificación Canónica | Detalle de Implementación |
| :--- | :---: | :--- |
| **Parámetros Totales del Modelo** | **915.568 parámetros** | Arquitectura v2: GroupNorm + Squeeze-and-Excitation + Convoluciones Bottleneck (-15% parámetros vs baseline legacy). |
| **Parámetros de Representación $h_0$** | **~400.128 parámetros** | Encoder espacial convolucional de entrada. |
| **Dimensiones de Entrada Sensorial** | **$B 	imes 38 	imes 16 	imes 16$** | 38 canales espaciales proyectados sobre coordenadas axiales $(q, r)$. |
| **Dimensiones de Estado Latente** | **$B 	imes 48 	imes 16 	imes 16$** | 48 canales latentes continuos con normalización Min-Max $s_{\text{norm}} = \frac{s - \min(s)}{\max(s) - \min(s) + \epsilon}$. |
| **Campo Receptivo de Representación** | **~15 $\times$ 15 hexágonos** | 3 bloques convolucionales $3\times 3$ con máscara hexagonal y compuertas SE. |
| **Espacio de Acciones** | **32 Logits** | Espacio discreto de maniobra táctica y combate. |
| **Desenrollado Recurrente (Unroll RQs)** | **5 Pasos ($k=5$)** | Profundidad de simulación latente weight-tied por cada paso MCTS. |
| **Bloques Convolucionales** | **3D + 2P** | 3 bloques en Dinámica + 2 bloques en Predicción + 3 en Representación. |
| **Precisión de Inferencia y Train** | **Auto (FP32 / AMP)** | Precisión adaptativa automática con optimizador AdamW fusionado en CUDA. |

### 1.2 Estructura y Ponderación Multitarea de las Cabezas Activas

Durante el entrenamiento en `trainer.py`, los gradientes de las 7 cabezas activas se balancean mediante **PCGrad** ponderados por los siguientes coeficientes relativos:

| Cabeza de Salida | Tipo de Arquitectura | Tensor de Salida | Coeficiente Relativo | Función Táctica Principal |
| :--- | :--- | :--- | :---: | :--- |
| **`POLÍTICA` ($f_\pi$)** | `Conv1x1(48 -> 4) -> MLP(1024 -> 64 -> 32)` | 32 Logits Prior | **77.5%** | Probabilidades prior $\pi(a \mid s)$ para guiar la búsqueda MCTS. |
| **`VALOR` ($f_v$)** | `AdaptiveAvgPool2d(2x2) -> Linear(128 -> 61)` | Escalar $[-1.0, +1.0]$ | **10.0%** | Retorno acumulado esperado modelado con Two-Hot / HL-Gauss. |
| **`OBJETIVO AUXILIAR` ($f_{\text{aux}}$)** | `AdaptiveAvgPool2d(2x2) -> Linear(128 -> 1)` | Escalar $[0.0, 1.0]$ | **4.5%** | Predicción del progreso diferencial de captura de VPs. |
| **`CONSISTENCIA` ($q_{\text{proj}}$)** | `SimSiam (Pool 4x4) -> Projector + Predictor` | Vector $\ell_2$ unitario | **3.5%** | Pérdida autosupervisada con stop-gradient que previene el colapso latente. |
| **`AMENAZA` ($f_{\text{threat}}$)** | `FCN Conv3x3 -> Conv1x1 (no-shrink)` | Heatmap $16\times 16$ | **3.0%** | Mapa espacial directo de líneas de tiro y amenaza de fuego de reacción. |
| **`DESGASTE` ($f_{\text{attr}}$)** | `SpatialAttentionBlock -> MLP` | Vector $[Aliado, Enemigo]$ | **2.0%** | Estimación de bajas esperadas en personal y potencia de fuego. |
| **`ESTADO DE MORAL` ($f_{\text{morale}}$)** | `SpatialAttentionBlock -> MLP` | 4 Clases | **1.5%** | Distribución categórica [Normal, Pinned, Suppressed, Routed]. |

---

## 2. Los 5 Componentes del Modelo de Mundo y Desglose de 49 Capas Conv2D

### 2.1. Red de Representación ($h_\theta$ — 19 Capas Conv2D)
* **Entrada**: Tensor espacial sensorial $o_t \in \mathbb{R}^{B \times 38 \times H \times W}$ construido por `voec_sim` y adaptado por `agents/efficientzero_v2/core/observation.py` ($16\times 16$, $32\times 32$, $64\times 64$).
* **Capas Internas**:
  * `Conv2d(38, 48, kernel_size=3, padding=1)` con máscara hexagonal.
  * `GroupNorm(num_groups=4, num_channels=48) + SiLU`.
  * 3x `ResidualBlockSE(48ch)`: cada uno con 2 convoluciones espaciales $3\times 3$ con GroupNorm y activación SiLU, complementadas con compuertas Squeeze-and-Excitation (SE ratio: 4).
* **Escalado Min-Max Latente**: $s_{\text{norm}} = \frac{s - \min(s)}{\max(s) - \min(s) + \epsilon}$.
* **Salida**: Estado latente abstracto $s_0 \in \mathbb{R}^{B \times 48 \times 16 \times 16}$.

### 2.1.1 Catálogo Canónico de los 38 Canales Espaciales de Entrada (Tensor $38 \times 16 \times 16$)

| Canal | Nombre Canónico | Categoría | Rango | Descripción Funcional |
| :---: | :--- | :---: | :---: | :--- |
| **Ch 00** | `ally_presence` | `UNITS` | $[0, 1]$ | $1.0$ en hexágonos ocupados por unidades aliadas activas. |
| **Ch 01** | `enemy_presence` | `UNITS` | $[0, 1]$ | $1.0$ en hexágonos con unidades enemigas detectadas. |
| **Ch 02** | `ally_hp_norm` | `UNITS` | $[0.0, 1.0]$ | Puntos de vida normalizados de las escuadras aliadas según `max_strength`. |
| **Ch 03** | `enemy_hp_norm` | `UNITS` | $[0.0, 1.0]$ | Puntos de vida normalizados de las escuadras enemigas según `max_strength`. |
| **Ch 04** | `ally_crossfire_risk` | `UNITS` | $[0.0, 1.0]$ | Riesgo de fuego cruzado enemigo sobre unidades aliadas / estado de supresión aliada. |
| **Ch 05** | `enemy_target_engagement` | `UNITS` | $[0.0, 1.0]$ | Hexágonos enemigos con objetivos aliados a su alcance de tiro / supresión enemiga. |
| **Ch 06** | `vp_contest_race` | `VP` | $[-1.0, +1.0]$ | Ventaja diferencial en carrera hacia el VP: $>0$ si el aliado llega antes, $<0$ si el enemigo lidera. |
| **Ch 07** | `reaction_fire_threat` | `UNITS` | $[0.0, 1.0]$ | Mapa de calor continuo de amenaza y fuego de reacción enemigo (*overwatch/opportunity fire*). |
| **Ch 08** | `ally_heavy_mg_support` | `UNITS` | $[0, 1]$ | $1.0$ para ametralladoras pesadas y medianas aliadas (HMG, MMG, MG42). |
| **Ch 09** | `enemy_heavy_mg_support` | `UNITS` | $[0, 1]$ | $1.0$ para ametralladoras pesadas y medianas enemigas (HMG, MMG, MG42). |
| **Ch 10** | `ally_indirect_mortar` | `UNITS` | $[0, 1]$ | $1.0$ para armas de tiro indirecto / morteros aliados (50mm, 60mm, 81mm). |
| **Ch 11** | `local_firepower_balance` | `UNITS` | $[-1.0, +1.0]$ | Balance local de potencia de fuego [$+1$ aliado dominante, $0$ disputado, $-1$ enemigo dominante]. |
| **Ch 12** | `map_playable` | `TERRAIN` | $[0, 1]$ | $1.0$ en hexágonos válidos del mapa; $0.0$ en los bordes fuera de tablero. |
| **Ch 13** | `vp_mask` | `VP` | $[0, 1]$ | $1.0$ en hexágonos que son Puntos de Victoria (VPs). |
| **Ch 14** | `vp_owner_relative` | `VP` | $[-1.0, +1.0]$ | $+1.0$ controlado por aliado, $-1.0$ por enemigo, $0.0$ disputado/neutral. |
| **Ch 15** | `terrain_move_cost_norm` | `TERRAIN` | $[0.0, 1.0]$ | Coste en puntos de movimiento (carretera = bajo, bosque/colina = alto). |
| **Ch 16** | `terrain_cover_norm` | `TERRAIN` | $[0.0, 1.0]$ | Bonificación defensiva de cobertura (edificios urbanos $= 0.5+$). |
| **Ch 17** | `terrain_los_block` | `TERRAIN` | $[0, 1]$ | Bloqueo de línea de visión por elevación o construcciones densas. |
| **Ch 18** | `vp_distance_field` | `VP` | $[0.0, 1.0]$ | Campo radial continuo de proximidad al VP más cercano ($1 / (1 + 	ext{dist})$). |
| **Ch 19** | `q_coord_norm` | `HEX` | $[-1.0, +1.0]$ | Coordenada axial Q del hexágono normalizada $[-1, 1]$. |
| **Ch 20** | `r_coord_norm` | `HEX` | $[-1.0, +1.0]$ | Coordenada axial R del hexágono normalizada $[-1, 1]$. |
| **Ch 21** | `frontline_control` | `HEX` | $[-1.0, +1.0]$ | Campo de potencial territorial $[-1, +1]$ (difusión y control de línea de frente). |
| **Ch 22** | `ally_mobility_norm` | `UNITS` | $[0.0, 1.0]$ | Puntos de movimiento disponibles restantes de la escuadra activa. |
| **Ch 23** | `enemy_indirect_mortar` | `UNITS` | $[0, 1]$ | $1.0$ para armas de tiro indirecto / morteros enemigos (50mm, 8cm). |
| **Ch 24** | `ally_direct_range_norm` | `UNITS` | $[0.0, 1.0]$ | Alcance de fuego directo y proyección 2D de alcance óptimo de combate aliado. |
| **Ch 25** | `enemy_direct_range_norm` | `UNITS` | $[0.0, 1.0]$ | Alcance de fuego directo y proyección 2D de alcance óptimo de combate enemigo. |
| **Ch 26** | `ally_fire_coverage` | `UNITS` | $[0.0, 1.0]$ | Heatmap de cobertura de fuego directo aliado sobre cada casilla del mapa. |
| **Ch 27** | `heavy_fortifications` | `TERRAIN` | $[0.0, 1.0]$ | Fortificaciones pesadas: $+1.0$ búnker/casamata, $+0.70$ trinchera, $+0.40$ urbano de piedra defensivo. |
| **Ch 28** | `ally_attack_power_norm` | `UNITS` | $[0.0, 1.0]$ | Poder de fuego ofensivo aliado (dados de combate normalizados). |
| **Ch 29** | `hazard_mines_and_wire` | `TERRAIN` | $[0.0, 1.0]$ | Peligros y obstáculos del terreno: $+1.0$ campos de minas, $+0.60$ alambradas de espino. |
| **Ch 30** | `ally_defense_power_norm` | `UNITS` | $[0.0, 1.0]$ | Capacidad defensiva de las escuadras aliadas (dados de defensa normalizados). |
| **Ch 31** | `enemy_defense_power_norm` | `UNITS` | $[0.0, 1.0]$ | Capacidad defensiva de las escuadras enemigas (dados de defensa normalizados). |
| **Ch 32** | `ally_doctrine_role` | `UNITS` | $[0.0, 1.0]$ | Codificación continua de rol aliado (`SPEARHEAD`=1.0, `FIRE_SUPPORT`=0.75, `RECON`=0.50, `SCREEN`=0.25). |
| **Ch 33** | `enemy_doctrine_role` | `UNITS` | $[0.0, 1.0]$ | Codificación continua de rol enemigo deducido (`SPEARHEAD`=1.0, `FIRE_SUPPORT`=0.75, `RECON`=0.50, `SCREEN`=0.25). |
| **Ch 34** | `ally_optimal_range_2d` | `UNITS` | $[0.0, 1.0]$ | Footprint 2D de alcance óptimo de combate aliado proyectado sobre el tablero. |
| **Ch 35** | `enemy_optimal_range_2d` | `UNITS` | $[0.0, 1.0]$ | Footprint 2D de alcance óptimo de combate enemigo proyectado sobre el tablero. |
| **Ch 36** | `turn_urgency_pressure` | `GLOBAL` | $[0.0, 1.5]$ | Presión temporal continua ($t/T$) y campo de urgencia radial amplificado hacia VPs no capturados. |
| **Ch 37** | `paralysis_exposure_risk` | `UNITS` | $[0.0, 1.0]$ | Mapa de calor de riesgo de parálisis: escuadras aliadas expuestas fuera de cobertura sin maniobra ni fuego. |
* **Entrada**: Tensor espacial sensorial $o_t \in \mathbb{R}^{B \times C \times H \times W}$ construido por `voec_sim` y adaptado por `agents/efficientzero_v2/core/observation.py` ($C \in \{32, 36, 37, 38\}$, agnóstico a la resolución espacial: $16\times 16$, $32\times 32$, $64\times 64$).
  * **Canales 13 y 14 (`vp_mask` y `vp_owner_relative`)**: Codificación de la ubicación y control de los Puntos de Victoria modulada por su valor intrínseco relativo ($v_{\text{rel}} = v_{\text{vp}} / 2.0$, asignando $1.0$ para 2 VP y $1.5$ para 3 VP clave; en el Canal 14, $+v_{\text{rel}}$ para control aliado y $-v_{\text{rel}}$ para enemigo).
  * **Canal 18 (`vp_distance_field`)**: Campo continuo euclidiano radial ponderado por el valor relativo de cada VP ($\max_{vp} \frac{v_{\text{rel}}}{1 + d_{\text{vp}}}$). Modulado dinámicamente por la presión temporal de la Tarea 2.3: si el bando no controla el VP, la pendiente se intensifica con $(1.0 + 0.5 \cdot \frac{t}{T})$, forzando convergencia espacial rápida hacia los objetivos decisivos antes de que transcurran los turnos.
  * **Canal 36 (`turn_urgency_pressure`)**: Difusión espacial continua de la presión temporal global $\tau = \frac{t}{T_{\text{max}}}$, amplificada un $+50\%$ en la proximidad de los VPs en disputa para alertar a la red sobre la ventana crítica de captura.
  * **Canal 37 (`paralysis_exposure_risk`)**: Mapa de calor que identifica en tiempo real las unidades aliadas situadas en terreno abierto (`cover < 0.35`) fuera del perímetro defensivo de los VPs, proyectando el riesgo de incurrir en la penalización acumulativa por parálisis.
* **Convoluciones con Máscara Hexagonal (`HexagonalMaskConv2d`)**: A diferencia de las convoluciones cartesianas $3\times 3$, anula estáticamente las dos esquinas diagonales que no comparten arista en la cuadrícula hexagonal axial $(q, r)$, eliminando la distorsión anisotrópica.
* **Bloques Residuales con Squeeze-and-Excitation (SE)**: Cada uno de los 4 bloques residuales (`48ch`) contiene 2 convoluciones espaciales $3\times 3$ más 2 convoluciones puntuales $1\times 1$ de cuello de botella SE (`48 -> 12 -> 48`).
* **Salida**: Estado latente abstracto inicial $s_0 \in \mathbb{R}^{B \times 48 \times H \times W}$.

### 2.2. Red de Dinámica Recurrente Weight-Tied ($g_\theta$ — 18 Capas Conv2D)
* **Entrada**: Estado latente $s_t \in \mathbb{R}^{B \times 48 \times H \times W}$ concatenado con el plano de acción expandido dinámicamente a la resolución actual $(B, 1, H, W)$.
* **Razonamiento Recurrente de Peso Compartido ($k$ pasos, Palma et al. 2025)**: El bloque `dynamics_state` (17 capas Conv2D) puede iterar $k = \text{dynamics\_recurrent\_steps}$ veces reutilizando exactamente los mismos pesos (0 parámetros adicionales). En el paso $i=0$ recibe la acción candidata; en los pasos $i=1 \dots k-1$ refina el estado latente concatenando un plano neutro de ceros para propagar cadenas causales multi-salto.
* **Escalado Min-Max Latente**: Para evitar que las activaciones exploten o se desvanezcan a lo largo del desenrollado recursivo, el estado latente resultante se normaliza en $[0, 1]$:
  $$s_{\text{norm}} = \frac{s - \min(s)}{\max(s) - \min(s) + \epsilon}$$
* **Cabeza 1 — Recompensa Inmediata (`reward_head`)**: `Conv1x1(48 -> 16) -> AdaptiveAvgPool2d(1) -> Linear(16 -> 64 -> 2K+1)`.

### 2.3. Tronco de Predicción y Preservación de Resolución Espacial ($f_\theta$)
* **Tronco (`prediction_trunk`)**: 2 bloques `ResidualBlockSE` operando a la **máxima capacidad latente de 48 canales** (`hidden_dim = 48`, con un total de 8 capas Conv2D de 48 canales y compuertas Squeeze-and-Excitation / ECA), seguidos de un bloque `SpatialAttentionBlock` (1 capa Conv2D $7\times 7$ sobre media y máximo por canal). No existe reducción prematura de canales a 8; la capacidad de 48 canales se mantiene estrictamente en todo el tronco.
* **Preservación de Topología Espacial (FCN vs Sectores 4x4)**:
  * **Cabezas Espaciales FCN Puras (`threat_map`, `final_ownership`)**: Operan directamente a resolución nativa $H \times W$ mediante convoluciones 2D locales (`Conv3x3(48 -> 16) -> GroupNorm -> SiLU -> Conv1x1(16 -> 1)`), produciendo mapas bidimensionales hexágono a hexágono sin colapso alguno.
  * **Cabezas Tácticas con Atención Espacial Sectorizada (`attrition`, `morale`, `objective_intent`, `multi_vp`)**: En lugar de Global Average Pooling puro ($1\times 1$), procesan el estado latente mediante `SpatialAttentionBlock(48, val_channels, (4, 4))`, reteniendo una matriz de $4 \times 4 = 16$ celdas espaciales con atención aprendida. Esto conserva la granularidad espacial de frentes, flancos y concentración de tropas antes del aplanado hacia sus respectivos clasificadores y regresores MLP.
* **Adaptación Espacial Bilineal (`_adapt_spatial`)**: Si el mapa de entrada tiene dimensiones distintas a $16\times 16$ (por ejemplo $32\times 32$ o $64\times 64$), aplica interpolación bilineal al tamaño canónico $16\times 16$ exclusivamente para las cabezas densas (`policy`, `value`), mientras que las cabezas FCN conservan la resolución $H \times W$.

### 2.4. Cabeza 11 — Proyector y Predictor de Consistencia Temporal SimSiam ($q_\theta$) y Estabilidad Anti-Colapso
Para evitar el colapso de representación dimensional (evitando que la dinámica recurrente aprenda constantes triviales), el módulo SimSiam (`consistency_projector` + `consistency_predictor`) incorpora dos salvaguardas estrictas:
1. **Stop-Gradient Dual en el Target**: Durante el entrenamiento (`EfficientZeroV2Trainer`), la representación objetivo $h_\theta(o_{t+k})$ se evalúa bajo `torch.no_grad()` y su proyección resultante se desacopla explícitamente mediante `.detach()` antes del cómputo de la pérdida de similitud del coseno. Los gradientes retropropagados por SimSiam fluyen exclusivamente a través de la predicción latente $p_\theta(q_\theta(s_k))$, sin contaminar ni desestabilizar las representaciones del tronco ni las cabezas de valor/recompensa.
2. **Normalización $\ell_2$ Unitaria**: Ambos vectores se normalizan estrictamente sobre la esfera unitaria ($\|z\|_2 = 1, \|p\|_2 = 1$) mediante `F.normalize(..., dim=-1)` antes del producto escalar:
$$\mathcal{L}_{\text{consistency}} = -\frac{1}{2} \left( \frac{p_\theta(q_\theta(s_k))}{\|p_\theta(q_\theta(s_k))\|_2} \cdot \text{stop\_grad}\left(\frac{q_\theta(h_\theta(o_{t+k}))}{\|q_\theta(h_\theta(o_{t+k}))\|_2}\right) \right)$$

### 2.5. Modulación Dinámica de Priors y Decaimiento Anti-Miopía (Tarea 2.8 [v2.5.26])
Para resolver el dilema identificado en la auditoría arquitectónica (donde un sesgo doctrinal estático del $+35\%$ acota artificialmente la exploración en el árbol de búsqueda MCTS e induce *"Objective Myopia"*), se introduce la modulación temporal gobernada por programa de decaimiento:

$$\beta_{\text{eff}}(a) = 1.0 + (\beta_{\text{raw}}(a) - 1.0) \cdot w_{\text{macro}}(t)$$

Donde la escala de modulación $w_{\text{macro}}(t)$ puede configurarse bajo tres regímenes:
1. **Decaimiento Cosinoidal Progresivo (Recomendado)**:
   $$w_{\text{macro}}(t) = w_{\min} + \frac{1}{2}(w_{\max} - w_{\min})\left(1 + \cos\left(\pi \frac{t}{T_{\text{decay}}}\right)\right)$$
   Proporciona guía heurística robusta ($w_{\max} = 1.0$) en fases iniciales cuando la política no conoce los objetivos, y decae suavemente hacia cero ($w_{\min} = 0.0$) permitiendo que la red neuronal descubra tácticas puras y sacrificios posicionales no convencionales.
2. **Decaimiento Lineal**:
   $$w_{\text{macro}}(t) = w_{\max} + (w_{\min} - w_{\max}) \cdot \min\left(1.0, \frac{t}{T_{\text{decay}}}\right)$$
3. **Ablación Científica A/B**:
   * **Variante A (Red Pura / Búsqueda Libre)**: $w_{\text{macro}} = 0.0$, donde los priors de la red alimentan MCTS al 100% sin sesgos heurísticos.
   * **Variante B (Doctrinal Shaped)**: $w_{\text{macro}} = 1.0$ estático para evaluar la ganancia o pérdida neta de ELO.

---

## 3. Catálogo Completo de las 11 Cabezas de Salida

La red neuronal produce simultáneamente **11 cabezas especializadas** (1 en dinámica, 1 de consistencia temporal y 9 en el tronco de predicción):

```mermaid
graph LR
    S["Estado Latente Atendido s\n[B, 48, H, W]"] --> ADAPT["_adapt_spatial\n[B, 48, 16, 16]"]
    S --> FCN["FCN 2D Nativa [B, 48, H, W]"]
    S --> S_ATTN["SpatialAttentionBlock (4x4)\n[B, val_ch, 4, 4]"]

    ADAPT --> H_POL["2. Policy Head\n[B, 32] Logits Priors"]
    ADAPT --> H_VAL["3. Value Head\n[B, 2K+1] Soporte"]

    FCN --> H_THREAT["5. Threat Map Head\n[B, 1, H, W] FCN 2D"]
    FCN --> H_OWNER["6. Final Ownership Head\n[B, 1, H, W] FCN 2D"]

    S_ATTN --> H_OBJ["4. Objective Head\n[B, 1] Escalar"]
    S_ATTN --> H_ATTR["7. Attrition Head\n[B, 2] Bajas A/E"]
    S_ATTN --> H_MORALE["8. Morale Head\n[B, 4] Estados Moral"]
    S_ATTN --> H_INTENT["9. Objective Intent Head\n[B, 8] Intencion"]
    S_ATTN --> H_MVP["10. Multi-VP Head\n[B, 4] Vector VPs"]
```

| # | Nombre de Cabeza | Módulo PyTorch | Dimensión de Salida | Topología Espacial / Función Táctica |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **Reward (`reward_logits`)** | `reward_head` | `[B, 2K+1]` | Distribución Two-Hot / HL-Gauss de la recompensa inmediata tras ejecutar $a_t$. |
| **2** | **Policy (`policy_logits`)** | `prediction_policy` | `[B, 32]` | Cuello de botella `Conv1x1(48->4)` $\to$ MLP prior sobre 32 ranuras legales en MCTS. |
| **3** | **Value (`value_logits`)** | `prediction_value` | `[B, 2K+1]` | Distribución Two-Hot / HL-Gauss del retorno descontado esperado desde $s_t$. |
| **4** | **Objective (`objective_logit`)** | `prediction_objective` | `[B, 1]` | `SpatialAttentionBlock(4x4)` $\to$ Estimador de progreso hacia la victoria por objetivos. |
| **5** | **Threat Map (`threat_map_logits`)** | `prediction_threat_map` | `[B, 1, H, W]` | **FCN 2D Nativa**: Mapa convolucional directo de riesgo de fuego y LOS enemiga inmediata. |
| **6** | **Final Ownership Map (`final_ownership_pred`)** | `prediction_final_ownership` | `[B, 1, H, W]` | **FCN 2D Nativa**: Predicción convolucional de posesión final del hexágono a $T$ (KataGo). |
| **7** | **Attrition (`attrition_pred`)** | `prediction_attrition` | `[B, 2]` | `SpatialAttentionBlock(4x4)` $\to$ Vector de bajas esperadas `[aliadas, enemigas]`. |
| **8** | **Morale (`morale_logits`)** | `prediction_morale` | `[B, 4]` | `SpatialAttentionBlock(4x4)` $\to$ Distribución de cohesión: `NORMAL`, `PINNED`, `SUPPRESSED`, `ROUTED`. |
| **9** | **Objective Intent (`objective_intent_logits`)** | `prediction_intent` | `[B, 8]` | `SpatialAttentionBlock(4x4)` $\to$ Clasificador de intención táctica (8 clases doctrinales). |
| **10** | **Multi-VP (`multi_vp_pred`)** | `prediction_multi_vp` | `[B, 4]` | `SpatialAttentionBlock(4x4)` $\to$ Vector `[control_ratio, contested_ratio, threat, time]`. |
| **11** | **Consistency (`latent_proj` / `pred`)** | `consistency_projector` | `[B, 128]` | Embedding SimSiam $\ell_2$-normalizado con stop-gradient dual para evitar colapso latente. |

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

### 4.3. Two-Hot Asimétrico con Warp Exponencial en Torno a Cero (Discriminación de Micro-Desgaste)
En wargames tácticos, las micro-ventajas de desgaste en las primeras escaramuzas (ej. forzar una retirada o causar una baja de 0.05 puntos de VP) caían en el mismo átomo central cero del soporte estándar $[-30, +30]$, generando gradientes nulos o ceguera táctica.

Para solucionarlo, [`agents/efficientzero_v2/core/support.py`](file:///c:/repos/python/assault/agents/efficientzero_v2/core/support.py) implementa el soporte asimétrico no lineal con `asym_zero_boost=True` y $\alpha = 0.75$:

$$\text{warp}(x) = \text{sign}(x) \cdot |x|^{\alpha}, \quad \alpha = 0.75$$
$$\text{unwarp}(y) = \text{sign}(y) \cdot |y|^{1/\alpha}$$

* **Efecto de Resolución**: Un valor pequeño de $x = 0.04$ se proyecta a $\approx 0.089$, expandiendo su representación a lo largo de los átomos discretos adyacentes sin modificar los 61 átomos totales ni romper la compatibilidad con checkpoints existentes.
* **Inversión Exacta**: Durante la inferencia escalar en MCTS (`support_to_scalar`), el valor esperado se des-transforma simétricamente mediante $1/\alpha \approx 1.3333$, recuperando la métrica continua real.

### 4.4. Régimen Dual de Inferencia y Pérdidas: Soporte Discreto vs. Modo Escalar Directo (MSE)

El motor de EfficientZero V2 (`EfficientZeroV2Trainer`) soporta dos regímenes matemáticos para las cabezas de Valor y Recompensa, gobernados por el parámetro `support_size`:

1. **Régimen Categórico Two-Hot (`support_size > 0`, ej. 30 $\to$ 61 átomos)**:
   - Las cabezas proyectan logits a una distribución discreta de átomos.
   - La función de coste es **Cross-Entropy Categórica** contra la interpolación two-hot:
     $$\mathcal{L}_{\text{val}} = -\sum_{i=-K}^{K} p_i^* \ln(p_i)$$
   - Los valores numéricos de pérdida se expresan en **nats** (rango típico: $0.5$ a $4.11 = \ln(61)$).

2. **Régimen Escalar Continuo (`support_size == 0`)**:
   - Las cabezas de valor y recompensa finalizan en una única neurona lineal escalar directa (`Linear(64, 1)`).
   - La función de coste es **Mean Squared Error (MSE)** directo:
     $$\mathcal{L}_{\text{val}} = \frac{1}{B} \sum_{b=1}^{B} (v_b - v_b^*)^2, \quad \mathcal{L}_{\text{rew}} = \frac{1}{B} \sum_{b=1}^{B} (r_b - r_b^*)^2$$
   - **Interpretación Dimensional**: Las pérdidas reportadas son magnitudes cuadráticas de las unidades del juego. Para interpretarlas en la escala de recompensa real, se debe extraer la raíz del error cuadrático medio:
     $$\text{RMSE}_{\text{reward}} = \sqrt{\mathcal{L}_{\text{rew}}}, \quad \text{RMSE}_{\text{value}} = \sqrt{\mathcal{L}_{\text{val}}}$$
   - En fases con recompensas de captura elevadas (ej. $+16.14$ por VP), un $\mathcal{L}_{\text{rew}} \approx 29.7$ representa un $\text{RMSE} \approx 5.45$ puntos, perfectamente acorde a la dispersión temporal y varianza estocástica de los combates.

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
        SCALE["Escala de Modulacion Dinamica:\n\beta_macro in [0.0, 1.0]"]
        PRIORS["Modulación Dinámica de Priors:\nP_mod(a) = P(a) * [1 + \beta_macro * (Boost(Postura, Rol, a) - 1)]"]
        TREE["Árbol de Búsqueda MCTS (512 simulaciones / 6 unrolls)"]
        
        SCALE --> PRIORS
        PRIORS --> TREE
    end

    ROLES ==> PRIORS
```

* **Desacoplamiento Operativo**: El Nivel 1 no decide cada paso físico de una unidad; define la doctrina.
* **Modulación Dinámica de Priors ($\beta_{\text{macro}}$)**: Durante el paso raíz del MCTS, las acciones tácticas que coinciden con el rol de la unidad y la postura del equipo reciben un bono modulado por el factor dinámico $\beta_{\text{macro}} \in [0.0, 1.0]$ (`macro_modulation_scale`). Con $\beta_{\text{macro}} = 1.0$, el bono doctrinal estándar es de $+35\%$ ($1.35\times$), guiando la búsqueda de Monte Carlo hacia rutas coherentes con el plan general. Con $\beta_{\text{macro}} = 0.0$, el sesgo doctrinal se desactiva al 100%, dejando los priors puros de la red neuronal intactos para ablación libre de sesgos.

### 5.1. Sintonización del Macro-Planner y Modulación de Priors de Asalto

Durante la fase de juego táctico competitivo frente a políticas estocásticas y baselines, se detectaron y corrigieron tres aspectos clave del planificador macro:
1. **Parseo Canónico de Acciones**: El motor serializa las acciones de movimiento con delimitadores de dos puntos (`MOVE:<unit_id>:<q>:<r>`), mientras que ciertas variantes emplean tuplas por coma. El parser ahora desacopla de forma robusta ambos esquemas y extrae de forma inequívoca las coordenadas de destino axiales $(q, r)$.
2. **Prior de Asalto y Detección de Captura Inmediata**: Si una acción legal sitúa a la unidad sobre un hexágono de punto de victoria neutral o enemigo (`dest_qr in enemy_vps`), el Macro Planner inyecta un factor de amplificación de prior agresivo ($1.5 \times \text{assault\_boost}$), priorizando la exploración de ramas de captura en la raíz del árbol MCTS.
3. **Dinámica de Roles en `ASSAULT_VP`**: Bajo la postura `ASSAULT_VP`, las unidades de infantería avanzada a distancia operativa ($\le 8$ hexágonos del objetivo) son asignadas doctrinariamente a `ROLE_SPEARHEAD`, impidiendo que queden indebidamente confinadas a `ROLE_OBJECTIVE_DEFENDER` en los VPs de despliegue inicial.

### 5.2. Gradiente Continuo de Recompensa y Urgencia Terminal

Para superar la aversión al riesgo excesiva donde las penalizaciones por fuego de oportunidad paralizaban el avance hacia los objetivos lejanos:
1. **Eliminación del Corte Artificial de Distancia (`opportunity_near_vp_max_dist`)**: Anteriormente limitado a $2$ ó $4$ hexágonos, se extendió a un radio efectivo de mapa completo ($12.0$ hexágonos por defecto). Esto garantiza un gradiente continuo de recompensa de aproximación (`team_progress_delta` y `objective_progress_delta`) desde el primer turno de juego.
2. **Atenuación del Factor de Exposición al Movimiento**: El factor de penalización preventiva por exposición a fuego de reacción durante el movimiento se redujo de $1.0$ a $0.6$, permitiendo que los beneficios proyectados de avance compensen razonablemente el riesgo táctico medido.
3. **Penalización por Derrota Terminal (`terminal_loss_penalty` = 1.5, `terminal_scale` = 1.5)**: La derrota por llegar al límite de turnos sin controlar la mayoría de VPs acarrea un coste terminal que supera con creces cualquier daño individual acumulado en la aproximación. Esta calibración matemática fuerza al MCTS a asumir riesgos calculados para evitar la derrota por tiempo.

### 5.3. Modulación Dinámica Continua y Desacoplamiento Doctrinal ($\beta_{\text{macro}}$) [Consolidado v2.5.27 / Tarea 2.8]

Para solventar el riesgo de sesgo heurístico excesivo (*Objective Myopia*) que pudiese acotar la exploración en etapas tempranas de autojuego o impedir maniobras contraintuitivas pero tácticamente superiores, se implementó el parámetro canónico `macro_modulation_scale` ($\beta_{\text{macro}} \ge 0.0$):

$$\text{boost}_{\text{eff}}(a) = 1.0 + (\text{boost}_{\text{doctrinal}}(a) - 1.0) \cdot \beta_{\text{macro}}$$
$$P_{\text{mod}}(a) = \frac{P_{\text{net}}(a) \cdot \text{boost}_{\text{eff}}(a)}{\sum_{b} P_{\text{net}}(b) \cdot \text{boost}_{\text{eff}}(b)}$$

Este desacoplamiento continuo habilita tres regímenes operativos gobernados desde la configuración YAML de autojuego (`cfg.selfplay.macro_modulation_scale`):
1. **Régimen de Red Pura / Búsqueda Libre ($\beta_{\text{macro}} = 0.0$)**:
   - $\text{boost}_{\text{eff}}(a) = 1.0 \implies P_{\text{mod}}(a) = P_{\text{net}}(a)$.
   - Los priors evaluados por la red neuronal se transmiten con 100% de pureza matemática al árbol MCTS. Esencial para la Tarea 2.8 (estudios de ablación A/B) para auditar el rendimiento táctico sin muletas heurísticas.
2. **Régimen de Calentamiento / Annealing Progresivo ($\beta_{\text{macro}}(t) = \beta_0 \cdot \gamma^t$ o $0.0 \to 1.0$)**:
   - Permite arrancar el entrenamiento con exploración libre pura ($\beta = 0.0$) y reforzar la disciplina doctrinal a medida que el valor converge, o viceversa (guiar el arranque y retirar el sesgo conforme la red madura).
3. **Régimen Doctrinal Completo ($\beta_{\text{macro}} = 1.0$)**:
   - Aplica el $+35\%$ canónico en roles de vanguardia y fuego de apoyo y $+50\%$ en captura directa de VPs. Verificado formalmente en `agents/efficientzero_v2/tests/test_heads_improvements.py`.

---

### 5.4. Perfilado Topográfico 5D e Inyección de Priors IPB Turno 0 (Tarea 4.3 - v2.5.28)

Complementando los roles doctrinales y la modulación $\beta_{\text{macro}}$, el **Nivel 1 (Planificador Macro)** incorpora el análisis topográfico del terreno en **Turno 0** (*Intelligence Preparation of the Battlefield - IPB*), desarrollado en `assault_model/map/topography_analyzer.py` e integrado en `agents/efficientzero_v2/core/macro_planner.py`.

#### 5.4.1 Vector 5D por Hexágono (`Hex5DProfile`)
Para cada celda $(q, r)$ del escenario, se computa de forma estática determinista un vector de 5 dimensiones:
1. **Cover Rating ($c \in [0.0, 1.0]$)**: Resistencia balística y ocultación del hexágono (edificios $\ge 0.85$, bosques densos $\ge 0.70$, crestas $\ge 0.40$, despejado $\le 0.15$).
2. **Elevation Dominance ($e \in [0.0, 1.0]$)**: Dominancia orográfica sobre el entorno circundante (crestas y colinas $\ge 0.85$).
3. **LOS Exposure ($l_{\text{exp}} \in [0.0, 1.0]$)**: Vulnerabilidad a líneas de visión y fuego cruzado en terreno abierto circundante.
4. **Chokepoint Bottleneck ($\text{chk} \in [0.0, 1.0]$)**: Constricción de maniobra debida a hexágonos adyacentes infranqueables (agua, relieve escarpado).
5. **VP Proximity Utility ($u_{\text{vp}} \in [0.0, 1.0]$)**: Proximidad hiperbólica hacia los Puntos de Victoria: $u_{\text{vp}} = \frac{1}{1 + \min_v d((q,r), v)}$.

#### 5.4.2 Clasificación Táctica y Sectores del Terreno
A partir del perfil 5D, los hexágonos se clasifican deterministamente en 6 categorías operacionales:
* **`KEY_TERRAIN`**: Hexágonos que contienen Puntos de Victoria (VPs).
* **`BASE_OF_FIRE`**: Alturas dominantes ($e \ge 0.75$) o posiciones de cobertura pesada con campo de tiro inmediato sobre los VPs ($1 \le d \le 6$).
* **`CHOKEPOINT`**: Pasos obligados y cuellos de botella con constricción severa ($\text{chk} \ge 0.60$).
* **`KILLZONE`**: Terreno despejado y abierto con alta exposición ($c < 0.35, l_{\text{exp}} \ge 0.60$) a corta distancia de objetivos ($d \le 4$).
* **`DEFILADE_CORRIDOR`**: Rutas de aproximación cubiertas por vegetación densa o relieve ($c \ge 0.65$ o $c \ge 0.50$ con baja exposición) que ocultan el avance hacia el objetivo.
* **`MANEUVER_TRANSIT`**: Espacio estándar de maniobra táctica.

#### 5.4.3 Reglas de Modulación de Priors en MCTS
En el cálculo de `compute_action_boost` del Macro Planner:
* **Avance en Desenfilada**: $+25\%$ de refuerzo cuando la unidad avanza acortando distancia al VP objetivo a través de `DEFILADE_CORRIDOR`.
* **Disuasión en Killzones**: Penalización severa ($0.55\times$ para roles generales, $0.65\times$ para unidades `SPEARHEAD` que realizan maniobras laterales sin cerrar distancia) al internarse en `KILLZONE` abierta expuesta a fuego cruzado.
* **Base de Fuego**: $+30\%$ de refuerzo para unidades de apoyo (`ROLE_FIRE_SUPPORT`) que alcanzan hexágonos designados como `BASE_OF_FIRE`.
* **Fijación de Chokepoints**: $+20\%$ de refuerzo para roles de defensa y pantalla (`ROLE_FLANK_SCREEN`, `ROLE_OBJECTIVE_DEFENDER`) que aseguran embudos tácticos.
* **Ablación Pura**: El factor continuo $\beta_{\text{macro}} = \text{modulation\_scale}$ neutraliza exactamente todos los boosts a $1.0$ cuando se evalúa en régimen de red puramente neural.

#### 5.4.4 Eficiencia en Entrenamiento y Telemetría MLOps
1. **Coste Turno 0 Nulo (0 ms en pasos posteriores)**: El análisis se ejecuta una única vez al inicio del episodio y se conserva en caché estática en memoria (`_topography_cache`), con cero sobrecarga en los rollouts subsiguientes.
2. **Poda de Ramas Suicidas**: Al penalizar la exploración en killzones abiertas, el árbol MCTS no desperdicia simulaciones en movimientos estériles o aniquilaciones tempranas, concentrando los rollouts en maniobras tácticas viables.
3. **Visibilidad en Replay (:8778)**: Capa interactiva `🛡️ IPB Topography` con polígonos coloreados, etiquetas tácticas vectoriales en cada hexágono y tooltip de inspección sectorial con desglose 5D.


---

## 6. Mitigación de Conflicto de Gradientes: PCGrad

Al entrenar simultáneamente la política, el valor, el objetivo y las cabezas tácticas auxiliares, los gradientes pueden entrar en conflicto destructivo:
$$\langle g_{\text{task}_i}, g_{\text{task}_j} \rangle < 0$$

Para resolverlo, el balanceador de pérdidas utiliza **PCGrad (*Projecting Conflicting Gradients*)**:
Si dos gradientes apuntan en direcciones opuestas, el gradiente de la tarea secundaria se proyecta sobre el hiperplano ortogonal al de la tarea primaria:
$$g_i = g_i - \frac{g_i \cdot g_j}{\|g_j\|^2} g_j$$
Esto garantiza matemáticamente que ninguna cabeza táctica auxiliar degrade la calidad de la política o el valor del modelo.

### 6.1 Implementación Vectorizada 1D en GPU (Cero Bucle Python) [Consolidado v2.5.25]
Para eliminar la sobrecarga de lanzamiento de kernels CUDA durante las actualizaciones de red, la función `pcgrad_backward` aplana los gradientes por tarea en vectores 1D contiguos en VRAM (`task_flat_grads`). La proyección ortogonal se calcula mediante operaciones vectorizadas BLAS puras en GPU (`torch.dot`), eliminando más de 110.000 llamadas secuenciales a micro-kernels por ciclo y reduciendo sustancialmente el cuello de botella del driver en la GPU.

---

## 7. Esquema de Inicialización de Pesos y Estabilidad de Gradientes

### 7.1. Estado Actual: Inicialización por Defecto de PyTorch (Kaiming Uniform)
En la implementación de [`agents/efficientzero_v2/core/network_base.py`](file:///c:/repos/python/assault/agents/efficientzero_v2/core/network_base.py) y [`network.py`](file:///c:/repos/python/assault/agents/efficientzero_v2/core/network.py), los pesos de los módulos siguen la inicialización por defecto del framework PyTorch al no definirse un hook explícito `_init_weights()`:
1. **Convoluciones 2D (`nn.Conv2d` y `HexagonalMaskConv2d`)**:
   - Inicialización **Kaiming Uniform** (He et al., 2015):
     $$\mathcal{U}(-\text{bound}, \text{bound}), \quad \text{bound} = \sqrt{\frac{6}{(1 + a^2) \cdot \text{fan\_in}}}$$
     donde PyTorch establece $a = \sqrt{5}$ por defecto, reduciendo la cota a $\text{bound} = \frac{1}{\sqrt{\text{fan\_in}}}$.
   - En las capas de convolución hexagonal, la máscara estática anula las esquinas tras inicializar.
2. **Capas Lineales y Proyecciones Densas (`nn.Linear`)**:
   - Inicialización **Kaiming Uniform** con $a=\sqrt{5}$ tanto en pesos $W$ como en sesgos $b \sim \mathcal{U}(-1/\sqrt{\text{fan\_in}}, 1/\sqrt{\text{fan\_in}})$.
   - Aplica a todas las cabezas del modelo: `prediction_policy`, `prediction_value`, `reward_head` y cabezas auxiliares tácticas.
3. **Normalización (`nn.GroupNorm` y `nn.LayerNorm`)**:
   - Escala $\gamma = 1.0$, sesgo $\beta = 0.0$.
4. **Embeddings Categóricos (`nn.Embedding`)**:
   - Inicialización normal estándar $\mathcal{N}(0, 1)$.

### 7.2. Limitaciones de Kaiming Uniform en Aprendizaje por Refuerzo (RL)
Si bien Kaiming Uniform es idónea para tareas de visión supervisada, en arquitecturas de planificación de árbol como EfficientZero V2 introduce fricciones en el paso inicial $t=0$:
* **Pérdida de Entropía Inicial en la Política**: Pesos aleatorios con varianza no mitigada en la última capa lineal generan logits dispares, sesgando estocásticamente la distribución prior de la política antes de acumular experiencia de autojuego.
* **Varianza Prematura en la Estimación de Valor y Recompensa**: Provoca que la red proyecte estimaciones de retorno distantes de cero en las primeras iteraciones MCTS, desestabilizando el soporte discreto Two-Hot / HL-Gauss antes del calentamiento (*warm-up*).
* **Degeneración del Flujo Residual Inicial**: En arquitecturas profundas (4 bloques en representación + 4 en dinámica + 2 en predicción), la acumulación de varianza a través de la rama residual dificulta que la red aprenda inicialmente la función identidad.

### 7.3. Especificación Canónica Propuesta: Inicialización Optimizada para RL
Para optimizar la estabilidad numérica y el muestreo inicial en MCTS, se formaliza la especificación canónica (*RL-Optimal Initialization Scheme*):

| Componente / Módulo | Técnica de Inicialización | Parámetros Matemáticos | Justificación Táctica / RL |
| :--- | :--- | :--- | :--- |
| **Cabeza de Política (`prediction_policy`)** | **Ortogonal (*Orthogonal Init*)** | `gain = 0.01`, `bias = 0.0` | **Máxima entropía inicial**: Los logits iniciales arrancan prácticamente en $0$, garantizando una distribución prior uniforme $\mathcal{U}(1/32)$ en la raíz del árbol MCTS, evitando exploraciones prematuramente sesgadas. |
| **Cabezas de Valor y Recompensa (`value`, `reward`)** | **Ortogonal (*Orthogonal Init*)** | `gain = 1.0` (o `0.1`), `bias = 0.0` | **Predicción centrada en cero**: Mitiga picos de gradiente en TD-learning y estabiliza el soporte discreto Two-Hot durante los primeros ciclos de autojuego. |
| **Cabezas Auxiliares Tácticas (`threat`, `morale`, `attrition`, etc.)** | **Ortogonal (*Orthogonal Init*)** | `gain = 1.0`, `bias = 0.0` | Gradientes iniciales estables y balanceados sin sobrecargar el proyector ortogonal PCGrad. |
| **Tronco Convolucional y Bloques Residuales** | **Kaiming Normal (He et al.)** | `mode='fan_in'`, `nonlinearity='silu'` | Preserva la varianza de las activaciones a través de las funciones no lineales SiLU en la cuadrícula hexagonal. |
| **Segunda Normalización Residual (`gn2` / Fixup)** | **Zero-Init / Fixup Initialization** | $\gamma = 0.0$ (`weight = 0.0`), $\beta = 0.0$ (`bias = 0.0`) | **Mapeo de Identidad Puro**: Al inicio, $x + f(x) = x + 0 = x$. Cada bloque residual comienza como una identidad exacta, permitiendo propagación directa de gradientes sin degradación ni sobrecalentamiento. |
| **Bloques de Atención SE / ECA** | **Pytorch Default / Cero en Salida** | $\gamma_{\text{final}} = 0.0$ | Permite que los canales arranquen con peso neutro ($1.0$ post-sigmoide o identidad) hasta que las representaciones espaciales converjan. |

### 7.4. Fundamentos Científicos y Literatura Académica de Referencia

Este esquema no responde a heurísticas empíricas informales, sino a conclusiones formales de la literatura reciente en Deep Reinforcement Learning y Model-Based RL:

1. **Inicialización Ortogonal de Política ($\text{gain}=0.01$) y Valor ($\text{gain}=1.0$)**:
   - **Andrychowicz et al. (Google Brain, ICLR 2021)**: *“What Matters In On-Policy Reinforcement Learning? A Large-Scale Empirical Study”*. Tras analizar más de 250.000 entrenamientos y 50+ decisiones de diseño, demuestran que la inicialización ortogonal con factor reducido ($\text{gain}=0.01$) en la capa final de la política es una de las 3 optimizaciones más determinantes para la estabilidad del entrenamiento, previniendo el colapso temprano de entropía.
   - **Engstrom, Ilyas et al. (MIT, ICLR 2020)**: *“Implementation Matters in Deep RL: A Case Study on PPO and TRPO”*. Revelan que las diferencias prácticas de rendimiento entre implementaciones canónicas (OpenAI Baselines) y librerías estándar provienen principalmente de la inicialización ortogonal con sesgo cero frente al Kaiming Uniform por defecto.
   - **Estándar en frameworks**: Adoptado canónicamente en las suites de referencia CleanRL, Stable-Baselines3 y OpenAI Gym.

2. **Zero-Init / Fixup en Normalización Residual ($\gamma = 0.0$)**:
   - **Goyal et al. (Facebook AI Research / FAIR, 2017)**: *“Accurate, Large Minibatch SGD: Training ImageNet in 1 Hour”*. Introducen la técnica de inicializar a cero la última capa de normalización de cada bloque residual ($\gamma = 0$), garantizando que al inicio de la optimización $y = x + F(x) = x$, haciendo que la red actúe como una identidad pura y eliminando la inestabilidad de gradiente en etapas tempranas.
   - **Zhang, Dauphin & Ma (ICLR 2019)**: *“Fixup Initialization: Residual Learning Without Normalization”*. Formalizan la teoría de la acumulación de varianza residual $\mathcal{O}(L)$ y demuestran que amortiguar la rama residual a cero en $t=0$ elimina la necesidad de *warm-up* agresivo en optimizadores basados en AdamW.
   - **Wu (2019–2020)**: *“Accelerating Self-Play Learning in Go”* (KataGo). Aplica Zero-Init en el tronco de bloques residuales para wargames combinatorios con MCTS, evitando que la red emita evaluaciones descalibradas durante las primeras simulaciones en árbol.

3. **Logits Centrados en Cero para Distribuciones Discretas de Valor (Two-Hot / HL-Gauss)**:
   - **Farebrother et al. (Google DeepMind, 2024)**: *“Stop Regressing: Training Value Functions via Classification for Scalable Deep RL”*. Demuestran que en parametrizaciones categóricas de valor (HL-Gauss y Two-Hot), los pesos aleatorios con dispersión estándar provocan predicciones multimodales espurias en los extremos del soporte al paso inicial. La inicialización ortogonal acotada con sesgo cero garantiza una distribución suave y simétrica en torno a cero en el inicio del autojuego.
   - **Ye et al. (2021)**: *“Mastering Atari with Discrete World Models”* (EfficientZero) & **Hafner et al. (DeepMind, 2023)**: *“Mastering Diverse Domains through World Models”* (DreamerV3). Establecen la necesidad de estabilizar la recurrencia dinámica $g_\theta(s, a)$ mediante representaciones acotadas para evitar que el escalado min-max latente diverja en los primeros ciclos de desenrollado temporal.

---



---

## 8. Modernización y Eficiencia Arquitectónica (Auditoría Forense ONNX / Netron) [Consolidado v2.5.0]

A raíz de la auditoría de topología visual exportada a ONNX e inspeccionada en Netron, se formalizó e integró una profunda reingeniería de la red para maximizar el ratio ELO por parámetro y la velocidad de inferencia recursiva en MCTS:

### 8.1. CoordConv Hexagonal (Inyección de Coordenadas Espaciales $38 \to 40$ Canales)
* **Diagnóstico**: Las capas convolucionales estándar son invariantes a la traslación espacial. Sin embargo, en un wargame táctico sobre rejilla hexagonal, la **posición absoluta** (bordes amigos de retirada, chokepoints urbanos fijos, ubicaciones cardinales de VPs) es un factor crítico de decisión.
* **Formulación**: Inyección explícita de 2 canales de coordenadas cartesianas continuas normalizadas $X, Y \in [-1, 1]$ (además de coordenadas axiales relativas):
  $$\text{Coord}_X(x, y) = \frac{2x}{W - 1} - 1, \quad \text{Coord}_Y(x, y) = \frac{2y}{H - 1} - 1$$
* **Impacto**: El tensor de entrada pasa de $38 \times 16 \times 16$ a $40 \times 16 \times 16$ con un coste computacional prácticamente despreciable, permitiendo a la red aprender distancias absolutas a los bordes y a los hexágonos de victoria sin depender de filtros convolucionales dilatados redundantes.

### 8.2. Rediseño No Destructivo de la Policy Head (Cuello de Botella Convolucional vs. GAP Puro)
* **Diagnóstico Crítico**: La arquitectura legacy utilizaba un aplanado masivo `Flatten(3072) -> Linear(3072, 32)` en la cabeza de política, absorbiendo más del $65\%$ de los parámetros totales de la cabeza y provocando lentitud en inferencia.
* **Peligro de Degeneración Táctica (Por qué evitar Global Average Pooling puro)**:
  > [!CAUTION]
  > El uso de *Global Average Pooling (GAP)* puro (`torch.mean(x, dim=[2,3])`) promedia todo el mapa $16\times 16$ a un único vector latente unidimensional. En un wargame táctico, **GAP destruye por completo la información espacial de qué unidad está en qué hexágono y hacia dónde debe moverse**, provocando amnesia posicional inmediata.
* **Solución Canónica Implementada**: Cuello de botella convolucional preservador de topología:
  $$\mathbf{Z}_{\text{policy}} = \text{Conv1x1}(48 \to 4) \longrightarrow \text{Flatten}(1024) \longrightarrow \text{Linear}(1024, 64) \longrightarrow \text{SiLU} \longrightarrow \text{Linear}(64, 32)$$
* **Resultado**: Reducción drástica del **$67\%$ de los parámetros** de la cabeza de política sin destruir la resolución espacial de las unidades en el mapa.

### 8.3. Atención por Canales Eficiente: Bloques ECA (Efficient Channel Attention 1D)
* **Diagnóstico**: En la red dinámica recurrente $g_\theta$ (que se evalúa cientos de miles de veces en cada rollout de MCTS), los bloques tradicionales *Squeeze-and-Excitation (SE)* aplican dos capas lineales completas con reducción dimensional, introduciendo cuello de botella en CPU/GPU.
* **Implementación ECA (Wang et al., 2020)**: Sustitución del MLP por una convolución 1D rápida entre canales con kernel adaptativo no lineal $k$:
  $$k = \psi(C) = \left| \frac{\log_2(C)}{\gamma} + \frac{b}{\gamma} \right|_{\text{odd}}$$
  con $\gamma=2, b=1$. Para $C=48$ canales latentes, $k=3$.
* **Ventaja**: Captura interacciones locales directas entre canales tácticos (blindaje, moral, línea de visión, terreno) con solo 3 parámetros aprendibles por bloque residual, acelerando el paso dinámico en MCTS.

### 8.4. Gated Residual Blocks (GLU) y Preservación de SimSiam
* **Compuertas GLU**: Inclusión de compuertas lineales (*Gated Linear Units*) en bloques residuales para regular dinámicamente el paso de activación y filtrar el ruido en zonas inactivas del tablero.
* **Preservación SimSiam con Stop-Gradient**: Se mantiene la formulación de proyección y predicción SimSiam con *stop-gradient* como estándar innegociable de auto-supervisión temporal por su probada estabilidad frente a colapso de representación y compatibilidad con el balanceo adaptativo multiobjetivo **PCGrad**.

---

## 9. Paquete de Optimización de Inferencia y MCTS [Consolidado v2.5.3]

Para reducir la duración de las campañas de entrenamiento de $>10$ horas a $<3.5$ horas con cero pérdida de fidelidad táctica ni matemática, se desarrollaron dos componentes de aceleración de bajo nivel:

### 9.1. Inferencia Estática Compilada (`torch.compile` con Inductor)
* **Compilación Ahead-of-Time / JIT**: Las redes de representación $h_\theta$, dinámica $g_\theta$ y predicción $f_\theta$ se encapsulan mediante `torch.compile(model, mode='reduce-overhead')` utilizando el backend TorchInductor.
* **Warm-up Seguro y Fallback Dinámico**: En entornos Windows o hardware sin compilador C++ compatible, el sistema ejecuta una ronda de calibración sintética (*warm-up*) de 3 pases; si se detecta cualquier incompatibilidad de runtime, conmuta automáticamente a modo PyTorch nativo sin interrumpir la simulación.

### 9.2. Precomputación Vectorizada de Raíz PUCT MCTS
* **Cálculo Fuera del Bucle Caliente**: En cada decisión táctica, la raíz del árbol MCTS contiene un conjunto de acciones legales fijas. Las componentes invariantes del algoritmo PUCT (priors normalizados, máscaras estáticas de legalidad, factores de exploración iniciales):
  $$U(s, a) = c_{\text{puct}} \cdot P(s, a) \cdot \frac{\sqrt{\sum_b N(s, b)}}{1 + N(s, a)}$$
  se precomputan de forma vectorizada con NumPy/PyTorch antes de iniciar las $N_{\text{sim}}$ simulaciones de MCTS, eliminando más de **$16,384$ operaciones redundantes por paso de juego**.

---

## 10. Inicialización Canónica de Capas Especializada en Reinforcement Learning [Consolidado v2.5.5]

En aprendizaje por refuerzo profundo sobre espacios de acción discretos y rollouts estocásticos MCTS, la inicialización estándar de redes neuronales (e.g. He Uniform / PyTorch default) provoca una degradación crítica en los primeros pasos de autojuego:
1. **Colapso Temprano de la Política**: Salidas lineales no calibradas imponen sesgos arbitrarios sobre ciertas acciones antes de recibir datos, reduciendo drásticamente la entropía y explorando únicamente un subconjunto ínfimo del árbol táctico.
2. **Deriva de Representación Residual**: En torres convolucionales profundas de representación y dinámica, la acumulación de ruido residual al paso 0 perturba la extracción de características antes de que los gradientes converjan.

Para resolver de raíz estas patologías, se implementó la función canónica `apply_canonical_rl_init(model)` y el método `apply_canonical_initialization()` en [`EfficientZeroV2BaseNetwork`](../agents/efficientzero_v2/core/network_base.py) y [`EfficientZeroV2Network`](../agents/efficientzero_v2/core/network.py), articulando cuatro garantías matemáticas:

### 10.1. Política Ortogonal con Ganancia Mínima ($\text{gain}=0.01, \text{bias}=0.0$)
* **Fundamento Matemático**: Basado en Andrychowicz et al. (2021) y Schulman et al. (2017). Para la última capa lineal de la cabeza de política (`prediction_policy`), los pesos se inicializan con una matriz ortogonal de escala minúscula:
  $$W_{\text{policy}} \sim \text{Orthogonal}(\text{gain} = 0.01), \quad b_{\text{policy}} = 0$$
* **Impacto en Entropía**: Los logits iniciales $z_a \approx 0$ para todas las acciones $a \in \mathcal{A}$. Tras la normalización softmax, la distribución inicial de probabilidades $\pi(a \mid s)$ es prácticamente uniforme:
  $$\pi(a \mid s) \approx \frac{1}{|\mathcal{A}|} \implies H(\pi) \approx \log(|\mathcal{A}|) = \log(32) \approx 3.4657 \text{ nats}$$
* **Resultado Verificado**: Se comprobó experimentalmente que la discrepancia entre la entropía inicial y el máximo teórico es menor a $0.02$ nats, garantizando máxima exploración estocástica uniforme al inicio del autojuego.

### 10.2. Cabezas de Valor, Recompensa y Auxiliares Ortogonales ($\text{gain}=1.0, \text{bias}=0.0$)
* **Estabilidad de Varianza**: Las salidas lineales de `prediction_value`, `dynamics_reward`, `consistency_projection` y las cabezas auxiliares tácticas (`threat_map`, `morale`, `attrition`, `final_ownership`) se inicializan con matrices ortogonales de ganancia unitaria:
  $$W_{\text{val/rew}} \sim \text{Orthogonal}(\text{gain} = 1.0), \quad b = 0$$
* **Ventaja**: Preserva exactamente la norma Euclidiana de las características latentes proyectadas hacia los átomos Two-Hot, impidiendo saturación prematura o gradientes desvanecidos en el cálculo de pérdidas de Bellman.

### 10.3. Kaiming Normal (He Normal) en Convoluciones SiLU y Capas Ocultas
* **Formulación**: Para todas las convoluciones `HexagonalMaskConv2d`, `Conv2d`, `Conv1d` y capas lineales intermedias con activación no lineal SiLU/ReLU:
  $$W \sim \mathcal{N}\left(0, \; \sigma^2 = \frac{2}{\text{fan\_out}}\right), \quad b = 0$$
* **Ventaja**: El modo `fan_out` garantiza que la varianza de las activaciones se conserve constante a lo largo de las múltiples capas residuales hacia adelante, eliminando oscilaciones numéricas en mapas de cualquier dimensión.

### 10.4. Zero-Init ResNet / Fixup en la Segunda Normalización Residual ($\gamma = 0, \beta = 0$)
* **Fundamento Matemático (Goyal et al., 2017; Zhang et al., 2019 Fixup)**: En cada bloque residual `ResidualConvBlock` y `ResidualMLPBlock`, la segunda capa de normalización (`gn2` en convolución, `ln2` en MLP) se inicializa con peso y sesgo idénticamente nulos:
  $$\gamma_{\text{norm2}} = 0, \quad \beta_{\text{norm2}} = 0$$
* **Función Identidad Pura al Paso 0**:
  Dado un bloque residual $y = x + F(x)$, donde $F(x) = \text{Attn}(\text{Norm}_2(\text{Conv}_2(\dots)))$:
  $$\text{Norm}_2(\cdot) = \gamma \cdot \hat{z} + \beta = 0 \cdot \hat{z} + 0 = 0 \implies F(x) = 0 \implies y = x + 0 = x$$
* **Impacto**: Al inicio del entrenamiento ($step=0$), toda la torre residual opera como una función identidad perfecta. Esto permite que el gradiente fluya sin obstáculos desde las cabezas de predicción hasta la capa de entrada $\frac{\partial (x + F(x))}{\partial x} = I + 0 = I$, permitiendo entrenar arquitecturas profundas sin explosión ni divergencia de gradientes.

### 10.5. Batería de Validación
Verificado al 100% en la suite de pruebas unitarias dedicada:  
[`agents/efficientzero_v2/tests/test_canonical_rl_initialization.py`](../agents/efficientzero_v2/tests/test_canonical_rl_initialization.py) (5/5 tests en verde).

---

## 11. Referencia a la Hoja de Ruta Evolutiva y Linaje

> [!NOTE]
> Toda la matriz de síntesis evolutiva, el estado de implementación de las mejoras de `EfficientZero V2` y las fases futuras de investigación se han unificado canónicamente en el documento final de la documentación: **[09. Hoja de Ruta Evolutiva: Assault Architecture Roadmap (2024–2026)](05_ROADMAP_EVOLUTIVO.md)**.



