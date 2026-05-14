# ASSAULT SIM — PRODUCTION DESIGN DOCUMENT

## 1. VISIÓN DE SISTEMA
Simulador táctico donde RL aprende doctrina táctica basada en terreno.

---

## 2. ARQUITECTURA

GameEngine
 ├── MapSystem
 ├── UnitSystem
 ├── CombatSystem
 ├── TurnSystem
 └── RL_Interface

---

## 3. MAP SYSTEM

class Hex:
    x, y
    terrain_type
    elevation
    movement_cost
    defense_bonus
    blocks_los
    hinders_los

### LOS
CLEAR / HINDERED / BLOCKED

---

## 4. UNIT SYSTEM

States:
NORMAL, DIGGING, DUG_IN, HIDDEN, AMBUSH, SUPPRESSED, FALLBACK

### Transiciones
- Suppression → fallback
- Dig → dug in
- Hide → hidden
- Hidden → ambush

---

## 5. COMBAT SYSTEM

- Dice: RED > YELLOW > GREEN > BLUE
- Resolución: ataque vs defensa
- Daño:
  - damage
  - suppression
  - critical

---

## 6. INTERACCIONES

- Terreno = control combate
- Estados = comportamiento
- LOS = gating ataque

---

## 7. RL

Observación:
- mapa
- unidades
- estados

Acciones:
- move
- fire
- dig
- hide

Reward:
- victoria
- objetivos
- pérdidas

---

## 8. BACKLOG

PRIORIDAD 1
[ ] LOS
[ ] terrain defense
[ ] movement
[ ] suppression
[ ] dig

PRIORIDAD 2
[ ] hide
[ ] ambush
[ ] spotting

PRIORIDAD 3
[X] close combat
[ ] covering fire

PRIORIDAD 4
[ ] fortifications
[ ] minefields

---

## 9. ROADMAP

FASE 1 → terreno + LOS
FASE 2 → infantry core
FASE 3 → stealth
FASE 4 → tactics
FASE 5 → terrain avanzado
FASE 6 → RL scaling

---

## RESULTADO
Sistema táctico completo:
- cobertura
- emboscadas
- moral
- coordinación


💥 9. NIVEL DE PRIORIDAD DE IMPLEMENTACIÓN

🥇 CRÍTICO PARA ESTE ESCENARIO

spawn aleatorio ✅
objetivos VP ✅
presión ✅
terreno defensivo ✅


🥈 IMPORTANTE

fortificaciones
minas
LOS


🥉 AVANZADO

ambush
coordinación
moral completa


🔥 10. CONCLUSIÓN CLARA
👉 Este escenario es:
test perfecto de tu simulador

porque requiere:

asimetría
terreno
timing
objetivos
presión


💥 VERDAD CLAVE
Si tu sim reproduce bien este escenario:
tu motor ya es táctico de verdad


🥇 PRIORIDAD 1 (YA)
✅ Aplicar terreno al combate
Pythondefense = base + terrain_bonusMostrar más líneas

✅ Aplicar rango de ataque
Pythondice = unit.attack[distance]Mostrar más líneas

✅ aplicar traits
Pythonif REMOVE_WEAKEST_TERRAIN_DEFENSE:    remove weakest defense dieMostrar más líneas

🥈 PRIORIDAD 2
✅ LOS real

usar muros
usar edificios
usar bosques


✅ combate completo (suppression + damage)

🥉 PRIORIDAD 3
✅ estados de infantería

dig
hidden
suppressed


🧠 PRIORIDAD 4
✅ lógica de escenario

landing
refuerzos
presión

🧠 🧭 PLAN DE IMPLEMENTACIÓN (ADAPTADO A TU ENGINE)
👉 Objetivo:
pasar de engine correcto → simulador táctico real jugable


🔥 PRINCIPIO CLAVE
Tu problema NO es arquitectura:
NO construir más engine ❌
SÍ conectar lo que ya tienes ✅


 1.2 Pipeline que DEBES tener
 resolve_ranged_combat():

    # 1. distancia → rango
    band = distance_to_range_band(distance)

    # 2. ataque base
    attack_dice = attacker.attack_profile[band]

    # 3. defensa base
    defense_dice = defender.defense_profile

    # 4. aplicar terreno
    defense_dice += terrain_bonus(defender.hex)

    # 5. aplicar LOS
    modifiers += los_modifier(los)

    # 6. aplicar traits
    apply_traits(attacker, defender)

    # 7. tirar dados
    result = compare_dice()

    # 8. aplicar efectos
    apply_damage_and_suppression()
	

✅ 1.3 Tareas concretas
 archivo: terrain_modifier.py
 terrain = game_map.get_hex(defender.pos)

if terrain.type == "building":
    defense_dice += [DiceColor.GREEN]

if terrain.has_cover:
    defense_dice += [DiceColor.BLUE]
	


Task 2 — Sustituir LOS temporal

 Task 3 — Range correcto
 
 band = distance_to_range_band(distance)
attack = attacker.attack_profile[band]

🥈 FASE 2 — TRAITS ENGINE (MUY CRÍTICO)
combat/trait_engine.py
def apply_traits(attacker, defender, context):

    if "REMOVE_WEAKEST_TERRAIN_DEFENSE" in attacker.traits:
        defender.remove_weakest_defense_die()

    if "ATTACK_DIE_REROLL" in attacker.traits:
        attacker.allow_reroll = True
.3 Integración
📍 en resolve_ranged_combat:

apply_traits(attacker, defender, ctx)
``
FASE 3 — INFANTRY STATE MACHINE
3.1 Añadir estados
📍 en unit_instance.py
3.1 Añadir estados
📍 en unit_instance.py
class UnitState(Enum):
    NORMAL
    SUPPRESSED
    DUG_IN
    HIDDEN
	
2 Aplicar en combate
📍 dentro de resolve_ranged_combat

if suppression > 0:
    if defender.state == SUPPRESSED:
        trigger_fallback()
    else:
        defender.state = SUPPRESSED
		
3.3 Añadir efectos
if defender.state == SUPPRESSED:
    defense += [DiceColor.GREEN]
FASE 4 — TERRENO REAL (USANDO LO QUE YA TIENES)
👉 tienes TODO en el 
elementoefectobuilding+defensa fuertewoods+LOS hinderwallbloquea parcialmentewaterpenaliza entrada
if hex.building:
    defense += 2

if hex.woods:
    los = PARTIAL

 FASE 5 — SCENARIO ENGINE
👉 tu Scenario es solo data
5.1 Añadir lógica
def on_turn_start(turn):

    if turn == 2:
        spawn_reinforcements("US")
	
	
 Landing system
def spawn_amphibious(unit):

    zone = random.choice(["A", "B"])

    if crowded:
        unit.attack_modifier = -1
``

✅ 5.3 Pressure system (simplificado)

FASE 6 — RL READY
reward =
    + objetivos
    + supervivencia
    - pérdidas
    - supresión
	
	vector env x8
	
 PLAN RESUMIDO (BRUTALMENTE CLARO)

🥇 Semana 1
✅ terrain → defense
✅ range → dice
✅ LOS real


🥈 Semana 2
✅ traits engine
✅ suppression + fallback


🥉 Semana 3
✅ terrain avanzado
✅ estados (dig/hide)


🧠 Semana 4
✅ scenario dinámico
✅ pressure
✅ landing


🚀 Semana 5
✅ RL integration