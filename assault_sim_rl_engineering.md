# ASSAULT SIM — RL ENGINEERING SPEC (PRODUCTION READY)

---
# 1. SYSTEM GOAL

Train RL agents to learn:
- positioning
- cover usage
- tactical timing

NOT:
- raw damage optimization

---
# 2. INTERFACE DESIGN (GYM STYLE)

class AssaultEnv(gym.Env):
    def __init__(self):
        self.map = Map()
        self.units = []

    def reset(self):
        return observation

    def step(self, action):
        apply_action(action)
        resolve_turn()
        return obs, reward, done, info

---
# 3. OBSERVATION SPACE

obs = {
    "map": tensor(H, W, channels),
    "units": tensor(N, features),
    "states": tensor(N, states)
}

Channels:
- terrain type
- elevation
- cover
- LOS visibility

---
# 4. ACTION SPACE

Discrete actions per unit:
- MOVE
- FIRE
- DIG
- HIDE
- REINFORCE
- PASS

Example encoding:
action = (unit_id, action_type, target)

---
# 5. CORE SYSTEMS

## 5.1 LOS
- raycasting hex-based
- blocked/hindered/clear

## 5.2 Terrain
- defense bonus
- movement cost

## 5.3 Infantry States
NORMAL, DIGGING, DUG_IN, HIDDEN, AMBUSH, SUPPRESSED, FALLBACK

Transitions handled per turn

---
# 6. COMBAT ENGINE

resolve(attacker, defender):
    atk = roll(attacker.dice)
    defn = roll(defender.dice)

    uncancelled = atk - defn
    apply_effects(uncancelled)

---
# 7. REWARD FUNCTION

reward = (
    +10 * win
    +2 * objectives
    -1 * damage_taken
    -2 * suppression
)

---
# 8. MULTI-AGENT LOGIC

Each unit acts sequentially.

Option A: centralized policy
Option B: decentralized agents

---
# 9. TRAINING STRATEGY

## Phase 1
- small maps
- no stealth

## Phase 2
- add cover + LOS

## Phase 3
- full simulation

---
# 10. VECTORIZED ENV

Parallel environments:

for _ in range(N):
    envs.append(AssaultEnv())

---
# 11. BACKLOG TASKS

CORE
[ ] LOS engine
[ ] terrain bonuses
[ ] movement system

INFANTRY
[ ] suppression
[ ] dig
[ ] hide
[ ] ambush

COMBAT
[ ] dice resolution

RL
[ ] observation builder
[ ] reward shaping

---
# 12. FINAL TARGET

Emergent behaviors:
- hold positions
- ambush
- retreat
- coordinate fire



“quiero stacking de suppression tipo pinned”
