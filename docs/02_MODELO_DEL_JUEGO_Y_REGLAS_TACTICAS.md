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


