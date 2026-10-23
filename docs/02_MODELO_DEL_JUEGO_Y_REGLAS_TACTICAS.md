# Modelo del Juego y Reglas Tácticas: Assault Tactical Engine

> **Estado**: Canónico y Exhaustivo  
> **Ámbito**: Motor de reglas `assault_model/` y su representación matemática en `voec_sim/`.

---

## 1. Topología Hexagonal y Geometría del Tablero

El campo de batalla de *Assault* se modela como una cuadrícula hexagonal regular orientada (*pointy-topped* o *flat-topped*). A diferencia de las cuadrículas cartesianas rectangulares (donde cada celda tiene 4 vecinos ortogonales y 4 diagonales dispares), **cada hexágono posee exactamente 6 vecinos equidistantes**.

```mermaid
graph TD
    subgraph Hex_Coord ["Geometría de Coordenadas Axiales (q, r) - Pointy-Topped"]
        C["Hex Central (q, r)"]
        NW["(q, r-1)\nNoroeste (NW)"]
        NE["(q+1, r-1)\nNoreste (NE)"]
        E["(q+1, r)\nEste (E)"]
        SE["(q, r+1)\nSureste (SE)"]
        SW["(q-1, r+1)\nSuroeste (SW)"]
        W["(q-1, r)\nOeste (W)"]
        
        C --- NW
        C --- NE
        C --- E
        C --- SE
        C --- SW
        C --- W
    end
```

### 1.1. Sistema de Coordenadas Axiales y Cúbicas
Cada hexágono se indexa mediante un par axial $(q, r)$ o un trío cúbico balanceado $(x, y, z)$ donde:
$$x = q, \quad z = r, \quad y = -x - z \iff x + y + z = 0$$

* **Distancia Hexagonal Exacta**:
  $$\text{dist}(h_1, h_2) = \frac{|q_1 - q_2| + |(q_1 + r_1) - (q_2 + r_2)| + |r_1 - r_2|}{2}$$
* **Adyacencia Estricta**: Dos hexágonos son adyacentes si y sólo si $\text{dist}(h_1, h_2) = 1$. No existen "esquinas diagonales".

---

## 2. Tipos de Terreno, Elevación y Cobertura

Cada hexágono posee propiedades físicas que condicionan el coste de movimiento en Puntos de Acción (PA) y proporcionan modificadores de dados a la tirada defensiva:

| Tipo de Terreno | Coste de Entrada (Inf.) | Coste de Entrada (Veh.) | Modificador Cobertura | Bloqueo de LOS | Efectos Especiales |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Despejado (Clear)** | 1 PA | 1 PA | 0 dados extra | No | Campo abierto; máxima vulnerabilidad a fuego cruzado. |
| **Bosque (Woods)** | 2 PA | 3 PA | +1 Dado de Defensa | Sí (a >1 hex) | Ocultamiento visual; limita el alcance efectivo de combate a 2 hexágonos. |
| **Urbano / Edificios** | 2 PA | Impracticable | +2 Dados de Defensa | Sí | Cobertura pesada; inmune a fuego directo de largo alcance salvo demolición. |
| **Colina / Elevación** | +1 PA adicional | +2 PA adicional | +1 Dado (si ventaja) | Condicional | Ventaja de cresta: domina hexágonos inferiores y extiende el spotting. |
| **Bocage / Setos** | 2 PA | 2 PA | +1 Dado de Defensa | Sí (en borde) | Límite visual en la arista de la celda. |
| **Río / Vado** | 3 PA | 4 PA | 0 dados extra | No | Expone a las unidades durante el cruce; penaliza el repliegue. |

---

## 3. Línea de Visión (LOS), Detección (*Spotting*) y Niebla de Guerra

```mermaid
flowchart LR
    A["Unidad Observadora\n(Elevación Z_A)"] --> L["Trazado de Rayo Hexagonal\n(Bresenham Hex Line)"]
    L --> INT["Evaluación de Intersecciones:\n- Elevación relativa\n- Obstáculos (Edificios, Bosques)\n- Humo / Polvo"]
    INT --> RES{"¿Línea Despejada?"}
    RES -- Sí --> SPOTTED["Objetivo Avistado (SPOTTED)\nSe revela en canal sensorial"]
    RES -- No --> HIDDEN["Objetivo en Niebla (HIDDEN)\nSolo última posición conocida"]
```

1. **Trazado de Rayo Hexagonal**: Se calcula la línea de hexágonos interceptada entre el centro del hexágono observador y el centro del objetivo.
2. **Elevación y Puntos Ciegos**: Si un hexágono intermedio posee una elevación $Z_{obs} \ge \min(Z_A, Z_B)$, la LOS se bloquea inmediatamente salvo que la diferencia de altura del observador genere una parábola de visión sobre la cresta.
3. **Parcialidad de la Información (POMDP)**: Las unidades enemigas que no han disparado y se encuentran en terreno cubierto permanecen no detectadas (*unspotted*), lo que obliga a la IA a gestionar la incertidumbre mediante la cabeza táctica `threat_map` y el contexto temporal de la red.

---

## 4. Sistema de Combate: Dados de Batalla, Daño y Supresión

El combate táctico no es un mero cálculo numérico determinista; refleja la letalidad y el caos del combate de infantería a corta y media distancia.

### 4.1. Dados de Batalla (`BattleDie`)
El motor utiliza dados tácticos con caras personalizadas:
* **Dados Blancos**: Representan armamento ligero estándar (fusiles de cerrojo, subfusiles).
* **Dados Negros**: Armamento pesado, ametralladoras coaxiales o fuego concentrado con alta probabilidad de impacto crítico.
* **Caras Posibles**:
  * `MISS` (Fallo): 0 impactos.
  * `HIT` (Impacto): 1 impacto potencial.
  * `DOUBLE_HIT`: 2 impactos directos.
  * `SUPPRESSION`: Impacto moral; induce caída de cohesión sin causar necesariamente bajas físicas.
  * `CRITICAL`: Fuerza una tirada en la tabla de impactos críticos (rotura de arma, baja de oficial, pánico).

### 4.2. Resolución de Combate a Distancia (*Ranged Combat*)

$$\text{Impactos Netos} = \max\left(0, \sum \text{Hits}_{\text{Ataque}} - \sum \text{Saves}_{\text{Defensa}}\right)$$

1. **Composición del Pool Atacante**:
   $$\text{Pool}_{\text{atk}} = \text{ArmaBase} + \text{ModificadorRango} + \text{ModificadorFlanco}$$
2. **Composición del Pool Defensor**:
   $$\text{Pool}_{\text{def}} = \text{DefensaUnidad} + \text{CoberturaTerreno} + \text{Trinchera/Fortificación}$$
3. **Asignación de Bajas**: Cada impacto neto reduce los Puntos de Vida (HP) de la escuadra. Al llegar a 0 HP, la unidad es eliminada del tablero.

---

## 5. Estados de Cohesión y Moral de la Escuadra

Las escuadras transitan dinámicamente entre 4 estados de moral que restringen severamente su capacidad operativa:

```mermaid
stateDiagram-v2
    [*] --> NORMAL: Inicio de Escenario
    NORMAL --> PINNED: Fuego Recibido / Supresión
    PINNED --> SUPPRESSED: Fuego Continuado
    SUPPRESSED --> ROUTED: Bajas Severas o Flanqueo
    
    PINNED --> NORMAL: Recuperación al inicio de turno
    SUPPRESSED --> PINNED: Tirada de Moral Exitosa
    ROUTED --> SUPPRESSED: Concentración con Oficial
    ROUTED --> [*]: Retirada del Mapa / Disolución
```

* **NORMAL**: Operatividad al 100%. Todos los puntos de acción y capacidad de fuego defensivo disponibles.
* **PINNED (Clavada)**: La escuadra busca cobertura inmediata. Pierde el 50% de sus puntos de movimiento; el fuego defensivo sufre una penalización de $-1$ dado.
* **SUPPRESSED (Suprimida)**: Incapaz de moverse o disparar voluntariamente. Solo puede buscar refugio o intentar reorganizarse.
* **ROUTED (En Desbandada)**: Ruptura de la cohesión. La escuadra huye en dirección opuesta al enemigo hacia el borde del mapa. Si recibe combate en este estado, es capturada o destruida.

---

## 6. Fuego de Reacción (*Opportunity Fire*)

Cualquier unidad en estado `NORMAL` con línea de visión despejada que no haya agotado su capacidad de reacción puede interrumpir el movimiento de una unidad enemiga en el momento en que ésta penetra en su arco de fuego:
* **Disparador**: Entrada en un hexágono con menor cobertura o desplazamiento a campo abierto.
* **Consecuencia para la IA**: El agente no puede realizar movimientos lineales despreocupados; cruzar una calle o un campo abierto frente a una ametralladora enemiga (`HMG`) desencadena una ráfaga inmediata que puede clavar (`PINNED`) o destruir la unidad antes de completar su destino.

---

## 7. Asaltos Cuerpo a Cuerpo (*Close Combat / Melee*)

Cuando una escuadra entra físicamente en el mismo hexágono ocupado por tropas enemigas, se produce un **Asalto Inmediato**:
* No se aplican modificadores de distancia (alcance 0).
* Se calcula el ratio de combate cuerpo a cuerpo relativo.
* Es una resolución simultánea y letal: el perdedor es aniquilado o forzado a una retirada desesperada, sufriendo chequeos de moral inmediatos.

### 7.1. Descomposición Secuencial de Asaltos Combinados Multi-Unidad (Palma et al. 2025, Sec. 3.3)
Para reflejar asaltos combinados doctrinales donde una unidad asalta mientras escuadras adyacentes proporcionan apoyo de supresión y cobertura antes de la melé cuerpo a cuerpo:

```mermaid
flowchart LR
    A["Escuadra de Asalto Principal"] --> CC["Asalto en Hexágono Objetivo (q, r)"]
    S1["Escuadra Adyacente 1 (Apoyo Flanqueo)"] -->|commit_support_unit| CC
    S2["Escuadra Pesada (HMG / Mortero)"] -->|commit_support_unit| CC
    CC --> DICE["Ronda 1: Inyección de Dados de Apoyo:\n+1 Verde (Infantería)\n+1 Rojo (Armas Pesadas)"]
    DICE --> RES["Resolución Simultánea de Bajas y Retirada"]
```

1. **Sub-Fase de Compromiso de Apoyo (`commit_support_unit`)**:
   * En [`assault_model/combat/close_combat_context.py`](file:///c:/repos/python/assault/assault_model/combat/close_combat_context.py), el objeto `CombatResolutionContext` permite registrar escuadras adyacentes que apoyan la maniobra tanto en el bando atacante (`supporting_attackers`) como en el defensor (`supporting_defenders`).
2. **Inyección de Dados de Apoyo en Ronda 1**:
   * En [`assault_model/combat/close_combat_resolver.py`](file:///c:/repos/python/assault/assault_model/combat/close_combat_resolver.py), durante la primera ronda del asalto, cada unidad de apoyo viva y no suprimida aporta un dado de ataque adicional:
     * **Infantería Estándar (Fusileros / Asalto)**: $+1$ dado `DiceColor.GREEN`.
     * **Armas Pesadas (`MMG`, `HMG`, `MORTAR`)**: $+1$ dado de alta letalidad `DiceColor.RED`.
3. **Manejo de Bajas y Continuidad**:
   * Si tras la ronda 1 ambos bandos conservan unidades vivas en el hexágono, el combate continúa hasta que un bando es aniquilado o forzado a romper el contacto.

---

## 8. Condiciones de Victoria y Puntos de Victoria (VP)

El desenlace de una partida se rige por una combinación de **control territorial** y **desgaste**:
1. **Control de Puntos de Victoria (VP)**: Hexágonos estratégicos designados (cruces de carreteras, puentes, colinas clave) que otorgan puntos por turno y bonificaciones al final de la partida.
2. **Balance de Bajas (Ratio de Desgaste)**: Puntos otorgados por la eliminación de escuadras enemigas versus penalización por bajas propias.
3. **Límite de Turnos**: Si ningún bando alcanza la victoria por aniquilación antes del límite temporal, el ganador se decide por el diferencial neto de VP.

---

## 9. Arquitectura Modular del Motor `assault_model/`

El motor de reglas está desacoplado siguiendo el patrón de **Estado Inmutable / Runtime de Mutación**:

```mermaid
graph TD
    subgraph Core_Engine ["Motor de Reglas assault_model/"]
        GS["assault_model/state/game_state.py\nGameState (Inmutable / Serializable)"]
        RT["assault_model/runtime/game_state_runtime.py\nRuntimeGameState (Controlador de Ejecución)"]
        
        MAP["assault_model/map/\nHexCoord • HexLine • Terrain • MapPiece"]
        COMBAT["assault_model/combat/\nRangedCombat • CloseCombat • BattleDie • Morale"]
        UNITS["assault_model/units/\nUnitInstance • UnitType • CatalogLoader"]
        REACT["assault_model/runtime/game_state_reactions.py\nReactionFire • ExecutionContext"]
        
        RT --> GS
        RT --> MAP
        RT --> COMBAT
        RT --> UNITS
        RT --> REACT
    end

    subgraph Neural_Interface ["Interfaz Neuronal voec_sim/"]
        VOEC["adapter_voec.py\nTensor 32 Canales (C=32, H, W) + Máscaras de Acción"]
        RT --> VOEC
    end
```

### 9.1. Responsabilidades de los Paquetes Internos

1. **`assault_model/state/` (`GameState`, `TurnState`)**:
   - Contenedor puro de datos serializable en disco o memoria.
   - Almacena el estado de cada celda (`HexState`), el inventario y posición de cada unidad (`UnitInstance`), el marcador de control (`HexOwnership`, `VPTracker`) y el registro de activación por bando.
   - **No contiene lógica de cálculo de combate ni reglas de movimiento**.

2. **`assault_model/runtime/` (`RuntimeGameState`, `ExecutionContext`)**:
   - Orquestador autoritativo del ciclo de simulación.
   - Gestiona el sistema de activación alternada (I-Go-U-Go o impulso táctico).
   - Invalida cachés espaciales mediante `_cache_version` tras cualquier mutación del tablero.
   - Supervisa las interrupciones por fuego de oportunidad (`game_state_reactions.py`).

3. **`assault_model/map/` (`HexCoord`, `HexLine`, `TerrainConfig`)**:
   - Aritmética hexagonal axial $(q, r)$ y cúbica $(x, y, z)$.
   - Algoritmo de ray-casting hexagonal para trazado de Línea de Visión (LOS) y detección de obstáculos.
   - Definición de costes de paso por tipo de terreno y elevación.

4. **`assault_model/combat/` (`RangedCombatResolver`, `CloseCombatResolver`, `BattleDie`, `MoraleState`)**:
   - Cálculo estocástico de dados de combate (`attack_dice_pool.py`, `defense_dice_pool.py`).
   - Resolución de impactos directos, impactos morales de supresión y tablas de efectos críticos.
   - Transiciones de estado de cohesión de tropas (`NORMAL` $\to$ `PINNED` $\to$ `SUPPRESSED` $\to$ `ROUTED`).

---

## 10. Ciclo Autoritativo de Mantenimiento del Estado (*State Loop*)

El siguiente diagrama detalla cómo el motor procesa cada acción individual de un agente o jugador humano, garantizando la consistencia absoluta de las reglas antes de devolver el nuevo estado y la recompensa asociada:

```mermaid
flowchart TD
    START([Acción Emitida: a_t]) --> VAL{Validar Acción Legal\nvs Máscara de Acciones}
    
    VAL -- Ilegal --> ERR[Rechazo de Acción / Penalización]
    VAL -- Legal --> TYPE{Tipo de Acción}

    TYPE -- Movimiento --> MOVE[1. Calcular Ruta Hexagonal\ny Coste en PA]
    MOVE --> OP_CHECK{¿Interrupción por Fuego\nde Reacción Enemigo?}
    
    OP_CHECK -- Sí --> OP_FIRE[2. Ejecutar Fuego de Oportunidad\nResolver Dados Atk vs Def]
    OP_FIRE --> OP_RES{¿Unidad Pinned,\nSuppressed o Eliminada?}
    OP_RES -- Sí --> STOP_MOVE[Movimiento Truncado en Hex Intermedio]
    OP_RES -- No --> CONT_MOVE[3. Completar Desplazamiento\nhacia Hex Destino]
    
    OP_CHECK -- No --> CONT_MOVE
    
    TYPE -- Disparo a Distancia --> RANGED[1. Traza LOS HexLine\n2. Determinar Alcance y Modificadores\n3. Tirada de BattleDice Atk vs Def]
    RANGED --> CASUALTY[4. Aplicar Bajas y Chequeos de Moral]
    
    TYPE -- Asalto Cuerpo a Cuerpo --> MELEE[1. Resolver Combate Cercano Simultáneo\n2. Bajas Brutales y Retirada Forzada]

    TYPE -- Pasar / Reorganizar --> RALLY[Chequeo de Moral / Recuperación de Cohesión]

    CONT_MOVE --> MUTATE[Mutación Atómica del GameState]
    STOP_MOVE --> MUTATE
    CASUALTY --> MUTATE
    MELEE --> MUTATE
    RALLY --> MUTATE

    MUTATE --> POST1[Actualizar Línea de Visión y Niebla: SpottingRuntime]
    POST1 --> POST2[Actualizar Control de Hexágonos y Puntos de Victoria: VPTracker]
    POST2 --> POST3[Alternancia de Turno o Nueva Activación: TurnState]
    POST3 --> POST4[Incrementar _cache_version e Invalidar Cachés]
    POST4 --> OUTCOME{¿Condición de Fin\nde Partida?}
    
    OUTCOME -- Sí --> TERMINAL([Fin de Partida: Victoria / Derrota / Recompensa Final])
    OUTCOME -- No --> TENSOR[voec_sim: Extraer Tensor Sensorial 32-38 Canales,\nConformado de Recompensas PBRS y Nueva Máscara]
    TENSOR --> NEXT([Nuevo Estado o_t+1 Listo para MCTS / Red])
```

---

## 11. Marco de Conformado de Recompensas Invariante (PBRS, Urgencia y Parálisis)

Para resolver el problema del aprendizaje con recompensas dispersas sin alterar el conjunto de políticas óptimas del wargame (teorema de Ng et al., 1999), la capa `voec_sim/core/reward_calculator.py` implementa un andamiaje matemático estricto:

### 11.1. Potencial Radial a VPs ($\Phi$) e Invariancia Telescópica
El potencial del estado respecto a los Puntos de Victoria se define como:
$$\Phi(s) = \sum_{u \in \text{Amigos}} \frac{w_u}{1 + \min_{\text{VP}} d(u, \text{VP})} + B_{\text{ctrl}} \cdot N_{\text{VP\_Controlados}}$$
donde $w_u$ pondera el rol táctico de la unidad (ej. $+25\%$ para unidades de choque `SPEARHEAD`) y $B_{\text{ctrl}} = 2.0$ bonifica el control efectivo.

La función de recompensa adicional por paso satisface:
$$F(s, a, s') = \gamma \Phi(s') - \Phi(s)$$
Garantizando que al final del episodio la suma acumulada sea telescópica $\sum_{t=0}^T \gamma^t F(s_t, a_t, s_{t+1}) = -\Phi(s_0)$ (ya que en estado terminal $\Phi(s_T) \equiv 0.0$), preservando al 100% las garantías de convergencia óptima.

### 11.2. Factor de Presión Temporal Dinámica ($\Psi_{\text{urgency}}$)
Siguiendo la extensión de PBRS para MDPs dependientes del tiempo (Devlin & Kudenko, 2012), cuando el bando amigo controla $0$ VPs, el potencial de distancia se atenúa exponencialmente conforme avanza el horizonte de la batalla ($\tau = t / T_{\text{max}}$):
$$\Phi(s, t) = \Phi_{\text{dist}}(s) \cdot \exp\left(-\lambda \cdot \frac{t}{T_{\text{max}}}\right)$$
con $\lambda = 1.2$. Esto introduce una severa degradación en el valor del estado si la fuerza amiga deambula o se retrasa, incentivando una agresión inmediata y decisiva hacia los objetivos.

### 11.3. Penalización Acumulativa por Parálisis de Unidades Expuestas
Cualquier unidad que permanezca en terreno desprovisto de cobertura defensiva (`cover < 0.35`) fuera del perímetro de un VP controlado, y que pase el turno sin avanzar hacia un objetivo ni abrir fuego, incurre en una penalización por parálisis:
$$\text{Penalty}_{\text{paralysis}} = -w_{\text{paralysis}} \cdot \left(1.0 + 0.5 \cdot \min(4, \text{streak} - 1)\right)$$
* La racha acumula un $+50\%$ adicional por cada turno de pasividad consecutiva (hasta $4\times$).
* Se resetea de forma inmediata a cero en cuanto la unidad realiza una maniobra de aproximación a un VP, abre fuego o entra en una posición con cobertura defensiva adecuada.

---

## 12. Habilidades Especiales de Ingenieros y Zapadores: Carga Explosiva y Detección de Minas

Siguiendo las reglas canónicas del wargame (*Assault Rulebook* §9.6.6.2 y §12.5) y las especificaciones de las cartas de unidades especializadas (ej. *Combat Engineers 43 / US_COMBAT_ENGINEERS_43*), el motor integra dos acciones tácticas dedicadas:

```mermaid
flowchart TD
    subgraph Zapadores ["Habilidades de Ingenieros / Zapadores"]
        EC["💣 EXPLOSIVE_CHARGE (Regla 12.5)\nAcción Rápida de Demolición"]
        MD["🔍 MINE_DETECTION (Regla 9.6.6.2)\nReconocimiento de Minas"]
        
        EC --> TGT["Objetivo Adyacente (Distancia 1):\n- Edificios (single/multi)\n- Fortificaciones (bunkers, trincheras)\n- Obstáculos (alambradas, minas)"]
        TGT --> D_ROLL["Tirada de Combate:\n1 Dado ROJO vs Dado Defensa Terreno más fuerte\n(o 1 Dado VERDE si no hay)"]
        D_ROLL --> EVAL["Resolución Regla 12.5:\n- Crit + Hit: Colapso y Eliminación unidades\n- Crit: Colapso y Mitad de Fuerza\n- 2+ Hits: Colapso y 1 Daño\n- 1 Hit: Obstáculo destruido / Repliegue\n- Supresión: Unidades suprimidas"]
        
        MD --> MD_TGT["Objetivo Hex Actual o Adyacente:\n- Campo de Minas Real o Dummy"]
        MD_TGT --> MD_ROLL["Tirada D6 + Modificadores:\n- Base: 5+ Infantería, 6+ Vehículos\n- Bono +2 por MINE_DETECTION\n- Bono +1 por SCOUT"]
        MD_ROLL --> MD_RES{"¿Éxito?"}
        MD_RES -- Sí --> MD_OK["Campo Identificado con Seguridad\n(Dummy se retira del mapa)"]
        MD_RES -- No --> MD_FAIL["Fallo en Detección\n(Riesgo de detonación al entrar)"]
    end
```

### 12.1. Carga Explosiva (`EXPLOSIVE_CHARGE` - Regla 12.5)
* **Tipo de Acción**: `ActionType.EXPLOSIVE_CHARGE`, `CombatMode.EXPLOSIVE_CHARGE` (`ExplosiveChargeAction`).
* **Condición de Generación**: Unidad activa viva que posee el rasgo `EXPLOSIVE_CHARGE` adyacente a un hexágono con edificios, fortificaciones (`bunker`, `casemate`, `pillbox`, `gun_emplacement`, `trench`, `sandbag`) u obstáculos (`barbed_wire`, `minefield`, `tank_barricade`).
* **Procedimiento de Resolución**:
  1. El atacante tira **1 dado ROJO de combate** (`BattleDie(DiceColor.RED)`).
  2. El defensor tira el **dado de defensa de terreno más fuerte** disponible en el hexágono objetivo. Si no dispone de ningún dado de defensa de terreno (ej. campo de minas en terreno abierto o alambrada), tira **1 dado VERDE por defecto** (`BattleDie(DiceColor.GREEN)`).
  3. Se comparan los resultados mediante `compare_dice()`.
  4. Los impactos y críticos no cancelados dictan el colapso de la estructura y el daño colateral a las unidades en su interior:
     * `CRITICAL + HIT`: Estructura colapsa/destruida; todas las unidades en el hex son **eliminadas**.
     * `CRITICAL`: Estructura colapsa/destruida; todas las unidades quedan reducidas a **media fuerza**.
     * `2+ HITS`: Estructura colapsa/destruida; todas las unidades reciben **1 punto de daño**.
     * `1 HIT`: Los obstáculos lineales (alambradas, campos de minas) son **destruidos y retirados del mapa**. Los edificios y fortificaciones resisten el colapso pero las unidades interiores sufren **repliegue forzado** (*fallback*).
     * `SUPPRESSION`: Estructura no colapsa; unidades interiores quedan **suprimidas**.
  5. **Transformación Física del Terreno**:
     * Los edificios colapsados se transforman en **ruinas** (`Terrain.RUINS`).
     * Los búnkers y posiciones blindadas colapsan al estado de trinchera (`trench`).
     * Las trincheras, pozos de tirador, alambradas y minas se eliminan del tablero.

### 12.2. Detección y Reconocimiento de Minas (`MINE_DETECTION` - Regla 9.6.6.2)
* **Tipo de Acción**: `ActionType.MINE_DETECTION` (`MineDetectionAction`) y bonificador pasivo en movimiento.
* **Condición de Generación**: Unidad con el rasgo `MINE_DETECTION` que se encuentre en el mismo hexágono o adyacente a un marcador de campo de minas no identificado.
* **Mecánica del Bono**:
  * Tirada básica en D6: Requiere un resultado de $5+$ para Infantería y $6+$ para Vehículos/Artillería.
  * El rasgo `MINE_DETECTION` aplica un modificador directo de **$+2$ al dado D6** (acumulable con $+1$ de `SCOUT` o $+1$ de mina no oculta).
  * En caso de éxito, si el marcador es un señuelo (*dummy minefield*), es retirado del tablero inmediatamente; si es un campo de minas real, queda marcado como **identificado** (*identified*), permitiendo al zapador y a las unidades aliadas planificar su cruce o demolición con carga explosiva de manera segura.

### 12.3. Configuración e Inspección en la Interfaz del Editor de Unidades (Puerto 8780)
Ambas habilidades están plenamente expuestas en el servidor visual de catálogo (`tools/unit_editor_server.py`):
* Chips interactivos con estado activo, iconos visuales y tooltips reglamentarios detallados (`TRAIT_HELP`).
* Compatibilidad con importación/exportación de perfiles estándar, inventario de cartas y propuestas de unidades en `assets/catalogs/unit_catalog.json` y `assets/catalogs/unit_staging_proposals.json`.

### 12.4. Rebalanceo de OOB y Despliegue Dinámico de Humo en Escenarios Canónicos (Subtarea 3.5.4)
Para garantizar la viabilidad táctica y el equilibrio competitivo en los escenarios históricos de asalto urbano y desembarco anfibio de Gela, manteniendo estricta fidelidad al manual oficial (Regla 7.2, donde el humo es una acción de combate generada dinámicamente y nunca un obstáculo pre-ubicado estático):
* **Battaglia Cittadina (`assets/scenarios/battaglia_cittadina_2_1.json`)**:
  * Sustitución del equipo `US_BAZOOKA_TEAM` (ineficaz ante fortificaciones y casamatas sin blindados) por **1x `US_COMBAT_ENGINEERS_43`** en la columna de aproximación (`[7, 9]`).
  * **Humo Táctico Dinámico (Regla 7.2)**: Dotación de granadas de humo tácticas (`SMOKE_GRENADES` y modo de ataque `SMOKE` con dados `GREEN, GREEN, BLUE, BLUE`) a los zapadores, coordinados con el fuego indirecto del mortero de 81mm (`US_81MM_MORTAR`). Esto permite generar cortinas de humo en la calle mayor (`q=7, r=6`), cegando las líneas de visión directa de la casamata italiana (`IT_6` en `[3, 4]`) y del francotirador (`IT_7`), permitiendo el avance cubierto sin recurrir a marcadores estáticos artificiales.
* **Mettete i Piedi a Terra (`assets/scenarios/mettete_i_piedi_terra_1.json`)**:
  * Incorporación de **1x `US_COMBAT_ENGINEERS_43`** en el sector central de desembarco (`[4, 12]`), encarado frontalmente a la red de alambradas alemana (`q=4, r=9`).
  * **Capacidad de Brecha y Cegado Táctico**: Empleo de torpedos Bangalore (`BANGALORE_TORPEDO`) y cargas explosivas (`EXPLOSIVE_CHARGE`) para neutralizar la alambrada y campos de minas en los primeros 3 turnos, apoyados por fumígenos dinámicos de ingenieros y mortero para aproximarse bajo fuego de la MG42 alemana.
* **Efectividad Táctica Garantizada**: Con un perfil de asalto de 3 dados a bocajarro (`RED + RED + YELLOW`, 8 puntos de potencia de asalto) frente a defensas fijas de infantería regular (2 puntos), el ratio de asalto alcanza **4.0 $\ge 1.0$**, certificando la capacidad de ruptura y asalto coordinado.




---

## 13. Catálogo Exhaustivo de Habilidades de Unidades (Traits del Editor) y Estado de Implementación

El Editor Táctico de Tropas (`tools/unit_editor_server.py`) y el catálogo maestro (`assets/catalogs/unit_catalog.json`) gestionan **24 habilidades y rasgos doctrinales (`STANDARD_TRAITS`)**. Esta sección audita su formulación matemática, mecánica autoritativa en el motor (`assault_model/`), archivos de resolución y estado exacto de desarrollo.

```mermaid
flowchart TD
    subgraph Engine_Traits ["Arquitectura de Resolución de Traits en el Motor"]
        direction TB
        EDITOR["Editor de Unidades (:8780)
STANDARD_TRAITS (24 Rasgos)"] --> CATALOG["Catálogo Canónico JSON
unit_catalog.json"]
        CATALOG --> UNIT_TYPE["UnitType / UnitInstance
has_trait(trait_name)"]
        
        UNIT_TYPE --> SPOT["1. Detección / LOS (spotting.py)
HIDDEN, CAMOUFLAGED"]
        UNIT_TYPE --> RANGED["2. Fuego a Distancia (ranged_combat_resolver.py)
SNIPER, RAPID_FIRE, INDIRECT_FIRE, NO_LOS, RIFLE_GRENADES, ANTI_TANK"]
        UNIT_TYPE --> CLOSE["3. Combate Cercano (close_combat_resolver.py)
TOUGH, RAPID_FIRE, ASSAULT, TANK_BUSTERS"]
        UNIT_TYPE --> ENG["4. Zapadores y Minas (mine_resolver.py / explosive_charge_resolver.py)
EXPLOSIVE_CHARGE, MINE_DETECTION, SCOUT, BANGALORE"]
        UNIT_TYPE --> MOVE["5. Maniobra y Arcos (movement_rules.py / combat_geometry.py)
SLOW_UNIT, PIVOT, FAST_DISEMBARK"]
        UNIT_TYPE --> SPEC["6. Acciones Especiales (smoke_resolver.py)
SMOKE, SMOKE_GRENADES"]
    end
```

### 13.1. Matriz Canónica de las 24 Habilidades del Editor

| # | Habilidad (`Trait`) | Categoría Operativa | Efecto en Reglamento Oficial (*Assault: Sicily 43*) | Mecánica en Engine (`assault_model/`) | Módulos Responsables | Estado | Unidades en Catálogo |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: | :--- |
| **1** | **`SNIPER`** | Combate Fuego | El defensor pierde el dado de terreno más potente al ser atacado a distancia (solo infantería/artillería). | `_remove_strongest_die(terrain_bonus)` elimina el dado de mayor valor numérico del pool de defensa. | `ranged_combat_resolver.py`<br>`targeting_service.py` | 🟢 **100% Implementado** | `IT_SNIPER_43`<br>`US_SNIPER_43` |
| **2** | **`HIDDEN`** | Detección / LOS | No puede ser avistado automáticamente por proximidad. Solo se revela al disparar o hacer acción rápida. | `can_spot()` retorna `False` salvo que `has_fired_this_turn` o `has_fast_action_this_turn` sean verdaderos. | `spotting.py`<br>`game_state_runtime.py` | 🟢 **100% Implementado** | `IT_SNIPER_43`<br>`US_SNIPER_43` |
| **3** | **`TOUGH`** | Combate Cercano | Ignora 1 punto de daño en la primera ronda de asalto cuerpo a cuerpo. | `attacker_damage = max(0, damage - 1)` aplicado en `ctx.round_number == 1` tanto en ataque como defensa. | `close_combat_resolver.py` | 🟢 **100% Implementado** | `GE_FJ_RIFLES_43`<br>`US_AIRBORNE_RIFLES_43`<br>`UK_PARACHUTE_RIFLES` |
| **4** | **`RAPID_FIRE`** | Combate General | Permite relanzar 1 dado de ataque que resulte fallido en fuego directo o asalto cuerpo a cuerpo. | Relanza dados blancos/amarillos desfavorables vía `_apply_cc002_outflank_reroll()` en asalto y re-roll en ranged. | `close_combat_resolver.py`<br>`ranged_combat_resolver.py` | 🟢 **100% Implementado** | `GE_HEAVY_MG_42`<br>`IT_20MM_BREDA_AA_43` |
| **5** | **`EXPLOSIVE_CHARGE`** | Zapadores / Demolición | Detona cargas de demolición (Regla 12.5) contra edificios, búnkers o campos de minas adyacentes. | Acción rápida `ExplosiveChargeAction`. Tira 1 dado Rojo vs mejor dado de terreno; colapsa estructura y causa daño masivo interior. | `explosive_charge_resolver.py`<br>`action_catalog.py` | 🟢 **100% Implementado** | `US_COMBAT_ENGINEERS_43`<br>`UK_ROYAL_ENGINEERS` |
| **6** | **`MINE_DETECTION`** | Zapadores / Minas | Capacidad especializada de detección y sondeo de campos de minas (Regla 9.6.6.2). | Modificador $+2$ en tirada D6 de detección (`calculate_detection_modifiers`). Si supera umbral, identifica mina o retira dummy. | `mine_resolver.py`<br>`action_catalog.py` | 🟢 **100% Implementado** | `US_COMBAT_ENGINEERS_43`<br>`UK_ROYAL_ENGINEERS` |
| **7** | **`SCOUT`** | Reconocimiento | Reconocimiento de trampas y vanguardia en terreno inexplorado. | Modificador $+1$ en tirada D6 de detección de minas. Asigna automáticamente rol doctrinal `RECON` en MacroPlanner EZv2. | `mine_resolver.py`<br>`macro_planner.py` | 🟢 **100% Implementado** | `US_RANGERS_43` |
| **8** | **`INDIRECT_FIRE`** | Artillería / Morteros | Fuego parabólico sobre obstáculos de terreno sin requerir trazado de LOS directa libre. | Compila tablas `INDIRECT_FIRE` en `UnitType`. Resuelve fuego ignorando penalizaciones de obstáculos intermedios de LOS. | `unit_type.py`<br>`ranged_combat_resolver.py` | 🟢 **100% Implementado** | `GE_50MM_MORTAR`<br>`IT_45MM_BRIXIA`<br>`US_81MM_MORTAR`<br>`GE_FJ_RIFLES_43` |
| **9** | **`NO_LINE_OF_SIGHT`** | Artillería Ligera | El arma está diseñada intrínsecamente para tiro curvo sin visión directa del servidor. | `_resolve_attack_mode()` fuerza automáticamente el modo `INDIRECT_FIRE` ante objetivos en rango sobre colinas o tras bosques. | `unit_type.py` | 🟢 **100% Implementado** | `IT_45MM_BRIXIA` |
| **10** | **`SMOKE`** | Apoyo Táctico | Despliegue de cortinas de humo balísticas (Regla 7.2) en hexágono blanco y hasta 2 adyacentes. | Genera `SmokeAction`. Coloca marcadores que degradan LOS a `HINDERED`/`BLOCKED` y otorgan dados de cobertura defensiva. | `smoke_resolver.py`<br>`action_catalog.py` | 🟢 **100% Implementado** | `GE_50MM_MORTAR`<br>`US_81MM_MORTAR` |
| **11** | **`SMOKE_GRENADES`** | Apoyo Táctico | Granadas de humo manuales de corto alcance para asalto cubierto de infantería. | Subtipo táctico de `SMOKE` asignado a zapadores e infantería de choque (`GREEN, GREEN, BLUE, BLUE`). | `smoke_resolver.py`<br>`unit_type.py` | 🟢 **100% Implementado** | `US_COMBAT_ENGINEERS_43` |
| **12** | **`ASSAULT`** | Choque / Melee | Unidad de choque frontal entrenada para asalto cuerpo a cuerpo agresivo a distancia 0. | Protocolo de asalto coordinado (*Base of Fire* + *Spearhead* con boost $1.40\times$). En editor actúa como etiqueta de doctrina. | `close_combat_resolver.py`<br>`macro_planner.py` | 🟢 **100% Implementado** | Todas las infanterías en rango 0 |
| **13** | **`ANTI_TANK`** | Armas Pesadas | Armamento especializado para penetración balística contra blindados (ATR, Bazooka, Panzerschreck). | Tablas duales de ataque (`INFANTRY` vs `VEHICLE`): dados masivos (`RED + RED + YELLOW`) contra blindados en catálogo JSON. | `unit_type.py`<br>`unit_catalog.json` | 🟡 **Implementado en Tablas** | `IT_SOLOTHURN_ATR_43`<br>`US_BAZOOKA_TEAM`<br>`GE_TANK_HUNTERS_43` |
| **14** | **`RIFLE_GRENADES`** | Infantería | Bocachas lanzagranadas de fusil para fuego curvo a media distancia (1-3 hexágonos). | Integrado en las tablas de ataque de fusileros: rango 1-3 con 2 dados verdes, relanzamiento y remoción de terreno débil. | `unit_catalog.json`<br>`unit_type.py` | 🟡 **Implementado en Tablas** | `GE_RIFLES_43`<br>`GE_FJ_RIFLES_43`<br>`US_RIFLES_43`<br>`US_AIRBORNE_RIFLES_43` |
| **15** | **`SLOW_UNIT` / `SLOW`** | Movilidad | Unidad pesada o de armas colectivas que no puede realizar acciones rápidas de movimiento (Regla 9.2). | Prohibición en `MovementRules.can_use_fast_action()`, descarte en `_move_fire_actions` de `action_catalog.py` y validación estricta en `FastMoveAction.is_valid_for_unit()`. Soporte de alias transparente. | `movement_rules.py`<br>`action_catalog.py`<br>`movement.py` | 🟢 **100% Implementado** | `GE_3_7CM_FLAK_37`<br>`GE_HEAVY_MG_42`<br>`IT_BREDA_MMG`<br>`IT_SOLOTHURN_ATR_43`<br>`US_81MM_MORTAR` |
| **16** | **`PIVOT`** | Encaramiento / Arcos | Arco de fuego libre de 360 grados sin penalizaciones ni restricciones angulares (Regla 10.6). | Función `is_in_arc_of_fire()` omnidireccional en `combat_geometry.py`. Permite tiro a cualquier sector relativo sin girar chasis ni penalizar dados. | `combat_geometry.py`<br>`unit_type.py` | 🟢 **100% Implementado** | `GE_3_7CM_FLAK_37`<br>`IT_20MM_BREDA_AA_43` |
| **16.1** | **`SHIELD`** | Blindaje y Orientación | La unidad orienta automáticamente su blindaje frontal hacia el hexágono al que dispara (Carta S43). | Al ejecutar fuego directo o indirecto en `ranged_combat_resolver.py`, `attacker.facing` muta hacia `calculate_facing_towards(target)`. El contragolpe enemigo impacta en el sector `FRONT` (escudo con dado amarillo). | `ranged_combat_resolver.py`<br>`combat_geometry.py` | 🟢 **100% Implementado** | `GE_3_7CM_FLAK_37` |
| **17** | **`FRAGILE_UNIT`** | Resistencia | Equipos reducidos de 1-2 servidores vulnerables a eliminación por fuego concentrado. | Fuerza máxima reducida (`max_strength = 2` en Bazooka team), provocando chequeos de repliegue moral más rápidos. | `unit_instance.py`<br>`unit_catalog.json` | 🟡 **Implementado en Atributos** | `US_BAZOOKA_TEAM` |
| **18** | **`BANGALORE_TORPEDO`** | Zapadores | Cargas alargadas para volar alambradas y campos de minas en el asalto a playas. | Resuelto a través de `ExplosiveChargeAction` contra obstáculos lineales (`barbed_wire`, `minefield`) a distancia 1. | `explosive_charge_resolver.py` | 🟠 **Resuelto vía Demolición** | `US_COMBAT_ENGINEERS_43` |
| **19** | **`TANK_BUSTERS`** | Asalto Especial | Escuadras cazacarros a pie con minas lapa magnéticas y cócteles Molotov. | En combate cuerpo a cuerpo aplican dados de penetración pesada a distancia cero contra vehículos en el catálogo. | `close_combat_resolver.py`<br>`unit_catalog.json` | 🟠 **Resuelto en Asalto** | `GE_TANK_HUNTERS_43` |
| **20** | **`RECON_PATROL`** | Reconocimiento | Patrulla de choque en vanguardia para reconocimiento agresivo del frente. | Opera en sinergia con `SCOUT` y modula el perfil doctrinal hacia avance rápido por flancos en el MacroPlanner. | `macro_planner.py`<br>`mine_resolver.py` | 🟠 **Resuelto vía Scout/Rol** | `US_RANGERS_43` |
| **21** | **`CAMOUFLAGED`** | Detección / Terreno | Ocultamiento táctico pasivo en cobertura vegetal o edificada. | En terreno con cobertura (`HINDERED` o superior), no puede ser avistada a distancia (>1 hex) a menos que dispare o haga acción rápida. Detección a quemarropa ($\le 1$ hex) operativa. | `spotting.py`<br>`unit_catalog.json` | 🟢 **100% Implementado** | `GE_50MM_MORTAR`<br>`IT_SOLOTHURN_ATR_43`<br>`IT_45MM_BRIXIA`<br>`GE_TANK_HUNTERS_43` |
| **22** | **`CONCEALED`** | Detección / Terreno | Sigilo e infiltración pasiva en matorral, terreno quebrado y zonas cubiertas. | En terreno con cobertura (`HINDERED` o superior), permanece oculta a distancia (>1 hex) sin ser avistada por LOS despejada hasta que abra fuego o realice acción rápida. | `spotting.py`<br>`unit_staging_proposals.json` | 🟢 **100% Implementado** | `UK_COMMANDOS` |
| **23** | **`FAST_DISEMBARK`** | Transporte Mecanizado | Desembarco rápido de vehículos semiorugas Sd.Kfz consumiendo solo 1 MP en vez del turno completo. | Programado para la fase de transporte mecanizado de la Línea 3 del Roadmap (§8.3 del reglamento). | `unit_editor_server.py`<br>`roadmap/03_LINEA_3` | ⚪ **Declarativo / Roadmap L3** | `GE_GRENADIERS_43` |
| **24** | **`PARATROOPS`** | Despliegue Aerotransportado | Inserción aérea y alta cohesión moral en aislamiento tras las líneas defensivas. | En combate cuerpo a cuerpo cuentan con `TOUGH` y máxima cohesión (HP 4). La inserción se modela en escenarios. | `unit_catalog.json`<br>`scenarios/` | ⚪ **Declarativo / Escenario** | `US_AIRBORNE_RIFLES_43`<br>`UK_PARACHUTE_RIFLES` |
| **25** | **`LOW_SILHOUETTE`** | Detección / Perfil Bajo | Perfil bajo y silueta reducida que dificulta el avistamiento enemigo al defender. | Aplica penalización de $-1$ en tiradas D6 de avistamiento del atacante (`calculate_spotting_modifier` en §10.5, TAS §12.3, OAS §12.4). En cobertura defensiva resiste detección a distancia (>1 hex) hasta disparar o correr. | `spotting.py`<br>`unit_editor_server.py` | 🟢 **100% Implementado** | Unidades alemanas S43 (Antitanque/Mortero/Cañón) |
| **26** | **`TALL_SILHOUETTE` / `SILHOUETTE`** | Detección / Silueta Alta | Silueta masiva o emplazamiento elevado que facilita enormemente el avistamiento por parte del enemigo. | Aplica bonificación de $+1$ a las tiradas D6 de avistamiento del atacante en fuego directo (§10.5), TAS (§12.3) y OAS (§12.4). | `spotting.py`<br>`unit_editor_server.py` | 🟢 **100% Implementado** | `IT_90MM_AA_GUN`<br>`GE_8_8CM_FLAK_36`<br>`GE_TIGER_E`<br>`IT_LANCIA_90MM` |
| **27** | **`BACK_BLAST`** | Artillería Cohete / Rebufo | Fogonazo y llamarada trasera al disparar cohetes o proyectiles sin retroceso. | Si la unidad tiene marcador de fuego y es atacada a distancia, un dado amarillo de defensa se degrada a verde. Si dispara dentro de edificio, sufre chequeo de supresión. | `ranged_combat_resolver.py`<br>`unit_catalog.json` | 🟢 **100% Implementado** | `GE_8_8CM_RW43_PUPPCHEN`<br>`GE_7_5CM_LG40` |
| **28** | **`IMMOBILE`** | Artillería Pesada | Emplazamiento estático sin tren de tracción propio (0 MP de chasis). | No puede generar acciones de movimiento autónomo ni acciones rápidas. Requiere transporte para cambiar de posición. | `movement_rules.py`<br>`action_catalog.py` | 🟢 **100% Implementado** | `GE_8_8CM_FLAK_36`<br>`IT_90MM_AA_GUN` |
| **29** | **`SET_UP_TIME`** | Artillería / Emplazamiento | Tiempo prolongado requerido para desplegar apoyos estabilizadores y apuntar. | Prohíbe formalmente la ejecución de acciones compuestas de maniobra con fuego (`MoveThenFireAction` y `FireThenMoveAction`) y acciones rápidas. | `movement_rules.py`<br>`action_catalog.py` | 🟢 **100% Implementado** | `IT_LANCIA_90MM` |
| **30** | **`LIMITED_PIVOT`** | Arcos de Fuego | Arco de tiro restringido exclusivamente a sectores laterales y posteriores (ej. montaje en plataforma de camión sin tiro frontal sobre cabina). | El arco de fuego se limita a 240° (flancos y retaguardia). Fuego hacia el sector frontal bloqueado (`is_in_arc_of_fire`). | `combat_geometry.py`<br>`unit_type.py` | 🟢 **100% Implementado** | `IT_LANCIA_90MM` |
| **31** | **`REAR_ECHELON`** | Servicios / Retaguardia | Tropas de intendencia, logística o servicio técnico con entrenamiento táctico reducido. | Si no cuenta con una unidad amiga en un hexágono adyacente, el atacante recibe automáticamente un resultado de impacto/supresión ('X') al atacarla. | `ranged_combat_resolver.py`<br>`close_combat_resolver.py` | 🟢 **100% Implementado** | `GE_SERVICE_TROOPS`<br>`UK_SERVICE_TROOPS` |
| **32** | **`FLAMETHROWER`** | Armas Especiales / Fuego | Chorro incendiario continuo que arrasa posiciones cubiertas y provoca pánico inmediato. | Los ataques ignoran el dado de defensa más potente del defensor y causan automáticamente 1 resultado de supresión ('X'). | `ranged_combat_resolver.py`<br>`close_combat_resolver.py` | 🟢 **100% Implementado** | `IT_L3_35_FLAME` |
| **33** | **`SMALL`** | Blindados Ligeros / Tamaño | Chasis diminuto o tanqueta de silueta mínima que elude proyectiles balísticos. | Al defender contra fuego a distancia, la unidad puede relanzar 1 dado de defensa desfavorable una vez por ataque. | `ranged_combat_resolver.py` | 🔵 **Fase Vehículos (Siguiente)** | `IT_L3_35`<br>`UK_AT_CARRIER`<br>`UK_BREN_CARRIER`<br>`GE_KETTENKRADS` |
| **34** | **`MANEUVERABLE`** | Blindados / Maniobra | Alta agilidad de orugas o chasis que permite rotar sin fricción motriz. | La unidad no paga puntos de movimiento (0 MP) al cambiar de encaramiento durante su desplazamiento. | `movement_rules.py`<br>`movement.py` | 🔵 **Fase Vehículos (Siguiente)** | `GE_SDKFZ_251_1`<br>`UK_VALENTINE_X`<br>`US_M8_GREYHOUND`<br>`UK_DAIMLER_AC` |
| **35** | **`SLOW_TURRET`** | Blindados / Torreta | Torreta pesada de giro lento gobernada por manivela manual o hidráulica lenta. | La unidad pierde su dado de defensa más débil al realizar fuego de torreta fuera de su arco frontal de chasis. | `ranged_combat_resolver.py`<br>`combat_geometry.py` | 🔵 **Fase Vehículos (Siguiente)** | `GE_TIGER_E` |
| **36** | **`GUN_STABILISATION`** | Blindados / Balística | Giroestabilizador vertical en elevación de cañón principal. | Al realizar fuego en movimiento (`MoveThenFire` / `FireThenMove`), el defensor no recibe el dado de defensa adicional por tiro en movimiento. | `ranged_combat_resolver.py` | 🔵 **Fase Vehículos (Siguiente)** | `US_M5_STUART`<br>`US_M4_SHERMAN` |
| **37** | **`REAR_DRIVER`** | Blindados / Retirada | Puesto de conducción dual gemelo en retaguardia para escape rápido sin virar chasis. | Al moverse marcha atrás, la unidad no divide sus puntos de movimiento a la mitad (§9.3). | `movement_rules.py` | 🔵 **Fase Vehículos (Siguiente)** | `GE_SDKFZ_231`<br>`GE_SDKFZ_233`<br>`IT_AUTOBLINDA_41` |
| **38** | **`QUICK`** | Blindados / Aceleración | Motor de alta aceleración en marchas cortas. | Recibe +1 MP adicional al realizar una maniobra rápida de avance (*fast action*), sumándose a la bonificación base. | `movement_rules.py` | 🔵 **Fase Vehículos (Siguiente)** | `IT_L6_40` |
| **39** | **`AA_MG`** | Apoyo Aéreo / Defensa | Ametralladora de afuste exterior montada en cúpula o afuste antiaéreo. | Capacidad de fuego defensivo reactivo contra unidades de apoyo aéreo táctico (TAS, Regla 12.3.4) con valor balístico azul. | `support_resolver.py` | 🔵 **Fase Vehículos (Siguiente)** | `US_M7_PRIEST`<br>`UK_M7_PRIEST` |
| **40** | **`TRANSPORT (N)`** | Transporte Mecanizado | Capacidad interna de carga y protección balística para pelotones de infantería o piezas ligeras. | Permite embarcar hasta $N$ puntos de fuerza o 1 cañón ligero, desplazarlos y protegerlos de fuegos ligeros. | `transport_rules.py`<br>`roadmap/03_LINEA_3` | 🔵 **Fase Vehículos (Siguiente)** | `GE_SDKFZ_251_1`<br>`US_M3_HALFTRACK`<br>`UK_BREN_CARRIER` |
| **41** | **HEAVY_WEIGHT** | Artillería Pesada / Movilidad | Piezas anticarro o artillería de gran masa y afuste pesado ('This unit must be transported to move up or down an elevation level'). | La unidad no puede cambiar de nivel de elevación (subir o bajar de colina / terreno elevado) por sus propios medios; requiere ser transportada / remolcada por un vehículo. Además, no puede realizar acciones rápidas (*fast action*). | movement_rules.py<br>unit_editor_server.py | 🟢 **100% Implementado** | GE_75MM_ATG_40<br>UK_17_POUNDER_ATG |

---

### 13.1.1. Plan de Implementación Dividido por Fases

A raíz de la auditoría exhaustiva OCR de las 95 cartas físicas, el catálogo de habilidades pendientes se divide formalmente en dos fases de desarrollo desacopladas:

1. **Fase A: Infantería, Artillería y Emplazamientos Pesados (Fase Actual)**:
   - Centrada en el combate a pie, piezas anticarro estáticas, cañones antiaéreos pesados y tropas de servicio:
     - `TALL_SILHOUETTE`: Modificador $+1$ en tiradas D6 de avistamiento enemigo.
     - `BACK_BLAST`: Penalización de defensa por rebufo de cohetes.
     - `IMMOBILE`: Dependencia de transporte/remolque.
     - `SET_UP_TIME`: Incompatibilidad con fuego en movimiento.
     - `LIMITED_PIVOT (240°)`: Restricción angular sobre chasis no blindado.
     - `REAR_ECHELON`: Vulnerabilidad aislada de unidades de servicio.
     - `FLAMETHROWER`: Daño térmico directo y supresión garantizada.

2. **Fase B: Vehículos Blindados, Carros y Transporte Mecanizado (Siguiente Fase)**:
   - Reservada exclusivamente para la fase de mecanización de la Línea 3:
     - `SMALL`: Relanzamiento defensivo en tanquetas y carriers.
     - `MANEUVERABLE`: Rotación a 0 MP de coste.
     - `SLOW_TURRET`: Penalización a fuego de torreta lenta (Tiger I).
     - `GUN_STABILISATION`: Cancelación de bonificación defensiva enemiga en movimiento (Sherman/Stuart).
     - `REAR_DRIVER`: Reversa al 100% de velocidad.
     - `QUICK`: Bono de MP en acciones rápidas.
     - `TRANSPORT (N)` & `FAST_DISEMBARK`: Sistema de embarque/desembarco y semiorugas.
     - `AA_MG`: Fuego antiaéreo de cúpula frente a TAS.

---

### 13.2. Mecánicas Detalladas de Resolución en los Algoritmos del Motor

#### 1. Mecánica de Francotirador (`SNIPER`) en Fuego a Distancia
Cuando una unidad con `SNIPER` (`US_SNIPER_43` o `IT_SNIPER_43`) ejecuta un disparo a distancia contra infantería o artillería:
1. El motor calcula el dado de defensa del hexágono objetivo mediante `TerrainModifier.from_hex()`.
2. Si el terreno otorga múltiples dados de defensa (ej. un bosque con dados `GREEN` y `BLUE`), la función `_remove_strongest_die(terrain_bonus)` identifica el dado de mayor orden jerárquico (`GREEN > BLUE > YELLOW > WHITE`) y lo suprime del pool defensivo.
3. El defensor se ve privado de su mejor bonificación ambiental, simulando el tiro selectivo y la eliminación de tiradores protegidos.

#### 2. Protocolo de Inmunidad a Detección (`HIDDEN`)
La función determinista `can_spot()` en `assault_model/combat/spotting.py` evalúa:
```python
traits = getattr(getattr(target, "unit_type", None), "traits", []) or []
if any(str(t).upper() == "HIDDEN" for t in traits):
    has_fired = bool(getattr(target, "has_fired_this_turn", False))
    has_fast = bool(getattr(target, "has_fast_action_this_turn", False))
    if not (has_fired or has_fast):
        return False  # Inmune a avistamiento automático por LOS despejada
```
La unidad permanece invisible en niebla de guerra para la red neuronal y para bots heurísticos hasta que ejecuta un disparo o una maniobra acelerada.

#### 3. Atenuación de Choque en Asalto (`TOUGH`)
En la resolución de asaltos cuerpo a cuerpo (`assault_model/combat/close_combat_resolver.py`):
```python
if ctx.round_number == 1 and _has_trait(unit, "TOUGH") and damage > 0:
    damage = max(0, damage - 1)
```
Tanto si la unidad asalta como si es asaltada, absorbe el primer punto de daño físico recibido en la ronda inicial, permitiendo a unidades como los Fallschirmjäger o Rangers sobrevivir al contraataque defensivo a quemarropa.

#### 4. Demolición Estructural y Despeje de Obstáculos (`EXPLOSIVE_CHARGE`)
Resuelto por `resolve_explosive_charge()` (`assault_model/combat/explosive_charge_resolver.py`):
* El zapador lanza **1 dado ROJO**.
* El defensor tira el dado más fuerte de la fortificación o terreno (o Verde por defecto).
* Tras comparar resultados con `compare_dice()`:
  * Con 2+ impactos o crítico, la estructura colapsa físicamente: un edificio se convierte en `Terrain.RUINS`, un búnker colapsa a `trench`, y un campo de minas o alambrada se elimina del mapa.
  * Todas las unidades guarnecidas sufren daño colateral letal o reducción a media fuerza.

---

## 14. Catálogo Canónico de Arte Visual, Marcadores y Overlays Tácticos (`assets/art/`)

El entorno visual de *Assault* se basa en una jerarquía de activos gráficos 2D (`assets/art/`) que representan de forma biunívoca el estado del motor (`assault_model/state/`), las fichas de unidad, los modificadores de terreno, la niebla de guerra y los marcadores de mando/moral.

```mermaid
flowchart TD
    subgraph Visual_Pipeline ["Pipeline de Renderizado Visual y Overlays Tácticos"]
        direction TB
        ENGINE_STATE["GameState Autoritativo
(Unidad, Terreno, Moral, PAs)"] --> RESOLVER["Visual Asset Mapper
(assault_ai_ui / editor / reporting)"]
        
        RESOLVER --> HEX_LAYER["1. Tablero y Terreno
assets/art/terrain/ y minefield/"]
        RESOLVER --> COUNTER_LAYER["2. Fichas de Unidad
assets/art/counters/"]
        RESOLVER --> EXP_LAYER["3. Capas de Veteranía/Activación
assets/art/layer/ (Rec, Vet, Hard, Elite, Moved)"]
        RESOLVER --> STATUS_LAYER["4. Estados Tácticos y Órdenes
assets/art/status/ y action_markers/"]
        RESOLVER --> FACTION_LAYER["5. Moral, Bajas y Objetivos
assets/art/markers/ (Hit, Smoke, VP, Dead, Routed)"]
        RESOLVER --> UI_LAYER["6. HUD y Resolución
assets/art/dice/ y icons/"]
    end
```

### 14.1. Marcadores de Estado de Unidad (`assets/art/status/`)
Colección de **16 archivos PNG (176×154 px, modo RGBA con canal alfa)** diseñados como insignias con geometría de chevron que se acoplan directamente a las fichas de combate o se proyectan en el HUD táctico:

| Archivo | Geometría | Estado del Motor (`UnitInstance` / `Action`) | Efecto Normativo en Reglas (*Assault: Sicily 43*) |
| :--- | :---: | :--- | :--- |
| `Status Normal Action.png` | 176×154 | Acción estándar consumida | Gasto nominal de puntos de activación; unidad lista para fases secundarias. |
| `Status Fast Action.png` | 176×154 | `has_fast_action_this_turn = True` | Movimiento rápido (Fast Action / Sprint): doble avance pero penaliza el disparo en el mismo turno. |
| `Status Fast Actionb.png` | 176×154 | Fast Action (reverso agotado) | Indica que la reserva de sprint ha sido completamente ejecutada este turno. |
| `Status Fire and Move.png` | 176×154 | Fuego y Maniobra coordinada | Permite a la escuadra disparar y acto seguido cambiar de posición hacia cobertura. |
| `Status Fire and Moveb.png` | 176×154 | Fuego y Maniobra (reverso) | Fase secundaria de fuego y movimiento concluida. |
| `Status Firing.png` | 176×154 | `has_fired_this_turn = True` | Unidad empeñada en fuego directo; expone su posición y anula camuflaje. |
| `Status Turret Fire.png` | 176×154 | Fuego de torreta acorazada | Fuego vehicular con arco específico sin modificar la orientación del chasis. |
| `Status Hide Action.png` | 176×154 | `is_hidden = True` / Desenfilada | Ocultación voluntaria en cobertura vegetal o desenfilada (+1 nivel defensivo, inmune a LOS lejana). |
| `Status Hide Actionb.png` | 176×154 | Ocultación (reverso confirmado) | Indica posición oculta fija verificada por el árbitro/motor. |
| `Status Dig In.png` | 176×154 | Atrincheramiento en curso | Construcción de pozos de tirador (Foxholes) consumiendo 2 PAs defensivos. |
| `Status Dig Inb.png` | 176×154 | Posición atrincherada consolidada | Otorga bonificación de cobertura atrincherada permanente contra metralla y HE. |
| `Status Delayed Action.png` | 176×154 | Fuego de reacción (Overwatch) | Acción retenida para interrumpir el movimiento enemigo durante su activación. |
| `Status Ambush.png` | 176×154 | Emboscada preparada | Fuego de reacción sorpresa a quemarropa con bonificación a la penetración/moral. |
| `Status Fallback.png` | 176×154 | `is_falling_back = True` | Repliegue forzoso hacia la retaguardia bajo fuego concentrado enemigo. |
| `Status Suppressed.png` | 176×154 | `is_suppressed = True` | Unidad suprimida/clavada al suelo: penalización de -1 dado de ataque y prohibición de avance. |
| `Status Immobile.png` | 176×154 | `is_immobile = True` | Inmovilización mecánica (oruga destruida, motor averiado o dotación fija). |

---

### 14.2. Marcadores Generales, Control de Objetivos y Bajas por Facción (`assets/art/markers/`)
Total: **30 archivos PNG (RGBA)** empleados en el track de turnos, puntos de victoria, logística y gestión psicológica de las fuerzas:

#### A. Combate, Turnos y Control de VPs
* **`Marker Hit.png` (161×143 px):** Marcador de impacto y daño acumulado sobre vehículos o formaciones.
* **`Marker Smoke.png` (71×48 px):** Cortina de humo balística/táctica generada según la Regla 7.2 (degrada o bloquea la LOS).
* **`Marker OBJ.png` (92×92 px):** Marcador neutral de Punto de Victoria (VP) en disputa sobre el hexágono.
* **`Markers Objective Allies.png` / `Markers Objective Axis.png` (92×92 px):** Puntos de Victoria controlados y asegurados por los Aliados o el Eje.
* **`Marker Supply.png` / `Marker Supply 2.png` (92×92 px):** Depósitos de pertrechos, munición disponible y niveles de reabastecimiento.
* **`Marker Turn.png` / `Marker Turn End.png` (71×71 px):** Progreso del turno en curso y delimitador de fase final de turno.
* **`Markers Command.png` / `Markers Commandb.png` (82×82 px):** Marcadores de activación de Plana Mayor / HQ (anverso activo y reverso consumido).

#### B. Moral, Ruptura y Bajas por Nación (92×92 px RGBA)
Cada ejército en combate (Alemania, Italia, Reino Unido y Estados Unidos) dispone de su repertorio formal de marcadores psicológicos y de atrición:

| Facción | Ficha Activa | Bajas Mortales (`Dead`) | En Desbandada (`Routed`) | Rendición (`Surrender`) | Retirada (`Withdraw`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Alemania (GE)** | `Markers Germany.png` | `Markers Germany Dead.png` | `Markers Germany Routed.png` | `Markers Germany Surrender.png` | `Markers Germany Withdraw.png` |
| **Italia (IT)** | `Markers Italy.png` | `Markers Italy Dead.png` | `Markers Italy Routed.png` | `Markers Italy Surrender.png` | `Markers Italy Withdraw.png` |
| **Reino Unido (UK)** | `Markers UK.png` | `Markers UK Dead.png` | `Markers UK Routed.png` | *(N/A)* | `Markers UK Withdraw.png` |
| **EE.UU. (USA)** | `Markers USA.png` | `Markers USA Dead.png` | `Markers USA Routed.png` | `Markers USA Surrender.png` | `Markers USA Withdraw.png` |

---

### 14.3. Marcadores de Acción del Tablero (`assets/art/action_markers/`)
Total: **8 archivos PNG (~119×119 px)**. Utilizados por la interfaz táctica y los visualizadores de la IA para proyectar órdenes directas y comprobaciones de visión:
* **`normal.png` / `fast_action.png`:** Vectores de desplazamiento normal y a la carrera.
* **`firing.png` / `turret_firing.png`:** Designación de hexágonos objetivo de fuego directo y arcos de torreta.
* **`fire_move.png` / `move_fire.png`:** Secuencias combinadas de maniobra y disparo.
* **`spotted.png` / `no_spotted.png`:** Estado de reconocimiento en niebla de guerra: contacto visual confirmado vs. objetivo oculto.

---

### 14.4. Capas de Veteranía y Activación (`assets/art/layer/`)
Total: **5 archivos PNG (161×143 px, RGBA con transparencia)** superpuestos dinámicamente sobre el counter base de la unidad:
* **`Layer_Rec.png` (Recluta - Nivel 1):** Tropas noveles con mayor susceptibilidad al fuego de supresión.
* **`Layer_Vet.png` (Veterano - Nivel 2):** Nivel regular de campaña; cohesión doctrinal estándar.
* **`Layer_Hard.png` (Curtido - Nivel 3):** Tropas fogueadas con bono de resistencia a la desbandada.
* **`Layer_Elite.png` (Élite - Nivel 4):** Unidades de choque (Fallschirmjäger, Rangers, Paracaidistas) con bonificación en combate cercano.
* **`Layer_Moved.png` (Activada):** Máscara oscura semitransparente que atempera el contraste de las unidades que ya finalizaron su turno.

---

### 14.5. Campos de Minas y Trampas Defensivas (`assets/art/minefield/`)
Total: **4 archivos PNG (130×112 px, RGBA)**:
* **`Minefield AP.png`:** Campo de minas antipersonal (amenaza de fragmentación contra infantería a pie).
* **`Minefield AT.png`:** Campo de minas anticarro (detonación balística pesada contra barcazas y trenes de rodaje).
* **`Minefield Dummy.png`:** Falso campo minado colocado para engaño táctico y canalización del atacante.
* **`Minefield Back.png`:** Reverso neutro e inexplorado que oculta la naturaleza del obstáculo hasta que un zapador con `MINE_DETECTION` o `SCOUT` lo sondea con éxito.

---

### 14.6. Fortificaciones y Modificadores de Terreno (`assets/art/terrain/`)
Total: **11 archivos PNG (RGBA)** que modifican dinámicamente las propiedades de cobertura física del hexágono:
* **Fortificaciones de Campaña (155×129 px):**
  * `Terrain Trenches.png`: Red de trincheras reforzadas (+2 dados de defensa frente a fuego directo).
  * `Terrain Sandbag Position.png`: Parapetos de sacos terreros para armas colectivas (MG42, Breda, Morteros).
  * `Terrain Barbed Wire.png`: Alambradas de espino (coste de movimiento × 3 e impedimento de avance rápido).
  * `Terrain Tank Barricades.png`: Erizos checos y dientes de dragón que bloquean el tránsito de vehículos acorazados.
  * `Terrain Bunker.png`: Búnker de hormigón armado (cobertura pesada y protección antibombardeo).
  * `Terrain Pillbox.png`: Casamata de hormigón con troneras protegidas para fuego rasante.
  * `Terrain Gun Emplacement.png`: Emplazamiento atrincherado para piezas de artillería o cañones anticarro PaK.
* **Cráteres de Artillería y Ruinas Urbanas (229×265 px):**
  * `Terrain Crater Clear.png`: Embudo de proyectil en campo abierto (+1 cobertura improvisada).
  * `Terrain Crater Trees.png`: Cráter en bosque que rompe el arbolado creando terreno difícil.
  * `Terrain Crater Building Black.png`: Escombros oscuros de edificio de mampostería colapsado.
  * `Terrain Crater Building Red.png`: Ruinas de ladrillo urbano destruido (impide vehículos, ofrece refugio a infantería).

---

### 14.7. Dados de Combate y Resolución (`assets/art/dice/`)
Total: **24 archivos PNG** que materializan el sistema probabilístico del juego:
* **Dados D6 Numéricos (25×25 px RGBA):** `D6_Black1.png` a `D6_Black6.png`, y `Dice Red 6.png` para chequeos de moral, eventos de escenario y detección de minas.
* **Dados Tácticos de Fuego por Colores (92×92 px RGB):**
  * **Azul (`blue_00.png` a `blue_02.png`):** Armamento ligero secundario y apoyo de fusilería.
  * **Verde (`green_00.png` a `green_03.png`):** Fusiles estándar, ametralladoras ligeras y fuego regular.
  * **Rojo (`red_00.png` a `red_04.png`):** Proyectiles de alto calibre, cargas huecas y armamento pesado anticarro.
  * **Amarillo (`yellow_00.png` a `yellow_04.png`):** Fuego de morteros, fragmentación y metralla de área.

---

### 14.8. Iconografía de Interfaz y Herramientas (`assets/art/icons/`)
Total: **31 archivos PNG (25×25 px)** integrados en la consola de mando, barra de herramientas y paneles MLOps:
* **Control de Simulación:** `Icon_Play`, `Icon_Reset`, `Icon_Undo`, `Icon_Roll Dice`, `Icon_LOS`, `Icon_Tracks`, `Icon_Cleanup`.
* **Herramientas de Visor y Zoom:** `Icon_Zoom-In`, `Icon_Zoom-Out`, `Icon_ZoomSelect`, `Icon_ImageCapture`.
* **Facciones y Filtros Doctrinales:** `Icon_GE`, `Icon_GE Planning`, `Icon_IT`, `Icon_IT Planning`, `Icon_UK`, `Icon_UK Planning`, `Icon_US`, `Icon_US Planning`.
* **Paneles de Tarjetas y Sistema:** `Icon_Command Card`, `Icon_Commmand Cards`, `Icon Tactical Cards`, `Icon_Minefield`, `Icon_Pieces`, `Icon_HidePieces`, `Icon_Server`, `Icon_User`, `Icon_Notepad`.

---

## 15. Catálogo Canónico de Formaciones Tácticas (Combined Arms OOB) y Anatomía de Cartas

En concordancia con la **Sección 4.1, 4.9.2 y 5.0 del Reglamento Oficial de Assault: Sicily 43**, las formaciones representan las unidades militares orgánicas combinadas (compañías y pelotones) que se seleccionan y despliegan en el tablero táctico.

### 15.1. Anatomía Visual y Marcadores de las Cartas de Formación (`assets/art/formations/`, 122 cartas)

1. **Círculo Inferior Derecho: Puntos de Mando (*Command Points / CP*) y Nivel Cualitativo:**
   * **Galones / Chevrons Interiores (`v`, `vv`, `vvv`):** Indican la cantidad de **Puntos de Mando (*Command Points*)** que la formación inyecta en el pool de mando de la facción al inicio de cada turno (Regla 4.9.2):
     * **1 Galón (`v`):** 1 Command Point aportado (típico de destacamentos de apoyo menores o de segunda línea).
     * **2 Galones (`vv`):** 2 Command Points aportados (pelotones y compañías de infantería estándar).
     * **3 Galones (`vvv`):** 3 Command Points aportados (unidades de élite, paracaidistas, comandos y tropas de choque).
   * **Color de Fondo del Círculo (Nivel de Experiencia, Regla 4.2.3):**
     * 🔵 **Azul (`RECRUIT`):** Reclutas; el atacante obtiene automáticamente un símbolo de impacto `X` al disparar contra la unidad.
     * 🟢 **Verde (`HARDENED`):** Endurecido / Curtido; añade $+1$ dado de combate azul de defensa adicional a las unidades con experiencia.
     * 🟠 **Naranja (`VETERAN`):** Veterano; añade $+1$ dado de combate azul de ataque adicional a las unidades con experiencia.
     * 🔴 **Rojo (`ELITE`):** Élite; ignora por completo los efectos y penalizaciones por supresión.

2. **Círculo Inferior Izquierdo: Dotación de Unidades con Experiencia Inicial (`xN`):**
   * El icono rojo con el soldado saludando y un multiplicador numérico (ej. `x4`, `x5`, `x8`) define el número exacto de escuadras de la formación que entran en despliegue con el marcador de experiencia correspondiente sobre el mapa.

3. **Código de Módulo y Serie Histórica:**
   * Ubicado bajo el círculo derecho (ej. `S43` = *Sicily 43*, `Pr43` = *Paratroopers 43*).

### 15.2. Modelo de Dominio y Contratos (`assault_model/units/formation.py`)

El motor modela formalmente estos atributos a través de la clase dataclass `Formation` y el catálogo canónico `assets/catalogs/formation_catalog.json`:

```python
@dataclass
class Formation:
    id: str
    name: str
    side: str
    command_rating: int = 8
    command_points: int = 2                       # 1, 2 o 3 según galones
    experience_level: str = "REGULAR"            # RECRUIT, REGULAR, HARDENED, VETERAN, ELITE
    experience_units_count: int = 0              # Cantidad de escuadras con experiencia (xN)
    line_units: List[str] = field(default_factory=list)
    heavy_weapons: List[str] = field(default_factory=list)
    specialists: List[str] = field(default_factory=list)
    units: List[str] = field(default_factory=list)
    card_image: str = ""
    description: str = ""
```

### 15.3. Integración en el Editor Táctico de Unidades y Formaciones (Puerto 8780)

La interfaz web en `tools/unit_editor_server.py` expone:
* Selectores dedicados de **Command Points (`1 CP`, `2 CP`, `3 CP`)**.
* Selectores tipados de **Experience Level** con su color distintivo.
* Contador numérico de **Exp. Units (`xN`)**.
* Badges de cabecera con actualización reactiva en tiempo real sobre el panel de inspección de la formación.

---

## 16. Algoritmo Canónico de Retirada a Borde Amigo en Desenfilada (Sección 6.4 / Regla 13.3)

El manual oficial (*Rulebook rev6* §6.4 y §13.3) estipula que una unidad que sufre un estado de retirada (*Fallback*) tras fuego concentrado o acumulación de impactos de supresión debe realizar un repliegue táctico:
> *«The unit is in retreat. It performs a fast action... away from the direction of the attack. Each hex should increase the distance between it and any enemy units. If that isn't possible at any point during the fallback, the unit takes a damage point and remains in the hex it was last able to retreat into. Artillery or immobilised units are eliminated if they are ever in fallback. All units are eliminated if they ever receive a second fallback.»*

Para materializar esta doctrina con fidelidad estricta y desterrar primitivas aleatorias o cableadas, el motor táctico implementa en `MovementRules.calculate_fallback_destination` un algoritmo determinista de selección de hexágono ponderado:

```mermaid
flowchart TD
    subgraph Fallback_Selection ["Algoritmo de Retirada en Desenfilada (Regla 13.3)"]
        direction TB
        EVENT["Impacto de Supresión / Fallback en Combate"] --> CHECK_TYPE{"¿Artillería o Inmovilizado?"}
        CHECK_TYPE -- SÍ --> ELIMINATED["Eliminación Inmediata de la Unidad (strength = 0, alive = False)"]
        CHECK_TYPE -- NO --> GET_NEIGHBORS["Evaluar 6 Vecinos Adyacentes (can_enter_hex, límites del mapa, sin unidades enemigas)"]
        
        GET_NEIGHBORS --> EVALUATE["Cálculo de Puntuación Táctica por Hexágono (h)"]
        
        EVALUATE --> P1["1. Desenfilada (LOS vs Atacante)
BLOCKED: +100 pts | HINDERED: +40 pts | CLEAR: 0 pts"]
        EVALUATE --> P2["2. Cobertura Terreno/Fortificación
Búnker: +15 | Casamata: +12 | Trinchera: +8 | Bosque: +6 | Sacos: +4"]
        EVALUATE --> P3["3. Distancia al Atacante
Δdist > 0: +30*Δdist | Δdist = 0: +5 | Δdist < 0: -500 (Penalizado)"]
        EVALUATE --> P4["4. Orientación Borde Amigo (Friendly Edge)
NORTH: -(Δr)*15 | SOUTH: +(Δr)*15 | EAST / WEST"]
        
        P1 & P2 & P3 & P4 --> DECIDE{"¿Existe Hexágono Legal?"}
        DECIDE -- SÍ --> RETREAT["Desplazamiento al Hexágono Óptimo y Recálculo de Control Territorial"]
        DECIDE -- NO --> DAMAGE["Regla 13.3: Sufre 1 Daño (strength -= 1) y Permanece en Posición Actual"]
    end
```

### 16.1. Jerarquía de Evaluación y Ponderaciones
Para cada hexágono legal adyacente $h \in \mathcal{N}(	ext{pos})$:
$$	ext{Score}(h) = 	ext{Score}_{	ext{defilade}}(h) + 	ext{Score}_{	ext{cover}}(h) + 	ext{Score}_{	ext{dist}}(h) + 	ext{Score}_{	ext{edge}}(h)$$

1. **Desenfilada (*Defilade*)**:
   - `LineOfSight.BLOCKED` (+100 pts): Desenfilada total. El atacante pierde la línea de visión directa tras un obstáculo (edificio, colina o arbolado denso).
   - `LineOfSight.HINDERED` (+40 pts): Desenfilada parcial a través de humo, matorral o arbolado ligero.
   - `LineOfSight.CLEAR` (0 pts): Hexágono expuesto al fuego enemigo directo.
2. **Cobertura Defensiva de Terreno**:
   - Ponderación de los dados de defensa otorgados según la categoría de unidad (verde = 6, azul = 4, amarillo = 2).
   - Bonificación de fortificaciones fijas: búnker (+15), casamata/pillbox (+12), trinchera (+8), parapeto de sacos (+4).
3. **Distancia al Atacante (*Away from Attack*)**:
   - Se bonifica alejarse del atacante ($\Delta 	ext{dist} > 0 \implies +30 	imes \Delta 	ext{dist}$).
   - Se penaliza drásticamente (-500 pts) cualquier paso que reduzca la distancia hacia la amenaza que provocó el combate.
4. **Borde Amigo (*Friendly Edge Alignment*)**:
   - Se prioriza la retaguardia de la facción (Norte para IT/GE, Sur para US/UK en el teatro de Sicilia, o vector opuesto al atacante).
5. **Criterio de Desempate Determinista**:
   `key = (total_score, defilade_score, cover_score, cand_dist, -q, -r)`.

### 16.2. Reglas Especiales de la Sección 13.3
* **Artillería e Inmovilizados**: La artillería a pie y los vehículos inmovilizados no pueden ejecutar maniobras de repliegue bajo fuego; son declarados baja inmediatamente (`alive = False`, `strength = 0`).
* **Unidad Atrapada / Rodeada**: Si la unidad se encuentra cercada por tropas enemigas o terreno intransitable sin ningún hexágono legal de retirada, sufre **1 punto de daño** (`strength -= 1`) y permanece en su posición original, simulando el castigo de ser acorralada sin opción de escape.

---

<span id="seccion-17-presupuesto-turnos"></span>
## 17. Presupuesto Dinámico de Simulación y Horizonte Gobernado por Turnos con Refuerzos (Turn-Authoritative Episode Horizon) [v2.5.12]

### 17.1. Diagnóstico del Problema: Desincronización entre Pasos RL y Turnos de Wargame
En el diseño clásico de aprendizaje por refuerzo (RL), los episodios suelen truncarse mediante un número fijo de micro-pasos de decisión (`max_steps`). En versiones previas del autojuego (`selfplay.py`), el presupuesto efectivo se estimaba al inicio del episodio ($t=0$) mediante una fórmula estática:
$$\text{effective\_max\_steps} = \text{scenario\_turns} \times \text{unit\_count}$$

Esta formulación colapsaba críticamente ante dos realidades del wargame táctico:
1. **Llegada Dinámica de Refuerzos (Fase de Organización)**: En escenarios como *Mettete i piedi per terra!* (Gela), el bando atacante inicia en Turno 1 con solo 7 unidades (Ola 1). En el Turno 2 desembarca la Ola 2 (+7 unidades), duplicando el número de activaciones por turno. Al medir `unit_count` solo en $t=0$, el presupuesto de pasos se agotaba prematuramente hacia el Turno 4 o 5 de 8.
2. **Falsos Timeouts y Castigo Catastrófico**: Cuando el bucle de autojuego agotaba los pasos asignados sin que el motor de wargame hubiera concluido (`not adapter.terminal()`), el sistema aplicaba una penalización catastrófica de timeout (-1.0). El agente aprendía una **parálisis defensiva espuria**, concluyendo que avanzar hacia los VPs era inútil porque el reloj de pasos siempre lo ejecutaba antes de poder jugar los 8 turnos reglamentarios.

### 17.2. Arquitectura de Gobernanza por Turnos (Turn-Authoritative Execution)
Para alinear 100% la simulación con el reglamento canónico de Assault, se establece la gobernanza autoritativa por turnos:

```mermaid
flowchart TD
    subgraph Engine["Wargame Engine (assault_model / voec_sim)"]
        direction TB
        T["Turno T <= T_max"] --> ACT["Fase de Acción (Alternancia de Activaciones)"]
        ACT --> ADV{"¿Todas las unidades elegibles han actuado?"}
        ADV -- SÍ --> NEXT_TURN["advance_turn() -> T = T + 1"]
        NEXT_TURN --> REINF["Fase de Organización: Despliegue de Refuerzos Programados"]
        REINF --> CHECK_TERM{"¿T > T_max o Victoria/Eliminación?"}
        CHECK_TERM -- SÍ --> DONE["state.done = True | adapter.terminal() == True"]
        CHECK_TERM -- NO --> ACT
    end

    subgraph SelfPlay["Autojuego y Simulación (EfficientZero V2)"]
        direction TB
        START["Iniciar Episodio"] --> LOOP["Bucle de Simulación: while not adapter.terminal()"]
        LOOP --> STEP["MCTS Inferencia -> adapter.apply(action)"]
        STEP --> WD{"Watchdog por Turno:
steps_in_turn > max(30, alive * 4)"}
        WD -- SÍ (Deadlock) --> DEADLOCK["Abortar por Deadlock:
terminal_reason = turn_deadlock_watchdog
Penalización Timeout"]
        WD -- NO --> DONE_CHECK{"¿done / terminal?"}
        DONE_CHECK -- SÍ --> CANONICAL_EVAL["Evaluación de Resultado Canónico
(Puntos VP / Casualties / Score)
Sin penalización espuria"]
        DONE_CHECK -- NO --> LOOP
    end
```

### 17.3. Componentes Implementados

1. **Cálculo del OOB Total (`scenario_total_units`)**:
   Tanto en `VOECSimulator` como en `EZV2VOECAdapter`, se inspecciona el catálogo del escenario para computar la totalidad de unidades iniciales más todas las oleadas de refuerzos programadas:
   $$\text{total\_units} = N_{\text{initial}} + \sum_{\text{wave} \in \mathcal{R}} |\text{wave.units}|$$
   El presupuesto efectivo se escala con respecto a este OOB integral:
   $$\text{effective\_max\_steps} = \lceil T_{\text{scenario}} \times \text{total\_units} \times \text{steps\_per\_unit\_turn} \rceil$$

2. **Headroom Táctico por Activación (`steps_per_unit_turn = 2.5`)**:
   Cada unidad en Assault puede requerir múltiples micro-pasos de decisión por ciclo de activación (movimiento, ventana de fuego de reacción enemiga, disparo propio, acción rápida). Un multiplicador de $2.5\times$ garantiza suficiente margen para maniobra compleja sin ahogar al agente.

3. **Watchdog de Deadlock por Turno (`turn_deadlock_watchdog`)**:
   Para proteger la simulación de bucles patológicos infinitos (ej. dos unidades pasando turno indefinidamente en un estancamiento) sin cortar turnos legítimos:
   - Al inicio de cada turno de wargame, se reinicia el contador de pasos: `steps_in_current_turn = 0`.
   - Se establece un techo específico para el turno: $\text{max\_steps\_per\_turn} = \max(30, N_{\text{alive}} \times 4)$.
   - Si se supera este techo dentro de un único turno, se marca `terminal_reason = "turn_deadlock_watchdog"` y se aborta el episodio. Partidas que fluyen con normalidad avanzan de turno en turno sin verse afectadas.

4. **Preservación del Resultado Canónico al Alcanzar $T_{\max}$**:
   Al alcanzar $T > T_{\max}$, el motor marca `adapter.terminal() == True`. En este caso, la partida concluye con su evaluación de victoria/derrota legítima por control de VPs y bajas, **sin** aplicar la penalización catastrófica de timeout (-1.0).

